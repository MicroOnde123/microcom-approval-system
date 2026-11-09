"""Static documentation checks only. Does not import/start the application."""
from pathlib import Path
from pypdf import PdfReader
import re
import json
import xml.etree.ElementTree as ET

import sys
ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
ASSETS=Path(__file__).resolve().parent
from pypdf._text_extraction import mult
summary={}
for lang in ("en","fr"):
    file=ROOT/f"user-manual-{lang}.md"
    content=file.read_text(encoding="utf-8")
    chapters=re.findall(r"^## (\d+)\. ",content,re.M)
    assert chapters==[str(x) for x in range(30)], (lang,chapters)
    assert "\ufffd" not in content
    assert "-pending.svg" not in content
    for link in re.findall(r"\]\(([^)]+)\)",content):
        if link.startswith("#"):
            assert 'id="'+link[1:]+'"' in content,link
        else:
            assert (ASSETS.parent/link).exists(),link
    for svg in (ASSETS/lang).glob("*.svg"):
        ET.parse(svg)
    summary[lang]={"chapters":29,"inline_placeholders":0,"links":"valid"}
for file in ROOT.glob("Microcom_*.pdf"):
    pdf=PdfReader(file)
    texts=[p.extract_text() for p in pdf.pages]
    assert len(texts)>=30,(file,len(texts))
    assert not pdf.is_encrypted
    assert all("\ufffd" not in t for t in texts)
    assert all(len(t.strip())>80 for t in texts)
    assert all(f"{i+1} / {len(texts)}" in t for i,t in enumerate(texts))
    assert "2026-11-09" in texts[0] and "3.0" in texts[0]
    assert "TEXT USER GUIDE" in texts[0] or "GUIDE UTILISATEUR TEXTUEL" in texts[0]
    assert all("REAL SCREENSHOT PENDING" not in t and "CAPTURE R?ELLE EN ATTENTE" not in t for t in texts)
    for page in pdf.pages:
        def bounds(text, cm, tm, font, size):
            if text.strip():
                x,y=mult(tm,cm)[4:6]
                assert 0<=x<=float(page.mediabox.width) and 0<=y<=float(page.mediabox.height),(file,x,y)
        page.extract_text(visitor_text=bounds)
    manifest_path=ROOT/"capture-manifest.json" if (ROOT/"capture-manifest.json").exists() else ASSETS/"capture-manifest.json"
    manifest_data=json.loads(manifest_path.read_text(encoding="utf-8"))
    language="fr" if "FR" in file.name else "en"
    contents=" ".join(texts[:4])
    for card in manifest_data["primary"]:
        title=card[language]
        title_pattern=re.escape(title).replace(r"\ ",r"\s+")
        heading=re.compile(r"(?m)^\d{2}\s+"+title_pattern+r"\s*$")
        pages=[i for i,t in enumerate(texts,1) if heading.search(t)]
        assert pages,(language,title)
        assert re.search(title_pattern+r"\s+"+str(pages[0])+r"\b",contents),(language,title,"contents")
    assert "Credit" in "".join(texts) or "Avoirs" in "".join(texts)
    summary[file.name]={"pages":len(texts),"blank_pages":0,"numbering":"valid","status":"final text edition","bytes":file.stat().st_size}
manifest=json.loads((ROOT/"capture-manifest.json" if (ROOT/"capture-manifest.json").exists() else ASSETS/"capture-manifest.json").read_text(encoding="utf-8"))
assert manifest["real_captured"]==manifest["real_annotated"]==manifest["workflow_runtime_verified"]==0
summary["screen_state_inventory_rows"]=sum(c["status"]=="missing" for c in manifest["primary"])+len(manifest["additional_states"])
summary["real_screenshots"]=0
summary["annotated_screenshots"]=0
summary["application_tests_run_by_document_validator"]=False
summary["authenticated_runtime_verification"]=False
for file in [ASSETS.parent/"user-manual-validation.md",ROOT/"manual-screenshot-checklist.md"]:
    for link in re.findall(r"\]\(([^)]+)\)",file.read_text(encoding="utf-8")):
        assert (ASSETS.parent/link).exists(),link
(ROOT/"document-checks.json" if ROOT!=ASSETS.parent else ASSETS/"document-checks.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(summary,ensure_ascii=False,indent=2))
