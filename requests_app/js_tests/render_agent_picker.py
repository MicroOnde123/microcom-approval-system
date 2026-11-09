"""Render synthetic browser fixtures without connecting to a database."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.test_stock_review_settings"
import django
django.setup()
from django import forms
from django.template.loader import render_to_string
from django.template import Template, Context
from django.utils.translation import override

class PreviewForm(forms.Form):
    agent_selections = forms.JSONField(required=False, widget=forms.HiddenInput, initial=[])
    site_selections = forms.JSONField(required=False, widget=forms.HiddenInput, initial=[])
    agent_legacy_text = ""
    site_legacy_text = ""


def form_page(content, language, site_picker=None):
    # Use the application's actual base and request-form styles for grid verification.
    styles = []
    for source in ("templates/base.html", "templates/requests_app/create_request.html"):
        markup = (ROOT / source).read_text(encoding="utf-8")
        styles.append(markup.split("<style>", 1)[1].split("</style>", 1)[0])
    css = Template("{% load i18n static %}" + "\n".join(styles)).render(Context({}))
    body = Template('''{% load i18n %}<main style="max-width:1000px;margin:24px auto;padding:0 16px">
    <h1>{% trans 'Site Authorization' %}</h1><section class="card form-section"><form><div class="form-grid" data-preview-grid>
    <div>{% if site_picker %}{{ site_picker|safe }}{% else %}<label for="preview-site">{% trans 'Site' %}</label><input id="preview-site" value="Site Microcom">{% endif %}</div>
    <div><label for="preview-from">{% trans 'Valid From' %}</label><input id="preview-from" type="date" value="2026-11-09"></div>
    <div><label for="preview-to">{% trans 'Valid To' %}</label><input id="preview-to" type="date" value="2026-11-10"></div>
    <div>{{ picker|safe }}</div>
    <div><label for="preview-tt">{% trans 'TT' %}</label><input id="preview-tt"></div>
    <div><label for="preview-external">{% trans 'External Persons' %}</label><input id="preview-external"></div>
    </div></form></section></main>''').render(Context({"picker": content, "site_picker": site_picker}))
    return '<!doctype html><html lang="'+language+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>'+css+'</style></head><body>'+body+'</body></html>'

output = ROOT / "local_artifacts" / "agent_multiselect_tests" / "browser"
output.mkdir(parents=True, exist_ok=True)
for language in ("en", "fr"):
    with override(language):
        content = render_to_string("requests_app/includes/agent_picker.html", {"form": PreviewForm()})
        html = form_page(content, language)
    (output / (language+".html")).write_text(html, encoding="utf-8")
    with override(language):
        site_picker = render_to_string("requests_app/includes/site_picker.html", {"form": PreviewForm()})
        together = form_page(content, language, site_picker)
    (output / (language+"_sites.html")).write_text(together, encoding="utf-8")
for scenario, initial, legacy in (
    ("draft", [{"kind": "user", "user_id": 12, "full_name": "Saved Employee"},
               {"kind": "manual", "key": "saved-person", "first_name": "Saved", "surname": "Person", "full_name": "Saved Person"}], ""),
    ("legacy", [], "Historical text / exact punctuation"),
    ("invalid", {"tampered": True}, ""),
):
    form = PreviewForm(initial={"agent_selections": initial})
    form.agent_legacy_text = legacy
    content = render_to_string("requests_app/includes/agent_picker.html", {"form": form})
    (output / (scenario+".html")).write_text('<!doctype html><meta charset="utf-8"><form>'+content+'</form>', encoding="utf-8")
for scenario in ("draft", "legacy"):
    form = PreviewForm(initial={"site_selections": [{"kind":"site","site_id":12,"name":"Saved directory site"},
        {"kind":"manual","key":"saved-site","name":"Saved manual site"}],
        "agent_selections":[{"kind":"user","user_id":12,"full_name":"Saved Employee"}]})
    if scenario == "legacy":
        form.site_legacy_text = "Historical site / exact punctuation"
        form.initial["site_selections"] = []
    content = render_to_string("requests_app/includes/agent_picker.html", {"form":form})
    site_picker = render_to_string("requests_app/includes/site_picker.html", {"form":form})
    (output/("sites_"+scenario+".html")).write_text(form_page(content,"en",site_picker),encoding="utf-8")
for name in ("agent_picker.js", "agent_picker.css", "site_picker.js"):
    (output / name).write_bytes((ROOT / "static" / "requests_app" / name).read_bytes())
print(output)
