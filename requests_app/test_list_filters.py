"""Request-list filtering and authorization integration on isolated PostgreSQL."""
from datetime import datetime, timezone
import re

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import Department
from workflows.models import ApprovalWorkflow, ApprovalWorkflowStep
from .models import Request, RequestType, RequestApproval


class RequestListFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department=Department.objects.create(name='List Alpha',code='LISTA')
        cls.other_department=Department.objects.create(name='List Beta',code='LISTB')
        cls.kind=RequestType.objects.create(code='LIST',name='List Type')
        cls.other_kind=RequestType.objects.create(code='LIST2',name='Other Type')
        cls.user=get_user_model().objects.create_user(username='list-reader')
        cls.other=get_user_model().objects.create_user(username='list-other')
        workflow=ApprovalWorkflow.objects.create(name='List workflow',request_type=cls.kind)
        cls.step=ApprovalWorkflowStep.objects.create(workflow=workflow,step_order=1,approver_user=cls.user)

    def setUp(self):
        self.client.force_login(self.user)

    def request_row(self,number='LIST-1',**changes):
        values=dict(request_number=number,request_type=self.kind,department=self.department,
                    request_for_department=self.department,submitted_by=self.user,description='Cable installation',status='APPROVED')
        values.update(changes)
        row=Request.objects.create(**values)
        Request.objects.filter(pk=row.pk).update(submitted_at=datetime(2026,10,28,23,30,tzinfo=timezone.utc))
        return row

    def approval(self,row,action='REJECTED',actor=None,day=29):
        return RequestApproval.objects.create(request=row,workflow_step=self.step,approver_user=self.user,
                    step_order=1,status=action,acted_by=actor or self.user,acted_at=datetime(2026,10,day,10,tzinfo=timezone.utc))

    def page(self,name,**filters):
        response=self.client.get(reverse(name),filters)
        self.assertEqual(response.status_code,200)
        return response

    def test_my_requests_search_filters_and_visibility(self):
        row=self.request_row()
        self.request_row('SECRET',submitted_by=self.other)
        self.request_row('OTHER',request_for_department=self.other_department,request_type=self.other_kind,status='REJECTED')
        for filters in [{'q':'list-1'},{'q':'Cable','department':self.department.pk,'request_type':self.kind.pk,'status':'APPROVED','date_from':'2026-10-29','date_to':'2026-10-29'}]:
            response=self.page('my_requests',**filters)
            self.assertEqual([r.pk for r in response.context['requests']],[row.pk])
            self.assertNotContains(response,'SECRET')
        self.assertNotContains(self.page('my_requests',q='SECRET'),'SECRET</strong>')

    def test_history_preserves_latest_action_and_overall_status(self):
        row=self.request_row();self.approval(row,'APPROVED',day=28);latest=self.approval(row,'REJECTED')
        hidden=self.request_row('SECRET');self.approval(hidden,actor=self.other)
        response=self.page('approval_history',q='Cable',department=self.department.pk,request_type=self.kind.pk,status='APPROVED',action='REJECTED',date_from='2026-10-29',date_to='2026-10-29')
        self.assertEqual([a.pk for a in response.context['approvals']],[latest.pk])
        self.assertContains(response,'Your Action');self.assertNotContains(response,'SECRET')
        self.assertEqual(len(self.page('approval_history',action='APPROVED').context['approvals']),0)
        self.assertEqual(len(self.page('approval_history',date_to='2026-10-28').context['approvals']),0)

    def test_each_filter_independently(self):
        row=self.request_row();action=self.approval(row)
        other=self.request_row('OTHER',description='Unrelated',request_type=self.other_kind,request_for_department=self.other_department,status='REJECTED')
        other_action=self.approval(other,day=30)
        Request.objects.filter(pk=other.pk).update(submitted_at=datetime(2026,10,30,10,tzinfo=timezone.utc))
        for name in ['my_requests','approval_history']:
            for filters in [{'q':'LIST-1'},{'department':self.department.pk},{'request_type':self.kind.pk},{'status':'APPROVED'},{'date_from':'2026-10-29'},{'date_to':'2026-10-29'}]:
                with self.subTest(name=name,filters=filters):
                    response=self.page(name,**filters)
                    rows=response.context['requests' if name=='my_requests' else 'approvals']
                    self.assertIn(row.pk if name=='my_requests' else action.pk,[r.pk for r in rows])
                    if 'date_from' not in filters:
                        self.assertNotIn(other.pk if name=='my_requests' else other_action.pk,[r.pk for r in rows])
            response=self.page(name,date_from='2026-10-30')
            rows=response.context['requests' if name=='my_requests' else 'approvals']
            self.assertEqual([r.pk for r in rows],[other.pk if name=='my_requests' else other_action.pk])

    def test_invalid_values_fail_closed_without_server_error(self):
        row=self.request_row();self.approval(row)
        for name in ['my_requests','approval_history']:
            for filters in [{'department':'bad'},{'request_type':'99999999999999999999999999999'},{'status':'INVALID'},{'date_from':'bad'},{'date_from':'2026-10-30','date_to':'2026-10-29'},{'date_to':'9999-12-31'},{'q':'x'*201}]:
                response=self.page(name,**filters)
                self.assertTrue(response.context['filter_form'].errors)
                self.assertEqual(response.context['page_obj'].paginator.count,0)
        self.assertTrue(self.page('approval_history',action='PENDING').context['filter_form'].errors)

    def test_pagination_empty_results_navigation_and_bilingual_controls(self):
        for index in range(26):self.approval(self.request_row(f'PAGED-{index:02d}'))
        for name in ['my_requests','approval_history']:
            for language in ['en','fr']:
                response=self.client.get(reverse(name),{'q':'PAGED','page':'2'},HTTP_ACCEPT_LANGUAGE=language)
                self.assertEqual(len(response.context['page_obj']),1)
                self.assertContains(response,'name="department"');self.assertContains(response,'q=PAGED')
                self.assertContains(response,reverse('dashboard'))
                self.assertContains(response,'Recherche et filtres' if language=='fr' else 'Search and filters')
            self.assertEqual(self.page(name,page='bad').context['page_obj'].number,1)
            self.assertEqual(self.page(name,page='999').context['page_obj'].number,2)
            self.assertEqual(self.page(name,q='NO-MATCH').context['page_obj'].paginator.count,0)

    def test_bounded_queries_and_no_writes(self):
        row=self.request_row();self.approval(row)
        for name in ['my_requests','approval_history']:
            with CaptureQueriesContext(connection) as small:self.page(name)
            for index in range(4):self.approval(self.request_row(f'MORE-{name}-{index}'))
            with CaptureQueriesContext(connection) as large:self.page(name)
            self.assertLessEqual(len(large),len(small)+1)
            # Existing SESSION_SAVE_EVERY_REQUEST legitimately updates the login
            # session. The lists must not write any business table.
            unexpected_queries = [
                q["sql"]
                for q in large
                if not (
                    q["sql"].lstrip().upper().startswith("SELECT")
                    or q["sql"].lstrip().upper().startswith('UPDATE "DJANGO_SESSION"')
                    or q["sql"].lstrip().upper().startswith("SAVEPOINT ")
                    or q["sql"].lstrip().upper().startswith("RELEASE SAVEPOINT ")
                    or re.match(r'^DECLARE "[^"]+" (?:NO )?SCROLL CURSOR (?:WITHOUT|WITH) HOLD FOR SELECT\b', q["sql"].lstrip().upper())
                )
            ]

            self.assertFalse(
                unexpected_queries,
                msg="Unexpected SQL statements:\n" + "\n".join(unexpected_queries),
            )

    def test_anonymous_users_cannot_access_lists(self):
        self.client.logout()
        for name in ['my_requests','approval_history']:
            self.assertEqual(self.client.get(reverse(name)).status_code,302)
