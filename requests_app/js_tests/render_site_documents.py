"""Synthetic authorization print fixtures. No database connection or real users."""
import os
import sys
from pathlib import Path
from datetime import date
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.test_stock_review_settings'
import django
django.setup()
from django.utils import timezone
from django.utils.translation import override
from django.template.loader import render_to_string
from accounts.models import User, Department
from requests_app.models import Request, RequestType

output = ROOT / 'local_artifacts/agent_multiselect_tests/browser'
output.mkdir(parents=True, exist_ok=True)
for scenario in ('short', 'long', 'legacy'):
    long = scenario == 'long'
    names = [f'SITE-{i}-BEGIN ' + ('Long operational site name ' * 8 if long else '') + f'SITE-{i}-END' for i in range(1,6 if long else 2)]
    people = [f'AGENT-{i}-BEGIN ' + ('Long employee name ' * 4 if long else '') + f'AGENT-{i}-END' for i in range(1,11 if long else 2)]
    metadata = {'permission_group':'SITE_AUTHORIZATION','valid_from':'2026-11-09','valid_to':'2026-11-10',
                'site':'; '.join(names),'microcom_agents':'; '.join(people)}
    if scenario != 'legacy':
        metadata['site_selections'] = [{'kind':'manual','key':str(i),'name':name,'order':i} for i,name in enumerate(names)]
        metadata['agent_current_attempt'] = 'shared-print-attempt'
        metadata['agent_attempts'] = [{'id':'shared-print-attempt','version':2,'sites':metadata['site_selections'],
                                      'site_text':metadata['site'],'text':metadata['microcom_agents']}]
    else:
        metadata['site'] = 'LEGACY-SITE-FREE-TEXT'
    request = Request(request_type=RequestType(code='AUTORISATION_GENERAL', is_permission_request=True),
        request_number='SYNTHETIC-PRINT-'+scenario, status='APPROVED', metadata_json=metadata,
        description=('Long authorization reason requiring readable pagination. ' * 160 if long else 'Short authorization reason. ')+'REASON-END-MARKER',
        submitted_by=User(username='synthetic',full_name='Synthetic requester'), department=Department(name='Synthetic department'),
        request_for_department=Department(name='Synthetic department'), date_needed=date(2026,11,9), submitted_at=timezone.now(),finalized_at=timezone.now())
    approvals = [SimpleNamespace(step_order=i,display_approver_name=f'Approver {i}',status='APPROVED',
        comment=('Approval evidence and correction history. '*8 if long else '')+f'APPROVAL-{i}-END',acted_at=timezone.now()) for i in range(1,7 if long else 2)]
    for language in ('en','fr'):
        with override(language):
            html = render_to_string('requests_app/permission_document.html',{'request_obj':request,'metadata':metadata,'approvals':approvals,'back_url':'#'})
        (output/f'print_{scenario}_{language}.html').write_text(html,encoding='utf-8')
print('Wrote six synthetic print fixtures:',output)
