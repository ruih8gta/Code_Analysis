"""COBOLプログラム1本から、ビューワーの材料になる事実（ファクト）を抽出する。

固定形式（1〜6桁目が連番、7桁目が標識、8〜72桁目が本文）を前提にした簡易解析です。
完全なCOBOL構文解析器ではありません。対応しない構文は unsupported に記録します。

使い方:
  python -X utf8 extract_cobol.py PROGRAM.cbl --copybooks DIR [--copybooks DIR2] --out facts.json

抽出するもの:
  - SELECT（DD名・編成・アクセス・キー・状態変数）と FD レコード
  - COPY 句を展開したデータ定義（01レコードごとの項目、位置、PIC、COPY句名）
  - 段落の行範囲
  - OPEN／READ／WRITE／REWRITE／DELETE／START／CLOSE と CALL
  - ファイルごとの CRUD（R=READ、C=WRITE、U=REWRITE、D=DELETE、O=開閉のみ）
  - レコードのキー項目（FDのキー位置と一致するCOPY句の項目）
"""
import argparse
import json
import re
from pathlib import Path

NAME = r"[A-Z0-9][A-Z0-9-]*"


def read_lines(path):
    return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()


def code_of(line):
    """標識と本文を返す。コメント行は None。"""
    if len(line) < 7:
        return " ", ""
    ind = line[6]
    if ind in "*/":
        return ind, None
    return ind, line[7:72]


def statements(lines, origin, start=1, stop=None):
    """データ部の記述を「.」区切りの文にまとめる。引用符内の「.」は区切りにしない。"""
    out, buf, first, quote = [], "", None, None
    stop = stop or len(lines)
    for no in range(start, stop + 1):
        _, code = code_of(lines[no - 1])
        if code is None:
            continue
        for i, ch in enumerate(code):
            if quote:
                buf += ch
                if ch == quote:
                    quote = None
                continue
            if ch in "'\"":
                quote = ch
            if first is None and ch.strip():
                first = no
            if ch == "." and (i + 1 == len(code) or code[i + 1] == " "):
                text = " ".join(buf.split())
                if text:
                    out.append({"text": text, "line": first, "origin": origin})
                buf, first = "", None
                continue
            buf += ch
        buf += " "
    return out


def pic_size(pic, usage):
    expanded = re.sub(r"(.)\((\d+)\)", lambda m: m.group(1) * int(m.group(2)), pic.upper())
    digits = sum(1 for c in expanded if c in "9")
    chars = sum(1 for c in expanded if c not in "SVP")
    usage = (usage or "").upper()
    if usage in ("COMP-3", "PACKED-DECIMAL"):
        return digits // 2 + 1
    if usage in ("COMP", "COMP-4", "COMP-5", "BINARY"):
        return 2 if digits <= 4 else 4 if digits <= 9 else 8
    if usage == "COMP-1":
        return 4
    if usage == "COMP-2":
        return 8
    return chars


ENTRY = re.compile(r"^(\d{1,2})\s+(" + NAME + r")?(.*)$")


def parse_entry(stmt):
    m = ENTRY.match(stmt["text"])
    if not m:
        return None
    level, name, rest = int(m.group(1)), m.group(2) or "FILLER", m.group(3)
    if name in ("PIC", "PICTURE", "VALUE", "REDEFINES", "OCCURS", "USAGE", "COMP", "COMP-3"):
        rest, name = name + rest, "FILLER"
    pic = re.search(r"\bPIC(?:TURE)?\s+(?:IS\s+)?(\S+)", rest)
    usage = re.search(r"\b(COMP-[1-5]|COMP|BINARY|PACKED-DECIMAL|DISPLAY)\b", rest)
    occurs = re.search(r"\bOCCURS\s+(\d+)", rest)
    redefines = re.search(r"\bREDEFINES\s+(" + NAME + ")", rest)
    return {
        "level": level, "name": name, "pic": pic.group(1).rstrip(".") if pic else None,
        "usage": usage.group(1) if usage else None, "occurs": int(occurs.group(1)) if occurs else 1,
        "redefines": redefines.group(1) if redefines else None, "line": stmt["line"], "origin": stmt["origin"],
    }


def layout(node, start):
    node["start"] = start
    if node.get("pic"):
        node["size"] = pic_size(node["pic"], node.get("usage"))
        return node["size"]
    off, end = start, start
    placed = {}
    for c in node["children"]:
        if c.get("redefines") and c["redefines"] in placed:
            target = placed[c["redefines"]]
            size = layout(c, target["start"]) * c["occurs"]
            end = max(end, target["start"] + size)
            continue
        size = layout(c, off) * c["occurs"]
        placed[c["name"]] = c
        off += size
        end = max(end, off)
    node["size"] = end - start
    return node["size"]


def records_from(entries):
    """データ記述の並びを01レコードの木にして、位置を計算する。"""
    records, stack = [], []
    for e in entries:
        if e["level"] in (66, 88):
            continue
        lvl = 1 if e["level"] in (1, 77) else e["level"]
        e = dict(e, lvl=lvl, children=[])
        while stack and stack[-1]["lvl"] >= lvl:
            stack.pop()
        if stack:
            stack[-1]["children"].append(e)
        else:
            records.append(e)
        stack.append(e)
    for r in records:
        layout(r, 0)
    return records


def flatten(record):
    out, groups = [], []

    def walk(n, path):
        for c in n["children"]:
            if c["children"]:
                groups.append({"name": c["name"], "pos": [c["start"] + 1, c["start"] + c["size"] * c["occurs"]], "line": c["line"]})
                walk(c, path + [c["name"]])
            else:
                out.append({
                    "name": c["name"], "pic": c.get("pic"), "usage": c.get("usage"),
                    "pos": [c["start"] + 1, c["start"] + c["size"] * c["occurs"]],
                    "occurs": c["occurs"], "group": path[-1] if path else None,
                    "line": c["line"], "origin": c["origin"],
                })
    if record["children"]:
        walk(record, [])
    elif record.get("pic"):
        out.append({"name": record["name"], "pic": record["pic"], "usage": record.get("usage"),
                    "pos": [1, record["size"]], "occurs": 1, "group": None,
                    "line": record["line"], "origin": record["origin"]})
    return out, groups


def find_copybook(name, dirs):
    for d in dirs:
        for ext in (".cpy", ".CPY", ".cbl", ""):
            p = Path(d) / (name + ext)
            if p.exists():
                return p
    return None


def extract(path, copy_dirs):
    lines = read_lines(path)
    text_lines = [(i + 1, code_of(l)[1]) for i, l in enumerate(lines)]
    find = lambda pat: next((no for no, c in text_lines if c and re.search(pat, c)), None)
    program = re.search(r"PROGRAM-ID\.\s*(" + NAME + ")", "\n".join(c or "" for _, c in text_lines))
    data_div, proc_div = find(r"\bDATA\s+DIVISION"), find(r"\bPROCEDURE\s+DIVISION")
    facts = {"program": program.group(1) if program else Path(path).stem, "source": str(path),
             "lines": len(lines), "divisions": {"data": data_div, "procedure": proc_div},
             "files": [], "records": [], "paragraphs": [], "copies": [], "ops": [], "calls": [], "unsupported": []}

    # SELECT
    sel_text = statements(lines, "program", find(r"FILE-CONTROL") or 1, (data_div or 1) - 1)
    for s in sel_text:
        m = re.match(r"SELECT\s+(" + NAME + r")\s+ASSIGN\s+TO\s+(" + NAME + ")", s["text"])
        if not m:
            continue
        g = lambda pat: (re.search(pat, s["text"]) or [None, None])[1]
        end = s["line"]
        while end < len(lines) and "." not in (code_of(lines[end - 1])[1] or ""):
            end += 1
        facts["files"].append({
            "name": m.group(1), "dd": m.group(2), "select": [s["line"], end],
            "organization": g(r"ORGANIZATION\s+(?:IS\s+)?(\w+)") or "SEQUENTIAL",
            "access": g(r"ACCESS\s+(?:MODE\s+)?(?:IS\s+)?(\w+)") or "SEQUENTIAL",
            "key": g(r"RECORD\s+KEY\s+(?:IS\s+)?(" + NAME + ")"), "status": g(r"FILE\s+STATUS\s+(?:IS\s+)?(" + NAME + ")"),
            "open": [], "ops": [],
        })
    by_name = {f["name"]: f for f in facts["files"]}

    # データ部（COPY展開しながら文を集める）
    entries, fd, section = [], None, None
    for s in statements(lines, "program", data_div or 1, (proc_div or len(lines)) - 1):
        t = s["text"]
        if re.match(r"(FILE|WORKING-STORAGE|LOCAL-STORAGE|LINKAGE)\s+SECTION", t):
            section, fd = t.split()[0], None
            continue
        m = re.match(r"(FD|SD)\s+(" + NAME + ")", t)
        if m:
            fd = m.group(2)
            if fd in by_name:
                by_name[fd]["fd"] = [s["line"], s["line"]]
            continue
        m = re.match(r"COPY\s+(" + NAME + ")", t)
        if m:
            cb = find_copybook(m.group(1), copy_dirs)
            facts["copies"].append({"name": m.group(1), "line": s["line"], "found": bool(cb), "path": str(cb) if cb else None})
            if cb:
                for cs in statements(read_lines(cb), m.group(1)):
                    e = parse_entry(cs)
                    if e:
                        entries.append(dict(e, section=section, fd=fd, copyLine=s["line"]))
            continue
        e = parse_entry(s)
        if e:
            entries.append(dict(e, section=section, fd=fd))
        elif section:
            facts["unsupported"].append({"line": s["line"], "text": t[:80]})
    for rec in records_from(entries):
        fields, groups = flatten(rec)
        facts["records"].append({
            "name": rec["name"], "section": rec.get("section"), "fd": rec.get("fd"), "line": rec["line"],
            "origin": rec["origin"], "copyLine": rec.get("copyLine"), "length": rec["size"], "fields": fields, "groups": groups,
        })
    for f in facts["files"]:
        recs = [r for r in facts["records"] if r["fd"] == f["name"]]
        if recs:
            f["fd"] = [f.get("fd", [recs[0]["line"]])[0], max(x["line"] for r in recs for x in [r] + r["fields"])]
            f["fdRecord"] = recs[0]["name"]
    rec_by = {r["name"]: r for r in facts["records"]}

    # 段落
    if proc_div:
        for no, c in text_lines[proc_div:]:
            if c and re.match(r"^ {0,3}(" + NAME + r")\.\s*$", c) and not c.startswith("    "):
                name = c.strip().rstrip(".")
                if name not in ("EXIT", "GOBACK"):
                    facts["paragraphs"].append({"name": name, "start": no})
        for i, p in enumerate(facts["paragraphs"]):
            nxt = facts["paragraphs"][i + 1]["start"] - 1 if i + 1 < len(facts["paragraphs"]) else len(lines)
            while nxt > p["start"] and not (code_of(lines[nxt - 1])[1] or "").strip():
                nxt -= 1
            p["end"] = nxt
    para_of = lambda no: next((p["name"] for p in reversed(facts["paragraphs"]) if p["start"] <= no), None)

    # 入出力文
    fd_rec_to_file = {f.get("fdRecord"): f["name"] for f in facts["files"] if f.get("fdRecord")}
    open_mode = None
    for no, c in text_lines[(proc_div or len(lines)):]:
        if not c:
            continue
        t = " ".join(c.split())
        m = re.search(r"\bOPEN\s+(INPUT|OUTPUT|I-O|EXTEND)\s+(.*)", t)
        names = []
        if m:
            open_mode, names = m.group(1), re.findall(NAME, m.group(2))
        elif open_mode and re.fullmatch(r"(" + NAME + r"\s*)+", t) and all(n in by_name for n in t.split()):
            names = t.split()
        else:
            open_mode = None if not m else open_mode
        for n in names:
            if n in by_name:
                by_name[n]["open"].append({"mode": open_mode, "line": no})
        for verb, pat in (("READ", r"\bREAD\s+(" + NAME + r")(?:\s+NEXT)?(?:\s+RECORD)?(?:\s+INTO\s+(" + NAME + "))?"),
                          ("WRITE", r"\bWRITE\s+(" + NAME + r")(?:\s+FROM\s+(" + NAME + "))?"),
                          ("REWRITE", r"\bREWRITE\s+(" + NAME + r")(?:\s+FROM\s+(" + NAME + "))?"),
                          ("DELETE", r"\bDELETE\s+(" + NAME + ")()"), ("START", r"\bSTART\s+(" + NAME + ")()"),
                          ("CLOSE", r"\bCLOSE\s+(" + NAME + ")()")):
            for m in re.finditer(pat, t):
                target = m.group(1)
                file = by_name.get(target) or by_name.get(fd_rec_to_file.get(target))
                if not file:
                    continue
                op = {"verb": verb, "line": no, "paragraph": para_of(no), "record": m.group(2) or None}
                if verb == "READ" and not op["record"]:
                    nxt = text_lines[no][1] if no < len(text_lines) else ""
                    mm = re.search(r"\bINTO\s+(" + NAME + ")", nxt or "")
                    op["record"] = mm.group(1) if mm else None
                file["ops"].append(op)
                facts["ops"].append(dict(op, file=file["name"]))
        for m in re.finditer(r"\bCALL\s+'([^']+)'", t):
            facts["calls"].append({"name": m.group(1), "line": no, "paragraph": para_of(no)})

    # ファイルごとのレイアウトとCRUD
    letter = {"READ": "R", "WRITE": "C", "REWRITE": "U", "DELETE": "D", "START": "R"}
    for f in facts["files"]:
        recs = [o["record"] for o in f["ops"] if o.get("record") in rec_by]
        f["layoutRecord"] = recs[0] if recs else f.get("fdRecord")
        lay = rec_by.get(f["layoutRecord"]) if f["layoutRecord"] else None
        f["copybook"] = lay["origin"] if lay and lay["origin"] != "program" else None
        f["length"] = lay["length"] if lay else None
        crud = "".join(sorted({letter[o["verb"]] for o in f["ops"] if o["verb"] in letter}, key="CRUD".index))
        if not crud and any(o["mode"] in ("OUTPUT", "EXTEND") for o in f["open"]):
            crud = "C"
        f["crud"] = crud or ("O" if f["open"] else "")
        # キー項目：FDのキー位置と重なるレイアウト項目
        f["keyFields"] = []
        if f.get("key") and lay:
            fdrec = rec_by.get(f.get("fdRecord"))
            kf = next((x for x in (fdrec or {}).get("fields", []) + (fdrec or {}).get("groups", []) if x["name"] == f["key"]), None)
            if kf:
                f["keyFields"] = [x["name"] for x in lay["fields"] if x["pos"][0] >= kf["pos"][0] and x["pos"][1] <= kf["pos"][1]]
    return facts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--copybooks", action="append", default=[])
    ap.add_argument("--out")
    a = ap.parse_args()
    facts = extract(a.source, a.copybooks)
    text = json.dumps(facts, ensure_ascii=False, indent=1)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
