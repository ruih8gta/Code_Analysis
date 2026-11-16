"""Verify the CardDemo viewer and optionally embed reproducible execution evidence.

Run with Python 3 and Node.js. Java 17+ is required. --jdk can select a JDK.
This checks this example's model and output. It does not execute COBOL.
"""
import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = {}
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.current = dict(attrs).get("id", "app")
            self.parts[self.current] = ""

    def handle_data(self, text):
        if self.current:
            self.parts[self.current] += text

    def handle_endtag(self, tag):
        if tag == "script":
            self.current = None


def run(command, **options):
    return subprocess.run([str(part) for part in command], capture_output=True, **options)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--update", action="store_true", help="Embed the result in viewer.html")
    cli.add_argument("--jdk", type=Path, help="JDK home directory")
    args = cli.parse_args()
    root = Path(__file__).resolve().parents[1]
    html_path = root / "viewer.html"
    html = html_path.read_text(encoding="utf-8")
    scripts = Scripts()
    scripts.feed(html)
    data = json.loads(scripts.parts["project-data"])
    review = json.loads(scripts.parts["review-data"])
    assert review == json.loads((root / 'review/review-model.json').read_text(encoding='utf-8')), 'Embedded review ledger differs'
    for language, name in (("cobol", "original/CBTRN01C.cbl"), ("java", "DailyTransactionLookup.java")):
        assert data["sources"][language].encode() == (root / name).read_bytes(), name + " differs from embedded source"
        assert review['basis'][language] == sha256(data['sources'][language].encode()).hexdigest(), 'Source review is stale'
    conversion = json.loads(scripts.parts['conversion-data'])
    assert conversion == json.loads((root / 'review/conversion-map.json').read_text(encoding='utf-8')), 'Embedded conversion ledger differs'
    assert conversion['basis'] == review['basis'], 'Conversion ledger is stale'
    for language in ('cobol', 'java'):
        total = len(data['sources'][language].splitlines())
        assert len(conversion['lines'][language]) == total == sum(conversion['counts'][language].values()), 'Every line needs one conversion kind'
    assert all(len(row['units']) <= 1 for row in conversion['lines']['cobol']), 'A COBOL line belongs to one conversion unit'
    assert {i for u in conversion['units'] for i in u['reviewIds']} <= {c['id'] for c in review['comparisons']}
    assert len({m['id'] for m in review['mappings']}) == len(review['mappings'])
    assert len({c['id'] for c in review['comparisons']}) == len(review['comparisons'])
    mapping_ids = {m['id'] for m in review['mappings']}
    behavior_ids = {c['id'] for c in review['comparisons']}
    for item in review['comparisons'] + review['mappings']:
        assert item['disposition'] == 'unreviewed', 'This sample has no recorded user approval'
        for language, key in [('cobol','oldRanges'),('java','newRanges')]:
            for start, end in item[key]:
                assert 1 <= start <= end <= len(data['sources'][language].splitlines()), (item['id'],key,start,end)
    for item in review['comparisons']:
        assert set(item['mappingIds']) <= mapping_ids
    for item in review['mappings']:
        assert set(item['behaviorIds']) <= behavior_ids
        for bid in item['behaviorIds']:
            assert item['id'] in next(c for c in review['comparisons'] if c['id']==bid)['mappingIds']
    assert len([m for m in review['mappings'] if m['category']=='field']) == 71
    assert len([m for m in review['mappings'] if m['category']=='variable']) == 37
    assert len([m for m in review['mappings'] if m['category']=='resource']) == 6
    syntax = run(["node", "--check", "-"], input=scripts.parts["app"].encode())
    assert syntax.returncode == 0, syntax.stderr.decode()

    app = scripts.parts["app"]
    component=(root/'scripts/source_coverage.js').read_text(encoding='utf-8').rstrip()
    embedded=app.split('// BEGIN SOURCE COVERAGE COMPONENT\n',1)[1].split('\n// END SOURCE COVERAGE COMPONENT',1)[0]
    assert embedded==component, 'Run sync_source_coverage.py before verification'
    core = app.split("const cobolWords")[0]
    inspector = "function conditionFor(step)" + app.split("function conditionFor(step)", 1)[1].split("function changeDetail(", 1)[0]
    audit = "function buildAudit()" + app.split("function buildAudit()", 1)[1].split("function renderAudit()", 1)[0]
    # DOM stubs only collect text from the real inspector renderer. Browser QA checks actual interactions.
    mock = """
class Item {
 constructor(tag) { this.tag=tag; this.textContent=""; this.children=[]; }
 append(...items) { this.children.push(...items); }
 replaceChildren(...items) { this.children=items; }
 addEventListener() {}
}
const panel=new Item("div");
const document={
 createElement:tag=>new Item(tag),
 getElementById:id=>id==="inspector"?panel:{textContent:payload[id]}
};
"""
    query = """
const results={};
const edgeNames=new Set(connections.map(([a,b])=>a+"-"+b));
for(const [id,trace] of Object.entries(traces)){
 const logs=[];
 trace.forEach((step,i)=>{
   if(i&&!edgeNames.has(trace[i-1].block+"-"+step.block))throw Error("Missing graph connection");
   for(const language of ["cobol","java"]){
     const lines=data.sources[language].trimEnd().split(/\\r?\\n/);
     for(const [,start,end] of sourceRanges(step,language)){
       if(!(start>0&&end>=start&&end<=lines.length))throw Error("Invalid source mapping");
     }
   }
   renderInspector(step);
   for(const child of panel.children)if(child.tag==="pre")logs.push(child.textContent);
 });
 results[id]={logs,steps:trace.length};
}
console.log(JSON.stringify({results,
 paragraphs:audit.paragraphs.map(p=>({line:p.start,status:p.status,registered:p.registered,total:p.lines.length})),
 decisions:audit.decisions.map(d=>({line:d.start,status:d.status})),
 edges:audit.usedEdges.size,definedEdges:connections.length,coverage:sourceCoverage}));
"""
    program = "const payload=" + json.dumps(scripts.parts) + ";\n" + mock + core + inspector + audit + query
    model = run(["node", "-"], input=program.encode())
    assert model.returncode == 0, model.stderr.decode()
    inspected = json.loads(model.stdout)
    assert len(inspected["paragraphs"]) == 18
    assert len(inspected["decisions"]) == 36
    assert sum(p["registered"] > 0 for p in inspected["paragraphs"]) == 7
    assert inspected["edges"] == inspected["definedEdges"] == 15
    assert next(p for p in inspected["paragraphs"] if p["line"] == 271)["registered"] == 0
    assert next(p for p in inspected["paragraphs"] if p["line"] == 476)["registered"] == 0
    assert next(d for d in inspected["decisions"] if d["line"] == 477)["status"] == "gap"
    coverage=inspected['coverage']
    assert [row['number'] for row in coverage['lines']] == list(range(1,495)), 'Every physical source line must appear once'
    assert [n for span in coverage['ranges'] for n in range(span['start'],span['end']+1)] == list(range(1,495)), 'Source ranges contain a gap or overlap'
    assert not coverage['issues'], coverage['issues']
    assert coverage['counts']['unknown']==0, 'Pinned sample contains an unclassified line'
    assert sum(coverage['counts'][k] for k in ['required','definitions','neutral'])==494
    assert coverage['lines'][0]['kind']=='comment' and not coverage['lines'][0]['requiresFlow']
    assert coverage['lines'][98]['kind']=='definition' and coverage['lines'][98]['ioRefs']==['DALYTRAN']
    assert not coverage['lines'][272]['flowIds'] and coverage['lines'][272]['ioRefs']==['CUSTFILE']
    assert any(c['line']==173 and c['branch']=='偽' for c in coverage['lines'][180]['conditions']), 'ELSE must link to the original false branch'
    assert any(c['line']==167 and c['branch']=='真' for c in coverage['lines'][167]['conditions'])
    assert coverage['lines'][172]['flowIds'] and coverage['lines'][172]['missing'], 'An unbound outer condition must keep its inner source range unresolved'
    assert 'CUSTFILE' in coverage['lines'][372]['ioRefs'], 'Do not rewrite the original DALYTRAN close diagnostic reference'
    decision_lines={d['line'] for d in inspected['decisions']}
    for row in coverage['lines']:
        assert {c['line'] for c in row['conditions']} <= decision_lines
        assert set(row['fieldIds']) <= mapping_ids
        assert set(row['ioRefs']) <= set(json.loads(scripts.parts['layouts'])) | {'SYSOUT'}

    java = args.jdk / "bin/java.exe" if args.jdk else shutil.which("java")
    javac = args.jdk / "bin/javac.exe" if args.jdk else shutil.which("javac")
    if not java or not javac:
        cli.error("Use --jdk to select an installed JDK.")
    version = run([java, "-version"], text=True, encoding="utf-8").stderr.splitlines()[0]
    checks = []
    names = dict(sample="同梱3件", success="照合成功", noCard="カード未登録", noAccount="口座未登録", empty="空入力")
    with tempfile.TemporaryDirectory(dir=root, prefix=".coverage-verify-") as folder:
        work = Path(folder).resolve()
        assert work.parent == root.resolve() and work.name.startswith(".coverage-verify-")
        classes = work / "classes"
        classes.mkdir()
        compiled = run([javac, "--release", "17", "-encoding", "UTF-8", "-d", classes, root / "DailyTransactionLookup.java"])
        assert compiled.returncode == 0, compiled.stderr.decode()
        base = [java, "-cp", classes, "DailyTransactionLookup"]
        daily = data["sampleRecords"]["DALYTRAN"]
        cases = dict(sample=daily, success=daily[:1], noCard=daily[1:2], noAccount=daily[2:], empty=[])
        for name, records in cases.items():
            directory = work / name
            shutil.copytree(root / "sample", directory)
            (directory / "dailytran.txt").write_bytes(("\n".join(records) + ("\n" if records else "")).encode("ascii"))
            result = run(base + [directory])
            actual = result.stdout.decode("ascii").splitlines()
            expected = "\n".join(inspected["results"][name]["logs"]).splitlines()
            assert result.returncode == 0 and not result.stderr, (name, result.stderr)
            assert actual == expected, (name, actual, expected)
            checks.append(dict(id=name, label=names[name], passed=True, observations=str(len(actual))+"行一致", lines=len(actual)))
        usage = run(base)
        assert usage.returncode == 2 and b"Usage:" in usage.stderr
        checks.append(dict(id="arguments", label="引数不足", passed=True, observations="終了コード2"))
        for check_id, filename, row, expected_error in (
            ("duplicate-card", "cardxref.txt", data["sampleRecords"]["XREFFILE"][0], "duplicate card"),
            ("duplicate-account", "acctdata.txt", data["sampleRecords"]["ACCTFILE"][0], "duplicate account"),
            ("record-width", "dailytran.txt", "0"*277, "dailytran.txt line 1")):
            directory = work / check_id
            shutil.copytree(root / "sample", directory)
            content = row+"\n" if check_id=="record-width" else row+"\n"+row+"\n"
            (directory / filename).write_bytes(content.encode("ascii"))
            result = run(base + [directory])
            assert result.returncode == 1 and expected_error.encode() in result.stderr
            checks.append(dict(id=check_id, label={"duplicate-card":"カード番号の重複","duplicate-account":"口座IDの重複","record-width":"レコード長の異常"}[check_id], passed=True, observations="終了コード1"))

    content = dict(cobol=data["sources"]["cobol"], java=data["sources"]["java"], app=app,
        sample=json.dumps([data["transactions"],data["references"],data["accounts"],data["sampleRecords"]], ensure_ascii=False, separators=(",",":")),
        review=scripts.parts['review-data'],layouts=scripts.parts['layouts'],conversion=scripts.parts['conversion-data'])
    evidence = dict(checkedAt=datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M JST"),
        javaVersion=version, hashes={key:sha256(value.encode()).hexdigest() for key,value in content.items()}, checks=checks)
    if args.update:
        coverage_report=dict(source=review['scope']['old'],sha256=review['basis']['cobol'],
            limitation='Source classification and registered links; not semantic completeness or COBOL runtime coverage.',**coverage)
        (root/'review/source-coverage.json').write_text(json.dumps(coverage_report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        updated, count = re.subn(r'(<script id="verification-data" type="application/json">).*?(</script>)',
            lambda m: m[1]+json.dumps(evidence,ensure_ascii=True,separators=(",",":")).replace("<",r"\u003c")+m[2], html, count=1, flags=re.S)
        assert count == 1
        html_path.write_bytes(updated.encode("utf-8"))
    print("COBOL: 18 paragraphs, 36 decisions; mapped lines in 7 paragraphs; modeled edges 15/15.")
    print('Review ledger: 10 behavior items; 71 record fields, 37 variables and 6 file interfaces. Links and source versions checked.')
    print(f"Conversion ledger: {len(conversion['units'])} units; every COBOL and Java line classified.")
    print('Source-order coverage: '+json.dumps(coverage['counts'])+'; all 494 lines partitioned with no gaps or overlaps.')
    for check in checks:
        print(check["label"]+": "+check["observations"])
    print("COBOL execution comparison and runtime branch instrumentation: not performed.")
    print("Verification evidence embedded." if args.update else "Verification complete. Use --update to save evidence.")


if __name__ == "__main__":
    main()

