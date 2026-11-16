"""Embed the source-order coverage component into the self-contained viewer."""
from pathlib import Path

root=Path(__file__).resolve().parents[1]
page=root/'viewer.html'
text=page.read_text(encoding='utf-8')
start_marker='// BEGIN SOURCE COVERAGE COMPONENT'
end_marker='// END SOURCE COVERAGE COMPONENT'
fragment=(root/'scripts/source_coverage.js').read_text(encoding='utf-8').rstrip()
assert '</script' not in fragment.lower()
if start_marker in text:
    begin=text.index(start_marker)
    end=text.index(end_marker,begin)+len(end_marker)
else:
    begin=text.index('function auditLabel(item) {')
    end=text.index('async function validateAuditEvidence()',begin)
text=text[:begin]+start_marker+'\n'+fragment+'\n'+end_marker+'\n'+text[end:]
page.write_bytes(text.encode('utf-8'))
print('Embedded source-order coverage. Run verify_viewer.py --update to refresh evidence.')
