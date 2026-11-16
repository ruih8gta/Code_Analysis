"""バッチ設計ビューワーを組み立てる。

  python -X utf8 build_viewer.py program MODEL.program.json --out CBTRN01C.html
  python -X utf8 build_viewer.py job MODEL.job.json --out daily-job.html

モデル（人とエージェントが書く業務上の意味づけ）と、ソースから機械的に抽出した事実（extract_cobol.py・extract_jcl.py）を合わせて、
単独で開けるHTMLを1つ作ります。モデルの中のパスは、モデルファイルのあるフォルダーからの相対パスです。

組み立ての前にモデルを検証し、存在しない処理ID・項目・行番号などを参照していたら、何も書き出さずに終了コード1で止まります。
--artifact は <!doctype>・<html>・<head> を付けない断片を出力します（claude.ai の Artifact として公開するとき用）。
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import extract_cobol  # noqa: E402
import extract_jcl  # noqa: E402

ASSETS = HERE.parent / "assets"
NAME = extract_cobol.NAME
ORG = {"SEQUENTIAL": "順次", "INDEXED": "索引", "RELATIVE": "相対", "LINE": "順次（行）"}
ACC = {"RANDOM": "ランダム", "SEQUENTIAL": "順次", "DYNAMIC": "動的"}
CRUD_LABEL = {"C": "作成", "R": "参照", "U": "更新", "D": "削除", "O": "開閉のみ"}


class ModelError(Exception):
    pass


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def rel(base, p):
    return (Path(base).parent / p).resolve()


def short(path):
    try:
        return str(Path(path).resolve().relative_to(Path.cwd()))
    except ValueError:
        return str(path)


# ---------- 項目の使われ方 ----------
def proc_lines(facts, lines):
    start = (facts["divisions"].get("procedure") or len(lines)) + 1
    out = []
    for no in range(start, len(lines) + 1):
        _, code = extract_cobol.code_of(lines[no - 1])
        if code:
            out.append((no, " ".join(code.upper().split())))
    return out


def ref_lines(name, plines, record=None, records_with_name=1):
    """name を参照する行。OF／IN で別レコードに修飾されている参照は除く。"""
    pat = re.compile(r"(?<![A-Z0-9-])" + re.escape(name) + r"(?![A-Z0-9-])(?:\s+(?:OF|IN)\s+(" + NAME + "))?")
    out = []
    for no, t in plines:
        for m in pat.finditer(t):
            if m.group(1) and record and m.group(1) != record:
                continue
            out.append(no)
            break
    return out


def assign_lines(name, plines):
    n = re.escape(name)
    pats = [r"\bTO\s+" + n + r"(?![A-Z0-9-])", r"\bCOMPUTE\s+" + n + r"(?![A-Z0-9-])", r"\bGIVING\s+" + n + r"(?![A-Z0-9-])",
            r"\bINITIALIZE\s+" + n + r"(?![A-Z0-9-])", r"\bINTO\s+" + n + r"(?![A-Z0-9-])"]
    out = []
    for no, t in plines:
        if re.search(r"\b(WRITE|REWRITE)\b", t):
            continue
        if any(re.search(p, t) for p in pats) or (re.search(r"\bSUBTRACT\b", t) and re.search(r"\bFROM\s+" + n + r"(?![A-Z0-9-])", t)):
            out.append(no)
    return out


def meaning(dic, name, store_name):
    if name == "FILLER":
        return f"{dic.get('filler', '予備領域')}（{store_name}）"
    return dic["names"].get(name, name)


def make_fields(store_key, store_name, record, key_fields, dic, plines=None):
    out, seen = [], {}
    for f in record["fields"]:
        n = f["name"]
        seen[n] = seen.get(n, 0) + 1
        k = f"{store_key}.{n}" + (f"-{seen[n]}" if seen[n] > 1 else "")
        x = {"key": k, "store": store_key, "name": n, "pic": f["pic"] or "", "usage": f.get("usage"), "pos": f["pos"],
             "origin": f["origin"], "line": f["line"], "meaning": meaning(dic, n, store_name), "isKey": n in key_fields}
        if plines is not None:
            x["direct"] = [] if n == "FILLER" else ref_lines(n, plines, record["name"])
            x["recLines"] = ref_lines(record["name"], plines)
            x["use"] = "個別参照" if x["direct"] else "レコード一括" if x["recLines"] else "定義のみ"
        out.append(x)
    return out


def group_items(fields, store_order):
    rank = {"個別参照": 2, "レコード一括": 1, "定義のみ": 0}
    groups = {}
    order = sorted(fields, key=lambda f: (not f["isKey"], store_order.index(f["store"]), f["pos"][0]))
    for f in order:
        groups.setdefault(f["meaning"], []).append(f)
    items = []
    for i, (name, fs) in enumerate(groups.items(), 1):
        it = {"id": f"DI-{i:02d}", "name": name, "fields": [f["key"] for f in fs], "isKey": any(f["isKey"] for f in fs),
              "pics": sorted({f["pic"] for f in fs})}
        if "use" in fs[0]:
            it["use"] = max((f["use"] for f in fs), key=lambda u: rank[u])
        for f in fs:
            f["item"] = it["id"]
        items.append(it)
    return items


# ---------- 処理フローの配置 ----------
LANE_X = {"main": 350, "left": 130, "right": 615}
LANE_W = {"main": 220, "left": 180, "right": 180}
DIM_H = {"term": 46, "pre": 52, "proc": 50, "dec": 70}
ROW_H, TOP = 86, 42


def layout_flow(flow):
    nodes = {n["id"]: n for n in flow["nodes"]}
    for n in flow["nodes"]:
        n["x"], n["y"] = LANE_X[n["lane"]], TOP + n["row"] * ROW_H
        n["w"] = LANE_W[n["lane"]] if n["type"] != "term" or n["lane"] != "main" else 190
        n["h"] = DIM_H[n["type"]]
    side = lambda n, s: {"top": [n["x"], n["y"] - n["h"] / 2], "bottom": [n["x"], n["y"] + n["h"] / 2],
                         "left": [n["x"] - n["w"] / 2, n["y"]], "right": [n["x"] + n["w"] / 2, n["y"]]}[s]
    channels, right_base = {}, LANE_X["right"] + LANE_W["right"] / 2 + 25

    def channel(target):
        if target not in channels:
            channels[target] = right_base + 22 * len(channels)
        return channels[target]

    def blocked(lane, r1, r2, skip):
        lo, hi = sorted((r1, r2))
        return any(m["lane"] == lane and lo < m["row"] < hi and m["id"] not in skip for m in flow["nodes"])

    for e in flow["edges"]:
        a, b = nodes[e["from"]], nodes[e["to"]]
        if a["lane"] == b["lane"] and b["row"] > a["row"]:
            pts = [side(a, "bottom"), side(b, "top")]
        elif a["lane"] == b["lane"]:
            pts = [side(a, "left"), [18, a["y"]], [18, b["y"]], side(b, "left")]
        elif a["row"] == b["row"]:
            pts = [side(a, "right"), side(b, "left")] if b["x"] > a["x"] else [side(a, "left"), side(b, "right")]
        elif a["lane"] == "main":
            start = side(a, "right" if b["x"] > a["x"] else "left")
            if not blocked(b["lane"], a["row"], b["row"], {a["id"], b["id"]}) and b["row"] > a["row"]:
                pts = [start, [b["x"], a["y"]], side(b, "top")]
            elif b["lane"] == "right":
                ch = channel(b["id"])
                pts = [start, [ch, a["y"]], [ch, b["y"]], side(b, "right")]
            else:
                pts = [start, [b["x"], a["y"]], side(b, "bottom" if b["row"] < a["row"] else "top")]
        elif a["lane"] == "left":
            pts = [side(a, "bottom" if b["row"] > a["row"] else "top"), [a["x"], b["y"]], side(b, "left")]
        else:
            ch = channel(b["id"])
            pts = [side(a, "right"), [ch, a["y"]], [ch, b["y"]], side(b, "right")]
        e["pts"] = pts
        if e.get("label") and "labelAt" not in e:
            (x0, y0), (x1, y1) = pts[0], pts[1]
            if x0 == x1:
                e["labelAt"] = [x0 + 8, y0 + 14, "start"]
            elif x1 > x0:
                e["labelAt"] = [x0 + 6, y0 - 8, "start"]
            else:
                e["labelAt"] = [x0 - 6, y0 - 8, "end"]
    for nt in flow.get("notes", []):
        x = LANE_X[nt["lane"]] - 85
        h = 34 + 18 * len(nt["lines"])
        nt.update({"x": x, "y": TOP + nt["row"] * ROW_H - 38, "w": 170, "h": h})
    xs = [p[0] for e in flow["edges"] for p in e["pts"]] + [n["x"] + n["w"] / 2 for n in flow["nodes"]]
    ys = [n["y"] + n["h"] / 2 for n in flow["nodes"]] + [nt["y"] + nt["h"] for nt in flow.get("notes", [])]
    flow["size"] = [max(xs) + 24, max(ys) + 24]
    return flow


# ---------- 検証 ----------
def check(cond, errors, msg):
    if not cond:
        errors.append(msg)


def check_ranges(ranges, n, errors, where):
    for r in ranges:
        check(len(r) == 2 and 1 <= r[0] <= r[1] <= n, errors, f"{where}: 行範囲 {r} が 1〜{n} の外です")


# ---------- プログラム ----------
def build_program(model_path):
    m = load(model_path)
    errors = []
    src_path = rel(model_path, m["source"])
    lines = src_path.read_text(encoding="utf-8").splitlines()
    facts = extract_cobol.extract(src_path, [rel(model_path, d) for d in m.get("copybooks", [])])
    dic = load(rel(model_path, m["dictionary"])) if m.get("dictionary") else {"names": {}}
    plines = proc_lines(facts, lines)
    rec_by = {r["name"]: r for r in facts["records"]}
    files = {f["dd"]: f for f in facts["files"]}
    copy_line = {c["name"]: c["line"] for c in facts["copies"]}

    stores, fields = [], []
    for s in m["stores"]:
        f = files.get(s["dd"])
        if not f:
            errors.append(f"stores: DD名 {s['dd']} が原本の SELECT にありません")
            continue
        rec = rec_by.get(s.get("layoutRecord") or f["layoutRecord"])
        key_fields = f["keyFields"]
        if rec and s.get("layoutRecord") and f.get("key"):
            fdrec = rec_by.get(f.get("fdRecord"))
            kf = next((x for x in (fdrec or {}).get("fields", []) + (fdrec or {}).get("groups", []) if x["name"] == f["key"]), None)
            key_fields = [x["name"] for x in rec["fields"] if kf and x["pos"][0] >= kf["pos"][0] and x["pos"][1] <= kf["pos"][1]]
        fs = make_fields(s["dd"], s["name"], rec, key_fields, dic, plines) if rec else []
        fields += fs
        cb = rec["origin"] if rec and rec["origin"] != "program" else None
        src = [f["select"]] + ([f["fd"]] if f.get("fd") else []) + ([[copy_line[cb], copy_line[cb]]] if cb in copy_line else [])
        keyname = " + ".join(dict.fromkeys(x["meaning"] for x in fs if x["isKey"]))
        keypic = " ".join(x["pic"] for x in fs if x["isKey"])
        stores.append(dict(s, org=ORG.get(f["organization"], f["organization"]), access=ACC.get(f["access"], f["access"]),
                           key=f"{keyname} {keypic}".strip() or "—", len=rec["length"] if rec else None, cb=cb or "—",
                           crud=f["crud"], src=src, record=rec["name"] if rec else None, fields=[x["key"] for x in fs],
                           ops=[o for o in f["ops"] if o["verb"] != "CLOSE"], open=f["open"]))
    order = [s["dd"] for s in stores]
    items = group_items(fields, order)
    fmap = {f["key"]: f for f in fields}
    smap = {s["dd"]: s for s in stores}

    flow = layout_flow(m["flow"])
    nids = {n["id"] for n in flow["nodes"]}
    for n in flow["nodes"]:
        check_ranges(n["lines"], len(lines), errors, f"flow.nodes[{n['id']}]")
    for e in flow["edges"]:
        check(e["from"] in nids and e["to"] in nids, errors, f"flow.edges: {e['from']}→{e['to']} の端点がありません")
    for s in stores:
        for n in s.get("nodes", []):
            check(n in nids, errors, f"stores[{s['dd']}].nodes: {n} がありません")
    eids = {f"{e['from']}>{e['to']}" for e in flow["edges"]}
    for k, p in m.get("patterns", {}).items():
        for i, st in enumerate(p["steps"]):
            check(st["node"] in nids, errors, f"patterns.{k}[{i}]: ノード {st['node']} がありません")
            check(not st.get("edge") or st["edge"] in eids, errors, f"patterns.{k}[{i}]: 線 {st.get('edge')} がありません")
    for e in m.get("errors", []):
        check(e["node"] in nids, errors, f"errors: ノード {e['node']} がありません")

    dfd = m["dfd"]
    pids = {p["id"] for p in dfd["processes"]}
    xids = {x["id"] for x in dfd["externals"]}
    for p in dfd["processes"]:
        for n in p["nodes"]:
            check(n in nids, errors, f"dfd.processes[{p['id']}]: ノード {n} がありません")
    for fl in dfd["flows"]:
        for end in (fl["from"], fl["to"]):
            t, i = end.split(":", 1)
            check((t == "P" and i in pids) or (t == "E" and i in xids) or (t == "D" and i in smap), errors, f"dfd.flows[{fl['id']}]: 端点 {end} がありません")
        expanded = []
        for k in fl.get("items", []):
            if k.endswith(".*"):
                expanded += smap.get(k[:-2], {}).get("fields", [])
            else:
                check(k in fmap, errors, f"dfd.flows[{fl['id']}]: 項目 {k} がありません")
                expanded.append(k)
        fl["items"] = expanded
        check_ranges(fl.get("lines", []), len(lines), errors, f"dfd.flows[{fl['id']}]")
    for dd in dfd["stores"]:
        check(dd in smap, errors, f"dfd.stores: {dd} がありません")
    if errors:
        raise ModelError("\n".join(errors))

    return {
        "kind": "program", "schema": m.get("$schema"),
        "meta": {"program": m["program"], "title": m["title"], "type": m.get("type", "BATCH COBOL"), "lines": len(lines),
                 "source": short(src_path), "sha256": hashlib.sha256(src_path.read_bytes()).hexdigest()},
        "links": m.get("links", {}), "source": lines,
        "paragraphs": facts["paragraphs"], "procedureLine": facts["divisions"]["procedure"],
        "overview": m["overview"], "context": m["context"], "stores": stores, "fields": fmap, "items": items,
        "flow": flow, "dfd": dfd, "errors": m.get("errors", []), "patterns": m.get("patterns", {}),
        "workArea": m.get("workArea", {}), "openItems": m.get("openItems", []),
    }


# ---------- ジョブ ----------
def build_job(model_path):
    m = load(model_path)
    errors, sources = [], {}
    dic = load(rel(model_path, m["dictionary"])) if m.get("dictionary") else {"names": {}}
    cdirs = [rel(model_path, d) for d in m.get("copybooks", [])]
    jcl = extract_jcl.parse_job
    jobs = {}
    for p in m.get("jcl", []):
        path = rel(model_path, p)
        j = jcl(path, [rel(model_path, d) for d in m.get("procs", [])])
        sid = "jcl:" + j["name"]
        sources[sid] = {"path": short(path), "kind": "jcl", "lines": j.pop("lines")}
        for st in j["steps"]:
            if st.get("procFile"):
                pid = "proc:" + st["proc"]
                if pid not in sources:
                    sources[pid] = {"path": short(st["procFile"]), "kind": "jcl", "lines": Path(st["procFile"]).read_text(encoding="utf-8").splitlines()}
        jobs[j["name"]] = dict(j, src=sid)
    progs = {}
    for name, p in m.get("programs", {}).items():
        path = rel(model_path, p["source"])
        lines = path.read_text(encoding="utf-8").splitlines()
        facts = extract_cobol.extract(path, cdirs)
        sources["cbl:" + name] = {"path": short(path), "kind": "cobol", "lines": lines}
        progs[name] = {"facts": facts, "plines": proc_lines(facts, lines), "viewer": p.get("viewer"), "lines": len(lines),
                       "recs": {r["name"]: r for r in facts["records"]}}

    datasets = m.get("datasets", {})
    stores, smap, steps = [], {}, []

    def store_for(dsn, lrecl=None):
        if dsn not in smap:
            d = datasets.get(dsn, {})
            s = {"id": dsn, "no": f"D{len(stores) + 1}", "name": d.get("name", dsn.split(".")[-2] if "." in dsn else dsn),
                 "desc": d.get("desc", ""), "kind": d.get("kind", ""), "lrecl": lrecl, "gdg": False, "layout": None,
                 "crudBy": {}, "dds": []}
            stores.append(s)
            smap[dsn] = s
        if lrecl and not smap[dsn]["lrecl"]:
            smap[dsn]["lrecl"] = lrecl
        return smap[dsn]

    for i, st in enumerate(m["steps"]):
        step = {"id": st["id"], "no": st["id"], "title": st["title"], "desc": st.get("desc", ""), "assumed": bool(st.get("assumed")),
                "note": st.get("note", ""), "job": st.get("job"), "step": st.get("step"), "procStep": st.get("procStep"),
                "program": st.get("program"), "dds": [], "warnings": []}
        jdds, jline, jend = [], None, None
        if st.get("job"):
            j = jobs.get(st["job"])
            if not j:
                errors.append(f"steps[{st['id']}]: JCL {st['job']} がありません")
                continue
            cands = [x for x in j["steps"] if x["name"] == st["step"]]
            occ = st.get("occurrence", 1)
            if len(cands) < occ:
                errors.append(f"steps[{st['id']}]: {st['job']} にステップ {st['step']}（{occ}番目）がありません")
                continue
            js = cands[occ - 1]
            if len(cands) > 1:
                step["warnings"].append(f"{st['job']} にステップ名 {st['step']} が{len(cands)}回あります（{occ}番目）")
            idx = j["steps"].index(js)
            jline = js["line"]
            jend = (j["steps"][idx + 1]["line"] - 1) if idx + 1 < len(j["steps"]) else len(sources[j["src"]]["lines"])
            step.update(src=j["src"], jcl=[jline, jend], pgm=js["pgm"] or js["proc"], proc=js["proc"])
            if js.get("proc"):
                ps = next((x for x in js["procSteps"] if x["name"] == st.get("procStep")), js["procSteps"][0] if js["procSteps"] else None)
                jdds = ps["dds"] if ps else []
                step["pgm"] = ps["pgm"] if ps else js["proc"]
                step["procSrc"] = "proc:" + js["proc"]
            else:
                jdds = js["dds"]
        else:
            step.update(src=None, jcl=None, pgm=st.get("program"))
            jdds = [{"dd": dd, "dsn": dsn, "line": None, "end": None, "disp": None, "generation": None, "assumed": True, "lrecl": None}
                    for dd, dsn in st.get("ddMap", {}).items()]
        prog = progs.get(st.get("program")) if st.get("program") else None
        files = {f["dd"]: f for f in prog["facts"]["files"]} if prog else {}
        util = st.get("utility", {})
        for d in jdds:
            if not d.get("dsn") or d.get("instream") or d["dd"] in ("STEPLIB", "JOBLIB", "SYSIN") or d.get("dsn") == "NULLFILE":
                continue
            f = files.get(d["dd"])
            if prog and not f:
                step["warnings"].append(f"DD {d['dd']}（{d['dsn']}）はプログラムの SELECT にありません")
                continue
            crud = f["crud"] if f else util.get(d["dd"], "")
            if not prog and d["dd"] not in util:
                step["warnings"].append(f"DD {d['dd']} の入出力はモデルで指定されていません")
            s = store_for(d["dsn"], d.get("lrecl") or (f or {}).get("length"))
            s["gdg"] = s["gdg"] or bool(d.get("generation"))
            s["crudBy"][step["id"]] = "".join(sorted(set(s["crudBy"].get(step["id"], "") + crud), key="CRUDO".index))
            if f and f.get("layoutRecord"):
                rec = prog["recs"].get(f["layoutRecord"])
                weak = lambda lay: lay is None or lay.get("fdOnly")
                if rec and weak(s["layout"]) and not (rec.get("fd") and s["layout"]):
                    s["layout"] = {"program": st["program"], "record": rec["name"], "origin": rec["origin"], "length": rec["length"],
                                   "keyFields": f["keyFields"], "fdOnly": bool(rec.get("fd"))}
            if f and s["kind"] == "":
                s["kind"] = ORG.get(f["organization"], f["organization"])
            ent = {"dd": d["dd"], "dsn": d["dsn"], "store": s["id"], "crud": crud, "disp": d.get("disp"), "generation": d.get("generation"),
                   "line": d.get("line"), "end": d.get("end"), "assumed": bool(d.get("assumed")), "override": bool(d.get("override")),
                   "ops": [o for o in (f or {}).get("ops", []) if o["verb"] != "CLOSE"], "open": (f or {}).get("open", []),
                   "select": (f or {}).get("select")}
            step["dds"].append(ent)
            s["dds"].append({"step": step["id"], **{k: ent[k] for k in ("dd", "crud", "line", "end", "assumed", "generation", "disp")}})
        if prog:
            used = {d["dd"] for d in step["dds"]}
            for f in prog["facts"]["files"]:
                if f["dd"] not in used:
                    step["warnings"].append(f"プログラムの {f['dd']} に対応する DD がありません")
            step["facts"] = {"paragraphs": len(prog["facts"]["paragraphs"]), "lines": prog["lines"],
                             "calls": sorted({c["name"] for c in prog["facts"]["calls"]})}
            step["viewer"] = prog["viewer"]
            step["programSrc"] = "cbl:" + st["program"]
        step["util"] = st.get("utilityNote")
        steps.append(step)

    # レイアウト（モデルでレコード名を指定するか、他のデータセットと同じレイアウトを指定できる）
    for s in stores:
        want = datasets.get(s["id"], {}).get("layoutRecord")
        if want:
            hit = next(((n, p["recs"][want]) for n, p in progs.items() if want in p["recs"]), None)
            if not hit:
                errors.append(f"datasets[{s['id']}].layoutRecord: {want} がどのプログラムにもありません")
                continue
            n, rec = hit
            files = progs[n]["facts"]["files"]
            ff = next((f for f in files if f.get("layoutRecord") == want or f.get("fdRecord") and progs[n]["recs"][f["fdRecord"]]["length"] == rec["length"]), None)
            key = []
            if ff and ff.get("key"):
                fdrec = progs[n]["recs"].get(ff.get("fdRecord"))
                kf = next((x for x in (fdrec or {}).get("fields", []) + (fdrec or {}).get("groups", []) if x["name"] == ff["key"]), None)
                key = [x["name"] for x in rec["fields"] if kf and x["pos"][0] >= kf["pos"][0] and x["pos"][1] <= kf["pos"][1]]
            s["layout"] = {"program": n, "record": want, "origin": rec["origin"], "length": rec["length"], "keyFields": key}
    if errors:
        raise ModelError("\n".join(errors))
    for s in stores:
        lf = datasets.get(s["id"], {}).get("layoutFrom")
        if lf and smap.get(lf) and smap[lf]["layout"]:
            s["layout"] = dict(smap[lf]["layout"], inherited=lf)
    fields = []
    for s in stores:
        lay = s["layout"]
        if not lay:
            continue
        rec = progs[lay["program"]]["recs"][lay["record"]]
        fs = make_fields(s["no"], s["name"], rec, lay.get("keyFields", []), dic)
        s["fields"] = [f["key"] for f in fs]
        for f in fs:
            f["dsn"] = s["id"]
        fields += fs
        s["lrecl"] = s["lrecl"] or lay["length"]
    items = group_items(fields, [s["no"] for s in stores])
    fmap = {f["key"]: f for f in fields}

    # 項目単位のCRUD（推定：名前の参照と代入先から判定）
    item_crud = {}
    for step in steps:
        prog = progs.get(step.get("program"))
        for d in step["dds"]:
            s = smap[d["store"]]
            for fk in s.get("fields", []):
                f = fmap[fk]
                letters, ev = set(), {}
                if prog:
                    rec_name = s["layout"]["record"] if s["layout"] and s["layout"]["program"] == step["program"] else None
                    refs = [] if f["name"] == "FILLER" else ref_lines(f["name"], prog["plines"], rec_name)
                    asg = [] if f["name"] == "FILLER" else assign_lines(f["name"], prog["plines"])
                    if "C" in d["crud"]:
                        letters.add("C")
                    if "U" in d["crud"] and asg:
                        letters.add("U")
                        ev["U"] = asg
                    if "R" in d["crud"] and refs:
                        letters.add("R")
                        ev["R"] = refs
                    if "D" in d["crud"]:
                        letters.add("D")
                else:
                    letters = set(d["crud"]) - {"O"}
                if letters:
                    cell = item_crud.setdefault(f["item"], {}).setdefault(step["id"], {"crud": "", "fields": [], "ev": {}})
                    cell["crud"] = "".join(sorted(set(cell["crud"]) | letters, key="CRUD".index))
                    cell["fields"].append(fk)
                    for k, v in ev.items():
                        cell["ev"][k] = sorted(set(cell["ev"].get(k, []) + v))

    # ジョブ全体のDFD（自動配置）
    sx = {st["id"]: 150 + i * 240 for i, st in enumerate(steps)}
    top, bottom = [], []
    for s in stores:
        letters = "".join(s["crudBy"].values())
        (bottom if re.search("[CUD]", letters) else top).append(s)
    W = 176

    def place(row, y):
        for s in row:
            xs = [sx[k] for k in s["crudBy"]]
            s["x"] = sum(xs) / len(xs) if xs else 150
        row.sort(key=lambda s: s["x"])
        last = -1e9
        for s in row:
            s["x"] = max(s["x"], last + W + 18, W / 2 + 10)
            last = s["x"]
            s["y"] = y
    place(top, 60)
    place(bottom, 540)
    flows = []
    for step in steps:
        for s in stores:
            c = s["crudBy"].get(step["id"], "")
            r, w = "R" in c, re.sub("[RO]", "", c)
            both = r and w
            if r:
                flows.append({"id": f"F{len(flows) + 1}", "from": f"D:{s['id']}", "to": f"S:{step['id']}", "crud": "R", "offset": -5 if both else 0})
            if w:
                flows.append({"id": f"F{len(flows) + 1}", "from": f"S:{step['id']}", "to": f"D:{s['id']}", "crud": w, "offset": 5 if both else 0})
            if c == "O":
                flows.append({"id": f"F{len(flows) + 1}", "from": f"D:{s['id']}", "to": f"S:{step['id']}", "crud": "O", "offset": 0, "dash": True})
    width = max([sx[s["id"]] for s in steps] + [s["x"] for s in stores]) + W / 2 + 20
    dfd = {"width": width, "height": 600, "steps": {k: [v, 300] for k, v in sx.items()},
           "stores": {s["id"]: [s["x"], s["y"]] for s in stores}, "flows": flows}

    # 自動チェック
    checks = []
    for step in steps:
        if step["assumed"]:
            checks.append({"level": "warn", "target": "S:" + step["id"], "text": f"{step['id']} {step['title']}：JCLが無く、ジョブへの組み込みと DD の割り当ては仮定です。"})
        for w in step["warnings"]:
            checks.append({"level": "warn", "target": "S:" + step["id"], "text": f"{step['id']}：{w}"})
        if step.get("util"):
            checks.append({"level": "warn", "target": "S:" + step["id"], "text": f"{step['id']}：{step['util']}"})
    for s in stores:
        letters = "".join(s["crudBy"].values())
        if not s["layout"]:
            checks.append({"level": "none", "target": "D:" + s["id"], "text": f"{s['no']} {s['name']}：レコードレイアウトが分かりません。"})
        if re.search("[CU]", letters) and "R" not in letters:
            checks.append({"level": "none", "target": "D:" + s["id"], "text": f"{s['no']} {s['name']}：このジョブでは作成・更新するだけで、読むステップがありません（ジョブの外で使う出力）。"})
        if not re.search("[CUD]", letters):
            checks.append({"level": "none", "target": "D:" + s["id"], "text": f"{s['no']} {s['name']}：このジョブでは読むだけです（ジョブの外で作られる入力）。"})
    if errors:
        raise ModelError("\n".join(errors))
    return {"kind": "job", "schema": m.get("$schema"), "meta": {"id": m["id"], "title": m["title"]}, "overview": m.get("overview", {}),
            "jobs": [{"name": j["name"], "src": j["src"], "line": j["line"], "steps": [s["id"] for s in steps if s.get("job") == j["name"]]} for j in jobs.values()],
            "steps": steps, "stores": stores, "fields": fmap, "items": items, "itemCrud": item_crud, "dfd": dfd, "checks": checks,
            "openItems": m.get("openItems", []), "sources": sources}


# ---------- HTMLへの埋め込み ----------
def render(view, template, artifact):
    page = (ASSETS / template).read_text(encoding="utf-8")
    page = page.replace("/*@CORE_CSS@*/", (ASSETS / "core.css").read_text(encoding="utf-8"))
    page = page.replace("/*@CORE_JS@*/", (ASSETS / "core.js").read_text(encoding="utf-8"))
    data = json.dumps(view, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = page.replace('"@VIEW@"', data)
    title = view["meta"].get("program") or view["meta"]["title"]
    page = page.replace("@TITLE@", f"{title} バッチ設計" if view["kind"] == "program" else view["meta"]["title"])
    if artifact:
        return page
    return f'<!doctype html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n</head>\n<body>\n{page}\n</body>\n</html>\n'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=["program", "job"])
    ap.add_argument("model")
    ap.add_argument("--out", required=True)
    ap.add_argument("--artifact", action="store_true")
    ap.add_argument("--dump", help="組み立てたデータをJSONでも書き出す（確認用）")
    a = ap.parse_args()
    try:
        view = build_program(a.model) if a.kind == "program" else build_job(a.model)
    except ModelError as e:
        print("モデルの検証で止まりました:\n" + str(e), file=sys.stderr)
        sys.exit(1)
    html = render(view, "program-viewer.html" if a.kind == "program" else "job-viewer.html", a.artifact)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(html, encoding="utf-8")
    if a.dump:
        Path(a.dump).write_text(json.dumps(view, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{a.out} を書き出しました（{len(html.encode('utf-8')) // 1024} KB）")


if __name__ == "__main__":
    main()
