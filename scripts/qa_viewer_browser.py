"""Exercise the local viewer in an installed Chromium browser without external services."""
import argparse
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import subprocess
import tempfile
import threading


QA = r"""
<script type="text/javascript">
(async () => {
  const checks = [];
  const ok = (value, name) => { if (!value) throw Error(name); checks.push(name); };
  const click = (selector) => document.querySelector(selector).click();
  const select = (id, value) => { $(id).value = value; $(id).dispatchEvent(new Event('change', {bubbles:true})); };
  try {
    for (let i=0; i<200 && evidenceState==='checking'; i++) await new Promise(r=>setTimeout(r,20));
    ok(evidenceState==='valid', 'Evidence hashes match current source, model and inputs');
    ok(reviewStage==='overview' && !$('review-overview').hidden, 'Overview opens first');
    ok(document.querySelector('.workspace').hidden, 'Overview shows review workflow without code clutter');
    ok(document.querySelectorAll('.cv-map .cv-unit').length===conversion.units.length, 'Overview draws every conversion unit');
    [...document.querySelectorAll('.cv-unit')].find(g=>g.getAttribute('aria-label').startsWith('6ファイルを閉じる')).dispatchEvent(new MouseEvent('click',{bubbles:true}));
    ok(reviewStage==='convert' && conversionSelected.id==='close' && panes.cobol.rows[360].classList.contains('selected') && panes.java.rows[54].classList.contains('selected'), 'A ribbon opens its unit with both code ranges');
    panes.java.rows[96].click();
    ok($('source-origin').querySelectorAll('button').length===6, 'A shared Java line lists every unit it derives from');
    panes.cobol.rows[103].click();
    ok(conversionSelected.id==='copy-unused' && $('lines-java').closest('.listing').hidden, 'A dropped unit shows no Java code');
    select('conversion-filter','added');
    ok(document.querySelectorAll('#conversion-items button').length===3 && $('lines-cobol').closest('.listing').hidden, 'Added units show no COBOL origin');
    click('#next');
    ok(conversionSelected.id==='width-check', 'Next moves through the filtered units');
    click('#conversion-detail .review-relations button');
    ok(reviewStage==='compare' && comparisonSelected.id==='validation', 'A unit links to its behaviour review');
    select('conversion-filter','all');conversionSelected=null;setReviewStage('overview');
    click('[data-stage="legacy"]');
    ok(getComputedStyle(document.querySelector('.code-pane:nth-child(2)')).display==='none', 'Legacy stage displays only original code');
    ok(!$('graph-viewport').hidden, 'Legacy stage starts with current flow');
    panes.cobol.rows[282].click();
    ok($('source-origin').textContent.includes('対応なし'), 'Unmapped original code reveals missing flow mapping');
    click('#source-origin button');
    ok(!$('coverage-panel').hidden, 'Unmapped code links back to coverage audit');
    ok(auditSelected.start<=283 && auditSelected.end>=283, 'Source click selects the exact physical line range');
    const selectLine=n=>{$('audit-line').value=n;click('#audit-go');};
    const selectedRow=()=>$('audit-items').querySelector('[aria-selected="true"]');
    const originalCounts=JSON.stringify(sourceCoverage.counts);
    const physical=[...$('audit-items').querySelectorAll('tr')].flatMap(r=>Array.from({length:+r.dataset.end-(+r.dataset.start)+1},(_,i)=>+r.dataset.start+i));
    ok(physical.length===494 && physical.every((v,i)=>v===i+1), 'Every physical source line is listed once, in order, including comments and declarations');
    const sourceLines=data.sources.cobol.split(/\r\n|\r|\n/);
    const displayedLines=[...$('audit-items').querySelectorAll('[data-source-line]')];
    ok(displayedLines.length===494 && displayedLines.every((el,i)=>+el.dataset.sourceLine===i+1 && el.textContent===sourceLines[i].slice(['*','/'].includes(sourceLines[i][6])?6:7,72).trimEnd()), 'Unified reading surface displays every original source body line without truncated previews');
    ok(getComputedStyle(document.querySelector('.source-panel')).display==='none' && $('coverage-panel').getBoundingClientRect().width>document.querySelector('.workspace').getBoundingClientRect().width*.9, 'Coverage uses the full workspace width with no duplicate code pane');
    ok(parseFloat(getComputedStyle(document.querySelector('.source-inline-code')).fontSize)>=14 && !$('audit-guide').open && !$('audit-selection').open, 'Readable code size and collapsed supporting explanations');
    ok($('audit-summary').textContent.includes('216') && $('audit-summary').textContent.includes('28 / 36'), 'Unregistered flow lines and decisions stay explicit');
    click('#audit-first');
    ok(auditSelected.start===1 && $('prev').disabled && auditSelected.kind==='comment', 'First opens line one with a comment classification');
    click('#audit-last');
    ok(auditSelected.end===494 && $('next').disabled, 'Last opens the final physical line');
    click('#prev');
    ok(auditSelected.end<494, 'Previous advances in source order');
    selectLine(173);
    ok(selectedRow().querySelector('[data-source-line="173"]').textContent.includes('IF WS-XREF-READ-STATUS') && $('lines-java').closest('.listing').hidden, 'Selected row shows the original predicate directly');
    click('#audit-items [aria-selected="true"] [data-condition-link]');
    ok(!$('inspector').hidden && sourceInspect.section==='condition' && $('inspector').textContent.includes('WS-XREF-READ-STATUS') && $('inspector').textContent.includes('L165') && $('inspector').textContent.includes('未登録'), 'Condition detail includes the actual predicate, ancestor guard and unresolved binding');
    ok(getComputedStyle(document.querySelector('.source-panel')).display!=='none' && panes.cobol.rows[172].classList.contains('focus-line'), 'Opening evidence restores the full original code beside the detail');
    ok(!$('coverage-return').hidden && $('coverage-return-label').textContent.includes('L173'), 'Condition detail retains its source origin');
    const falseExample=[...$('inspector').querySelectorAll('.source-condition-card')].find(c=>c.textContent.includes('L173')).querySelectorAll('button')[2];
    falseExample.click();
    const decision173=audit.decisions.find(d=>d.start===173);
    ok(detailView==='flow' && decision173.binding.value(traces[scenario][index])===false, 'False example selects the corresponding modeled outcome');
    click('#coverage-back');
    ok(detailView==='coverage' && auditSelected.start===173, 'Back restores the original source range');
    click('#audit-items [aria-selected="true"] .source-more');
    ok($('audit-selection').open && [...$('audit-detail').querySelectorAll('button')].filter(b=>b.textContent.startsWith('フロー：')).length===auditSelected.flowIds.length, 'Additional flow mappings open on demand without hiding alternatives');
    const expandedRow=selectedRow().getBoundingClientRect(),expandedList=$('audit-table-scroll').getBoundingClientRect();
    ok(expandedRow.top>=expandedList.top-1 && expandedRow.bottom<=expandedList.bottom+1, 'Expanded mapping details keep the selected source row in view');
    $('audit-selection').open=false;
    click('#audit-items [aria-selected="true"] [data-flow-link]');
    ok(!$('graph-viewport').hidden && sourceReturnLine===173 && $('scenario').disabled===false, 'Registered source row opens its flow and retains return path');
    click('#coverage-back');selectLine(273);
    ok(selectedRow().textContent.includes('未登録') && !selectedRow().querySelector('[data-flow-link]'), 'Unmapped OPEN has no invented flow link');
    click('#audit-items [aria-selected="true"] [data-io-link]');
    ok($('inspector').textContent.includes('OPEN INPUT CUSTOMER-FILE') && $('inspector').textContent.includes('CUSTFILE') && !$('inspector').textContent.includes('undefined'), 'Unmapped OPEN still links to its actual I/O definition');
    click('#coverage-back');
    select('audit-kind','decisions');selectLine(477);
    click('#audit-items [aria-selected="true"] [data-condition-link]');
    ok($('inspector').textContent.includes('IO-STATUS NOT NUMERIC') && $('inspector').textContent.includes('未登録'), 'Unmapped compound condition shows its actual expression and incomplete status');
    click('#coverage-back');selectLine(99);
    ok(auditKind==='all' && auditSelected.kind==='definition' && selectedRow().textContent.includes('DALYTRAN'), 'Line lookup restores hidden definitions from a filtered view');
    click('#audit-items [aria-selected="true"] [data-io-link]');
    click('#inspector .source-condition-card button');
    ok($('dictionary').open && $('dict-file').value==='DALYTRAN' && $('dict-content').textContent.includes('DALYTRAN-CARD-NUM'), 'COPY line opens the matching original record definition');
    click('#close-dictionary');click('#coverage-back');click('#audit-first');click('#audit-next-gap');
    ok(auditSelected.requiresFlow && auditSelected.missing, 'Next missing skips comments and definitions');
    for(const kind of ['process','missing','definitions','decisions']) {
      select('audit-kind',kind);
      const ranges=visibleAuditItems();
      ok(ranges.length>0 && ranges.every((r,i)=>i===0||r.start>ranges[i-1].end) && document.querySelectorAll('#audit-items tr').length===ranges.length, 'Source filter preserves ordered ranges: '+kind);
    }
    select('audit-kind','all');
    ok(JSON.stringify(sourceCoverage.counts)===originalCounts, 'Viewing links never promotes unregistered mappings to covered');
    selectLine(173);click('#audit-items [aria-selected="true"] [data-flow-link]');
    click('#io-tab');
    ok(!$('inspector').hidden && $('inspector').textContent.includes('WS-XREF-READ-STATUS') && !$('inspector').textContent.includes('reference == null'), 'Legacy condition details contain only original expression');
    click('[data-stage="compare"]');
    ok(getComputedStyle(document.querySelector('.code-pane:nth-child(2)')).display!=='none', 'Comparison restores both code panes');
    ok(document.querySelectorAll('#comparison-items button').length===10, 'Ten behavior comparisons listed');
    click('[data-compare-id="close-order"]');
    ok($('comparison-detail').textContent.includes('逆順') && $('ranges-cobol').textContent.includes('L188'), 'Close order difference has original and new evidence');
    const selectedBox=$('comparison-items').querySelector('[aria-pressed="true"]').getBoundingClientRect();
    const listBox=$('comparison-items').getBoundingClientRect();
    ok(selectedBox.top>=listBox.top-1 && selectedBox.bottom<=listBox.bottom+1, 'Selected comparison stays visible in the list');
    select('comparison-filter','difference');
    ok(document.querySelectorAll('#comparison-items button').length===4, 'Difference filter exposes four distinct differences');
    select('comparison-filter','all');
    click('[data-compare-id="eof"]');
    ok($('comparison-detail').textContent.includes('初期値') && $('comparison-detail').textContent.includes('未確認'), 'Empty-input assumption remains explicit');
    click('[data-compare-id="validation"]');
    ok($('lines-cobol').closest('.listing').hidden, 'Java-only validation shows no invented original counterpart');
    click('#tests-tab');
    ok($('tests-panel').querySelectorAll('.proof-row').length===9 && $('tests-panel').textContent.includes('COBOL実行 ↔ Java実行'), 'Runtime evidence separates model checks from actual old-new execution');
    const prior=evidence.hashes.review;
    evidence.hashes.review='stale'; await validateAuditEvidence();
    ok(evidenceState==='stale' && !$('tests-panel').querySelector('.proof-row'), 'Stale ledger evidence cannot retain successful runtime badges');
    evidence.hashes.review=prior; await validateAuditEvidence();
    ok(evidenceState==='valid', 'Matching evidence restores after revalidation');
    click('[data-stage="data"]');
    ok(document.querySelectorAll('#mapping-items button').length===114, 'Data inventory includes 71 fields, 37 variables and six resources');
    $('mapping-search').value='DALYTRAN-CARD-NUM';$('mapping-search').dispatchEvent(new Event('input'));
    ok(document.querySelectorAll('#mapping-items button').length===1 && $('mapping-detail').textContent.includes('263–278'), 'Field search reveals original position and Java counterpart');
    ok($('ranges-java').textContent.includes('L110'), 'Field mapping highlights actual new use site');
    const back=[...$('mapping-detail').querySelectorAll('button')].find(b=>b.textContent==='② カード番号の照合');back.click();
    ok(reviewStage==='compare' && comparisonSelected.id==='card', 'Field links back to the same behavior review');
    click('[data-stage="data"]');
    $('mapping-search').value='no-such-field';$('mapping-search').dispatchEvent(new Event('input'));
    ok($('lines-cobol').closest('.listing').hidden && $('lines-java').closest('.listing').hidden, 'Empty search clears stale source highlights');
    $('mapping-search').value='';$('mapping-search').dispatchEvent(new Event('input'));select('mapping-category','unmapped');
    ok(document.querySelectorAll('#mapping-items button').length>0 && $('mapping-detail').textContent.includes('未整理'), 'Unresolved variables remain visible');
    select('mapping-category','all');
    if('__FINAL_STAGE__'==='coverage'){
      history.replaceState(null,'','?line=173#coverage');dispatchEvent(new HashChangeEvent('hashchange'));
      ok(reviewStage==='legacy' && detailView==='coverage' && auditSelected.start===173, 'Shared demo link opens the requested source row');
    }
    else setReviewStage('__FINAL_STAGE__');
    if(reviewStage==='convert') selectConversion(conversion.units.find(u=>u.id==='xref-read'));
    if(reviewStage==='compare') selectComparison(review.comparisons.find(c=>c.id==='close-order'));
    if(detailView==='coverage') {
      const a=selectedRow().getBoundingClientRect(),b=$('audit-table-scroll').getBoundingClientRect(),h=$('audit-table-scroll').querySelector('thead').getBoundingClientRect().height;
      ok(a.top>=b.top+h-1 && a.bottom<=b.bottom+1, 'Selected source row remains visible below the sticky header');
    }
    ok(!window.__qaErrors.length, 'No browser errors');
    ok(document.documentElement.scrollWidth<=innerWidth+1, 'No page horizontal overflow');
    const report=document.createElement('pre'); report.id='qa-results'; report.hidden=true;
    report.textContent=JSON.stringify({passed:true,checks,viewport:[innerWidth,innerHeight],stage:reviewStage});
    document.body.append(report);
  } catch(error) {
    const report=document.createElement('pre'); report.id='qa-results';
    report.textContent=JSON.stringify({passed:false,checks,error:String(error),browserErrors:window.__qaErrors});
    document.body.append(report);
  }
})();
</script>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', required=True, type=Path)
    parser.add_argument('--screenshot', required=True, type=Path)
    parser.add_argument('--width', type=int, default=1366)
    parser.add_argument('--height', type=int, default=900)
    parser.add_argument('--stage', choices=['overview','convert','legacy','coverage','compare','data'], default='overview')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = (root / 'viewer.html').read_text(encoding='utf-8')
    capture = '<script type="text/javascript">window.__qaErrors=[];addEventListener("error",e=>window.__qaErrors.push(e.message));addEventListener("unhandledrejection",e=>window.__qaErrors.push(String(e.reason)));</script>'
    page = source.replace('</head>', capture+'</head>').replace('</body>', QA.replace('__FINAL_STAGE__',args.stage)+'</body>').encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != '/':
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, *_):
            pass

    # A temporary profile keeps the user's browser profile untouched.
    with tempfile.TemporaryDirectory(dir=root, prefix='.viewer-browser-') as folder:
        profile = Path(folder).resolve()
        assert profile.parent == root.resolve() and profile.name.startswith('.viewer-browser-')
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run([str(args.browser), '--headless=new', '--no-first-run', '--no-default-browser-check',
                '--disable-extensions', '--disable-background-networking', '--force-device-scale-factor=1',
                '--user-data-dir='+str(profile), '--window-size='+str(args.width)+','+str(args.height),
                '--virtual-time-budget=7000', '--dump-dom', '--screenshot='+str(args.screenshot.resolve()),
                'http://127.0.0.1:'+str(server.server_port)+'/#overview'], capture_output=True, timeout=45)
        finally:
            server.shutdown()
            server.server_close()
        match = re.search(r'<pre id="qa-results"[^>]*>(.*?)</pre>', result.stdout.decode('utf-8'), re.S)
        if not match:
            raise RuntimeError('Browser QA produced no report: '+result.stderr.decode('utf-8', errors='replace')[-3000:])
        report = json.loads(html.unescape(match[1]))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        assert result.returncode == 0 and report['passed'], 'Browser checks failed'
        assert args.screenshot.exists(), 'Screenshot was not saved'
        print('Screenshot: '+str(args.screenshot.resolve()))


if __name__ == '__main__':
    main()
