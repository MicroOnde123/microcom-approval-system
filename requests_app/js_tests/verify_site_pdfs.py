"""Check that Edge PDF output contains complete evidence in both copies."""
from pathlib import Path
from pypdf import PdfReader
import re
import json

root = Path(__file__).resolve().parents[2] / 'local_artifacts/agent_multiselect_tests/browser'
results = []
for language in ('en','fr'):
    for scenario in ('short','long','legacy'):
        document = PdfReader(root / f'print_{scenario}_{language}.pdf')
        assert all(abs(float(page.mediabox.width)-595.28)<1 and abs(float(page.mediabox.height)-841.89)<1 for page in document.pages), 'Expected portrait A4 pages'
        text = ' '.join(page.extract_text() or '' for page in document.pages)
        text = re.sub(r'\s+', ' ', text)
        if scenario == 'short':
            assert len(document.pages) == 1, ('Two short copies must fit on A4', language, len(document.pages))
        if scenario == 'long':
            assert len(document.pages) >= 2
            for index in range(1,6):assert text.count(f'SITE-{index}-END') == 2, (language,'site',index)
            for index in range(1,11):assert text.count(f'AGENT-{index}-END') == 2, (language,'agent',index)
            for index in range(1,7):assert text.count(f'APPROVAL-{index}-END') == 2, (language,'approval',index)
        if scenario == 'legacy':assert text.count('LEGACY-SITE-FREE-TEXT') == 2
        assert text.count('REASON-END-MARKER') == 2, (language,scenario,'reason clipped')
        signature = re.sub(r'\s+', ' ', (root/f'print_{scenario}_{language}.footer.txt').read_text(encoding='utf-8'))
        assert text.count(signature) == 2, (language,scenario,'signature clipped')
        results.append({'language':language,'scenario':scenario,'pages':len(document.pages),'complete_copies':2})
(root/'site_pdf_results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps({'pdf_checks':len(results),'passed':True,'results':results}))
