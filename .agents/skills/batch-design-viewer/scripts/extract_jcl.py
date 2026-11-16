"""JCL（とカタログ式プロシージャ）から、ジョブ・ステップ・DD の事実を抽出する。

使い方:
  python -X utf8 extract_jcl.py JOB1.jcl [JOB2.jcl ...] --procs DIR --out jcl.json

扱う文: JOB、EXEC（PGM= と PROC=／プロシージャ名）、DD（DSN、DISP、SYSOUT、DCB の LRECL、* の入力データ）、PROC／PEND。
EXEC PROC は --procs のフォルダーからプロシージャを読み、DD の上書き（STEP.DD）を反映します。
記号パラメーター（&NAME）は置き換えずにそのまま残します。
"""
import argparse
import json
import re
from pathlib import Path


def logical_statements(lines):
    """継続行をまとめて (開始行, 名前, 操作, オペランド) を返す。インストリームの行は data に入れる。"""
    out, i = [], 0
    while i < len(lines):
        raw = lines[i].rstrip()
        no = i + 1
        i += 1
        if raw.startswith("//*") or not raw.startswith("//"):
            if out and out[-1]["op"] == "DD" and out[-1].get("instream") and not raw.startswith("//") and raw != "/*":
                out[-1]["data"].append({"line": no, "text": raw})
            continue
        body = raw[2:72]
        m = re.match(r"(\S*)\s+(\S+)\s*(.*)", body)
        if not m:
            continue
        name, op, operands = m.group(1), m.group(2), m.group(3)
        operands = re.split(r"\s{2,}|\s(?=//)", operands.strip())[0] if operands else ""
        end = no
        while operands.endswith(",") and i < len(lines) and lines[i].startswith("//") and not lines[i].startswith("//*"):
            cont = lines[i][2:72].strip()
            operands += cont.split()[0] if cont else ""
            end = i + 1
            i += 1
        st = {"line": no, "end": end, "name": name, "op": op, "operands": operands, "data": []}
        st["instream"] = op == "DD" and (operands.startswith("*") or operands.startswith("DATA"))
        out.append(st)
    return out


def params(operands):
    """カンマ区切りのキーワード引数を辞書にする（括弧の中のカンマは区切らない）。"""
    res, depth, cur, pos = {}, 0, "", []
    for ch in operands + ",":
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            pos.append(cur)
            cur = ""
        else:
            cur += ch
    for p in pos:
        if "=" in p:
            k, v = p.split("=", 1)
            res[k.upper()] = v
        elif p:
            res.setdefault("_pos", []).append(p)
    return res


def dd_info(st):
    p = params(st["operands"])
    dsn = p.get("DSN") or p.get("DSNAME")
    gen = None
    if dsn:
        m = re.match(r"(.+?)\(([+-]?\d+)\)$", dsn)
        if m:
            dsn, gen = m.group(1), m.group(2)
        else:
            m = re.match(r"(.+?)\((\w+)\)$", dsn)
            if m:
                dsn, gen = m.group(1), None
                p["MEMBER"] = m.group(2)
    lrecl = re.search(r"LRECL=(\d+)", st["operands"])
    return {
        "dd": st["name"], "line": st["line"], "end": st["end"], "dsn": dsn, "generation": gen, "member": p.get("MEMBER"),
        "disp": p.get("DISP"), "sysout": p.get("SYSOUT"), "lrecl": int(lrecl.group(1)) if lrecl else None,
        "instream": st["instream"], "data": st["data"], "dcbRef": "DCB=(*." in st["operands"],
    }


def parse_proc(path):
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    steps, cur = [], None
    for st in logical_statements(lines):
        if st["op"] == "EXEC":
            p = params(st["operands"])
            cur = {"name": st["name"], "pgm": p.get("PGM"), "line": st["line"], "dds": []}
            steps.append(cur)
        elif st["op"] == "DD" and cur is not None and st["name"]:
            cur["dds"].append(dd_info(st))
    return {"file": str(path), "lines": lines, "steps": steps}


def parse_job(path, proc_dirs):
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    job = {"file": str(path), "name": None, "line": None, "lines": lines, "steps": []}
    cur = None
    for st in logical_statements(lines):
        if st["op"] == "JOB":
            job["name"], job["line"] = st["name"], st["line"]
        elif st["op"] == "EXEC":
            p = params(st["operands"])
            proc = p.get("PROC") or (p.get("_pos") or [None])[0]
            cur = {"name": st["name"], "line": st["line"], "pgm": p.get("PGM"), "proc": None if p.get("PGM") else proc,
                   "params": {k: v for k, v in p.items() if k not in ("PGM", "PROC", "_pos")}, "dds": []}
            if cur["proc"]:
                pf = next((Path(d) / f"{cur['proc']}{ext}" for d in proc_dirs for ext in (".prc", ".PRC", ".proc", "")
                           if (Path(d) / f"{cur['proc']}{ext}").exists()), None)
                cur["procFile"] = str(pf) if pf else None
                cur["procSteps"] = parse_proc(pf)["steps"] if pf else []
            job["steps"].append(cur)
        elif st["op"] == "DD" and cur is not None and st["name"]:
            info = dd_info(st)
            if "." in info["dd"] and cur.get("procSteps") is not None:
                pstep, dd = info["dd"].split(".", 1)
                for ps in cur["procSteps"]:
                    if ps["name"] == pstep:
                        ps["dds"] = [x for x in ps["dds"] if x["dd"] != dd] + [dict(info, dd=dd, override=True)]
            else:
                cur["dds"].append(info)
    return job


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jcl", nargs="+")
    ap.add_argument("--procs", action="append", default=[])
    ap.add_argument("--out")
    a = ap.parse_args()
    res = {"jobs": [parse_job(j, a.procs) for j in a.jcl]}
    text = json.dumps(res, ensure_ascii=False, indent=1)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
