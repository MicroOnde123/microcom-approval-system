"""Guards touch only new financial tables; stock rows are read/locked, never changed."""
from django.db import migrations


SQL = r"""
-- A technical uniqueness registry, not a number generator. A shared UNIQUE key
-- remains safe at REPEATABLE READ too, unlike cross-table snapshot checks.
CREATE TABLE invoicing_finalreference (
 number varchar(150) PRIMARY KEY,
 document_type varchar(10) NOT NULL CHECK (document_type IN ('INVOICE','CREDIT')),
 document_id bigint NOT NULL,
 UNIQUE(document_type,document_id)
);
CREATE FUNCTION inv_fail() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Append-only financial evidence cannot be changed' USING ERRCODE='23514'; END $$;

CREATE FUNCTION inv_document_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r record; a record; v record; s record; docdate date; expected text;
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN
   RAISE EXCEPTION 'Financial document writes require READ COMMITTED isolation' USING ERRCODE='23514'; END IF;
 IF TG_OP <> 'INSERT' AND OLD.status = 'FINALIZED' THEN
   RAISE EXCEPTION 'Finalized financial documents are immutable' USING ERRCODE='23514';
 END IF;
 IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
 IF TG_TABLE_NAME = 'invoicing_invoice' THEN
   SELECT * INTO r FROM requests_app_request WHERE id=NEW.request_id FOR SHARE;
   SELECT * INTO a FROM requests_app_requestapproval WHERE id=NEW.classification_approval_id;
   SELECT * INTO v FROM invoicing_companyverification WHERE id=NEW.company_verification_id;
   IF NEW.business_timezone IS DISTINCT FROM (SELECT business_timezone FROM core_companydocumentsettings WHERE id=v.configuration_id) THEN
     RAISE EXCEPTION 'Document business timezone must match explicit company configuration' USING ERRCODE='23514'; END IF;
   IF r.status <> 'APPROVED' OR NOT r.stock_deducted OR r.classification IS DISTINCT FROM 'MICROCOM'
      OR NOT EXISTS(SELECT 1 FROM requests_app_requesttype WHERE id=r.request_type_id AND requires_materials)
      OR r.succursale_id IS DISTINCT FROM NEW.succursale_id
      OR r.classified_by_id IS DISTINCT FROM NEW.classification_actor_id
      OR r.classified_at IS DISTINCT FROM NEW.classification_at
      OR a.request_id IS DISTINCT FROM r.id OR NOT a.requires_stock_classification
      OR a.status IS DISTINCT FROM 'APPROVED' OR a.acted_at IS NULL OR a.acted_by_id IS DISTINCT FROM NEW.classification_actor_id THEN
     RAISE EXCEPTION 'Approved Microcom request and classification confirmation required' USING ERRCODE='23514';
   END IF;
   IF NOT EXISTS (SELECT 1 FROM requests_app_requestmaterialitem WHERE request_id=r.id)
     OR EXISTS (SELECT 1 FROM requests_app_requestmaterialitem i WHERE i.request_id=r.id AND
       (i.quantity<=0 OR (SELECT count(*) FROM requests_app_requestmaterialitem x WHERE x.request_id=r.id AND x.material_id=i.material_id)<>1
        OR (SELECT count(*) FROM requests_app_stockmovement m WHERE m.request_id=r.id AND m.material_id=i.material_id AND m.movement_type='OUT')<>1
        OR NOT EXISTS (SELECT 1 FROM requests_app_stockmovement m WHERE m.request_id=r.id AND m.material_id=i.material_id AND m.movement_type='OUT' AND m.quantity=i.quantity AND m.quantity>0)
        OR EXISTS (SELECT 1 FROM requests_app_stockmovement m WHERE m.request_id=r.id AND m.material_id=i.material_id AND m.movement_type='RETURN'
          AND (m.quantity<=0 OR m.created_at<(SELECT created_at FROM requests_app_stockmovement source WHERE source.request_id=r.id AND source.material_id=i.material_id AND source.movement_type='OUT' LIMIT 1)))
        OR COALESCE((SELECT sum(m.quantity) FROM requests_app_stockmovement m WHERE m.request_id=r.id AND m.material_id=i.material_id AND m.movement_type='RETURN'),0)>i.quantity))
     OR EXISTS (SELECT 1 FROM requests_app_stockmovement m WHERE m.request_id=r.id AND m.movement_type IN ('OUT','RETURN')
       AND NOT EXISTS (SELECT 1 FROM requests_app_requestmaterialitem i WHERE i.request_id=r.id AND i.material_id=m.material_id)) THEN
     RAISE EXCEPTION 'Financial allocation blocked: ambiguous or inconsistent stock history; administrator review required' USING ERRCODE='23514';
   END IF;
   IF NEW.status='FINALIZED' THEN
     IF NEW.company_snapshot IS DISTINCT FROM v.configuration_snapshot THEN
       RAISE EXCEPTION 'Company snapshot must match the verified configuration' USING ERRCODE='23514'; END IF;
     IF NOT EXISTS (SELECT 1 FROM core_companydocumentsettings c WHERE c.id=v.configuration_id
       AND (to_jsonb(c)-'id'-'updated_at')=v.configuration_snapshot) THEN
       RAISE EXCEPTION 'Company verification is stale' USING ERRCODE='23514';
     END IF;
     IF NOT EXISTS (SELECT 1 FROM invoicing_invoiceline WHERE invoice_id=NEW.id)
        OR EXISTS (SELECT 1 FROM invoicing_invoiceline l LEFT JOIN invoicing_invoiceissueallocation x ON x.line_id=l.id
          WHERE l.invoice_id=NEW.id AND (l.unit_price IS NULL OR l.line_total IS NULL OR x.id IS NULL OR x.quantity<>l.quantity
            OR l.line_total<>round(l.quantity*l.unit_price,2)))
        OR NEW.total IS DISTINCT FROM (SELECT sum(line_total) FROM invoicing_invoiceline WHERE invoice_id=NEW.id) THEN
       RAISE EXCEPTION 'Complete priced invoice allocations and consistent totals required' USING ERRCODE='23514';
     END IF;
     -- Every OUT must be represented by net billing plus whole return exclusions.
     IF EXISTS (SELECT 1 FROM requests_app_stockmovement m WHERE m.request_id=r.id AND m.movement_type='OUT' AND
       m.quantity IS DISTINCT FROM COALESCE((SELECT sum(x.quantity) FROM invoicing_invoiceissueallocation x
          JOIN invoicing_invoiceline l ON l.id=x.line_id WHERE l.invoice_id=NEW.id AND x.out_movement_id=m.id),0)
          + COALESCE((SELECT sum(e.quantity) FROM invoicing_invoicereturnexclusion e JOIN invoicing_invoiceissueallocation x ON x.id=e.issue_allocation_id
              JOIN invoicing_invoiceline l ON l.id=x.line_id WHERE l.invoice_id=NEW.id AND x.out_movement_id=m.id),0))
       OR EXISTS (SELECT 1 FROM requests_app_stockmovement m WHERE m.request_id=r.id AND m.movement_type='RETURN' AND
          NOT EXISTS (SELECT 1 FROM invoicing_invoicereturnexclusion e JOIN invoicing_invoiceissueallocation x ON x.id=e.issue_allocation_id
            JOIN invoicing_invoiceline l ON l.id=x.line_id WHERE l.invoice_id=NEW.id AND e.return_movement_id=m.id)) THEN
       RAISE EXCEPTION 'All pre-invoice returns must be excluded from billing' USING ERRCODE='23514';
     END IF;
   END IF;
 ELSE
   SELECT * INTO r FROM invoicing_invoice WHERE id=NEW.invoice_id FOR UPDATE;
   IF r.status IS DISTINCT FROM 'FINALIZED' OR NEW.currency<>r.currency THEN
     RAISE EXCEPTION 'Credit notes require a finalized invoice and matching currency' USING ERRCODE='23514';
   END IF;
   IF NEW.business_timezone IS DISTINCT FROM (SELECT company_config.business_timezone FROM core_companydocumentsettings company_config
       JOIN invoicing_companyverification verification_row ON verification_row.configuration_id=company_config.id
       WHERE verification_row.id=r.company_verification_id) THEN
     RAISE EXCEPTION 'Credit business timezone must match explicit company configuration' USING ERRCODE='23514'; END IF;
   IF NEW.status='FINALIZED' AND (NOT EXISTS(SELECT 1 FROM invoicing_creditallocation WHERE credit_note_id=NEW.id)
       OR NEW.total IS DISTINCT FROM (SELECT sum(line_total) FROM invoicing_creditallocation WHERE credit_note_id=NEW.id)) THEN
     RAISE EXCEPTION 'Credit allocations and consistent totals required' USING ERRCODE='23514';
   END IF;
 END IF;
 IF NEW.status='FINALIZED' THEN
   IF TG_OP='INSERT' THEN
     RAISE EXCEPTION 'Financial documents must begin as drafts' USING ERRCODE='23514';
   END IF;
   SELECT * INTO s FROM invoicing_documentsequence WHERE id=NEW.sequence_id FOR UPDATE;
   IF s.document_type<>(CASE WHEN TG_TABLE_NAME='invoicing_invoice' THEN 'INVOICE' ELSE 'CREDIT' END)
      OR s.verified_by_id IS NULL OR s.verified_at IS NULL OR s.verification_digest='' OR s.verification_evidence='' THEN
     RAISE EXCEPTION 'Verified document sequence required' USING ERRCODE='23514';
   END IF;
   INSERT INTO invoicing_finalreference(number,document_type,document_id)
     VALUES(NEW.number,CASE WHEN TG_TABLE_NAME='invoicing_invoice' THEN 'INVOICE' ELSE 'CREDIT' END,NEW.id);
   IF NEW.finalized_at < statement_timestamp()-interval '5 seconds' OR NEW.finalized_at>statement_timestamp()+interval '5 seconds' THEN
     RAISE EXCEPTION 'Backdated or future finalization is prohibited' USING ERRCODE='23514'; END IF;
   -- Persist database time, never a caller-controlled issue timestamp. At the
   -- year boundary a mismatched date/sequence fails atomically for later retry.
   NEW.finalized_at := clock_timestamp();
   docdate := (NEW.finalized_at AT TIME ZONE NEW.business_timezone)::date;
   IF NEW.issue_date IS DISTINCT FROM docdate OR s.year<>extract(year FROM docdate)::int
      OR NEW.company_snapshot='{}'::jsonb OR NEW.succursale_snapshot='{}'::jsonb
      OR NEW.branding_snapshot='{}'::jsonb OR NEW.request_reference_snapshot='' OR NEW.amount_words_fr='' THEN
     RAISE EXCEPTION 'Current finalization time and complete immutable snapshots required' USING ERRCODE='23514';
   END IF;
 END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION inv_child_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE n jsonb; o jsonb; olddoc bigint; doc bigint; credit bigint; state text;
  l record; x record; m record; source record; inv record; c record; used numeric;
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN
   RAISE EXCEPTION 'Financial allocation writes require READ COMMITTED isolation' USING ERRCODE='23514'; END IF;
 IF TG_OP <> 'INSERT' THEN
   o:=to_jsonb(OLD);
   IF TG_TABLE_NAME='invoicing_invoiceline' THEN olddoc:=OLD.invoice_id;
   ELSIF TG_TABLE_NAME='invoicing_invoiceissueallocation' THEN SELECT invoice_id INTO olddoc FROM invoicing_invoiceline WHERE id=OLD.line_id;
   ELSIF TG_TABLE_NAME='invoicing_invoicereturnexclusion' THEN SELECT l.invoice_id INTO olddoc FROM invoicing_invoiceissueallocation x JOIN invoicing_invoiceline l ON l.id=x.line_id WHERE x.id=OLD.issue_allocation_id;
   ELSE SELECT status INTO state FROM invoicing_creditnote WHERE id=OLD.credit_note_id FOR UPDATE;
   END IF;
   IF olddoc IS NOT NULL THEN SELECT status INTO state FROM invoicing_invoice WHERE id=olddoc FOR UPDATE; END IF;
   IF state='FINALIZED' THEN RAISE EXCEPTION 'Finalized financial children are immutable' USING ERRCODE='23514'; END IF;
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 IF TG_TABLE_NAME='invoicing_invoiceline' THEN
   doc:=NEW.invoice_id;
 ELSIF TG_TABLE_NAME='invoicing_invoiceissueallocation' THEN
   SELECT * INTO l FROM invoicing_invoiceline WHERE id=NEW.line_id;
   doc:=l.invoice_id;
 ELSIF TG_TABLE_NAME='invoicing_invoicereturnexclusion' THEN
   SELECT * INTO x FROM invoicing_invoiceissueallocation WHERE id=NEW.issue_allocation_id;
   SELECT * INTO l FROM invoicing_invoiceline WHERE id=x.line_id;
   doc:=l.invoice_id;
 ELSE
   SELECT * INTO c FROM invoicing_creditnote WHERE id=NEW.credit_note_id FOR UPDATE;
   IF c.status='FINALIZED' THEN RAISE EXCEPTION 'Finalized financial children are immutable' USING ERRCODE='23514'; END IF;
   SELECT * INTO x FROM invoicing_invoiceissueallocation WHERE id=NEW.issue_allocation_id;
   SELECT * INTO l FROM invoicing_invoiceline WHERE id=x.line_id;
   SELECT * INTO inv FROM invoicing_invoice WHERE id=l.invoice_id FOR UPDATE;
   SELECT * INTO m FROM requests_app_stockmovement WHERE id=NEW.return_movement_id FOR UPDATE;
   SELECT * INTO source FROM requests_app_stockmovement WHERE id=x.out_movement_id;
   IF TG_OP='UPDATE' AND (OLD.credit_note_id<>NEW.credit_note_id OR OLD.issue_allocation_id<>NEW.issue_allocation_id OR OLD.return_movement_id<>NEW.return_movement_id) THEN
     RAISE EXCEPTION 'Credit allocation identity cannot be changed' USING ERRCODE='23514'; END IF;
   IF inv.id IS DISTINCT FROM c.invoice_id OR m.movement_type IS DISTINCT FROM 'RETURN' OR m.quantity<=0
      OR m.request_id IS DISTINCT FROM source.request_id OR m.material_id IS DISTINCT FROM source.material_id
      OR m.created_at<=inv.finalized_at
      OR EXISTS(SELECT 1 FROM invoicing_invoicereturnexclusion WHERE return_movement_id=m.id)
      OR NEW.unit_price_snapshot IS DISTINCT FROM l.unit_price OR NEW.line_total<>round(NEW.quantity*NEW.unit_price_snapshot,2) THEN
     RAISE EXCEPTION 'Return is not eligible for this invoice credit' USING ERRCODE='23514';
   END IF;
   SELECT COALESCE(sum(quantity),0) INTO used FROM invoicing_creditallocation WHERE return_movement_id=m.id AND id<>COALESCE(NEW.id,0);
   IF used+NEW.quantity>m.quantity THEN RAISE EXCEPTION 'Credit exceeds returned quantity' USING ERRCODE='23514'; END IF;
   SELECT COALESCE(sum(quantity),0) INTO used FROM invoicing_creditallocation WHERE issue_allocation_id=x.id AND id<>COALESCE(NEW.id,0);
   IF used+NEW.quantity>x.quantity THEN RAISE EXCEPTION 'Credit exceeds invoiced quantity' USING ERRCODE='23514'; END IF;
   RETURN NEW;
 END IF;
 SELECT * INTO inv FROM invoicing_invoice WHERE id=doc FOR UPDATE;
 IF inv.status='FINALIZED' THEN RAISE EXCEPTION 'Finalized financial children are immutable' USING ERRCODE='23514'; END IF;
 IF TG_OP='UPDATE' THEN
   -- Reparenting is forbidden: delete/recreate draft allocations instead.
   n:=to_jsonb(NEW);
   IF (o-'quantity'-'unit_price'-'line_total'-'description_snapshot'-'material_code_snapshot'-'unit_snapshot'-'rounding_policy'-'position')
      IS DISTINCT FROM (n-'quantity'-'unit_price'-'line_total'-'description_snapshot'-'material_code_snapshot'-'unit_snapshot'-'rounding_policy'-'position') THEN
     RAISE EXCEPTION 'Financial allocation identity cannot be changed' USING ERRCODE='23514';
   END IF;
 END IF;
 IF TG_TABLE_NAME='invoicing_invoiceline' THEN
   IF NEW.currency<>inv.currency OR NOT EXISTS(SELECT 1 FROM requests_app_requestmaterialitem WHERE request_id=inv.request_id AND material_id=NEW.material_id) THEN
     RAISE EXCEPTION 'Invoice line must match issued request and currency' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='invoicing_invoiceissueallocation' THEN
   SELECT * INTO m FROM requests_app_stockmovement WHERE id=NEW.out_movement_id FOR UPDATE;
   IF m.movement_type IS DISTINCT FROM 'OUT' OR m.quantity<=0 OR m.material_id IS DISTINCT FROM l.material_id OR m.request_id IS DISTINCT FROM inv.request_id
      OR NEW.quantity+COALESCE((SELECT sum(quantity) FROM invoicing_invoicereturnexclusion WHERE issue_allocation_id=NEW.id),0)>m.quantity OR NEW.quantity<>l.quantity THEN
     RAISE EXCEPTION 'Consistent positive OUT allocation required' USING ERRCODE='23514'; END IF;
 ELSE
   SELECT * INTO m FROM requests_app_stockmovement WHERE id=NEW.return_movement_id FOR UPDATE;
   SELECT * INTO source FROM requests_app_stockmovement WHERE id=x.out_movement_id;
   IF m.movement_type IS DISTINCT FROM 'RETURN' OR m.quantity<=0 OR NEW.quantity<>m.quantity
      OR m.material_id IS DISTINCT FROM source.material_id OR m.request_id IS DISTINCT FROM source.request_id
      OR EXISTS(SELECT 1 FROM invoicing_creditallocation WHERE return_movement_id=m.id) THEN
     RAISE EXCEPTION 'Consistent whole pre-invoice RETURN exclusion required' USING ERRCODE='23514'; END IF;
   SELECT COALESCE(sum(quantity),0) INTO used FROM invoicing_invoicereturnexclusion WHERE issue_allocation_id=x.id AND id<>COALESCE(NEW.id,0);
   IF used+NEW.quantity+x.quantity>source.quantity THEN RAISE EXCEPTION 'Net billing plus exclusions exceed issue' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$;

CREATE TRIGGER inv_invoice_guard BEFORE INSERT OR UPDATE OR DELETE ON invoicing_invoice FOR EACH ROW EXECUTE FUNCTION inv_document_guard();
CREATE TRIGGER inv_credit_guard BEFORE INSERT OR UPDATE OR DELETE ON invoicing_creditnote FOR EACH ROW EXECUTE FUNCTION inv_document_guard();
CREATE TRIGGER inv_line_guard BEFORE INSERT OR UPDATE OR DELETE ON invoicing_invoiceline FOR EACH ROW EXECUTE FUNCTION inv_child_guard();
CREATE TRIGGER inv_issue_guard BEFORE INSERT OR UPDATE OR DELETE ON invoicing_invoiceissueallocation FOR EACH ROW EXECUTE FUNCTION inv_child_guard();
CREATE TRIGGER inv_exclusion_guard BEFORE INSERT OR UPDATE OR DELETE ON invoicing_invoicereturnexclusion FOR EACH ROW EXECUTE FUNCTION inv_child_guard();
CREATE TRIGGER inv_creditallocation_guard BEFORE INSERT OR UPDATE OR DELETE ON invoicing_creditallocation FOR EACH ROW EXECUTE FUNCTION inv_child_guard();
CREATE TRIGGER inv_audit_append_only BEFORE UPDATE OR DELETE ON invoicing_invoiceauditevent FOR EACH ROW EXECUTE FUNCTION inv_fail();
CREATE TRIGGER inv_verification_append_only BEFORE UPDATE OR DELETE ON invoicing_companyverification FOR EACH ROW EXECUTE FUNCTION inv_fail();
CREATE TRIGGER inv_artifact_append_only BEFORE UPDATE OR DELETE ON invoicing_documentartifact FOR EACH ROW EXECUTE FUNCTION inv_fail();
CREATE TRIGGER inv_reference_append_only BEFORE UPDATE OR DELETE ON invoicing_finalreference FOR EACH ROW EXECUTE FUNCTION inv_fail();

CREATE FUNCTION inv_sequence_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF position('{year' in NEW.number_format)=0 THEN
   RAISE EXCEPTION 'Annual formats require the business year' USING ERRCODE='23514'; END IF;
 IF TG_OP='UPDATE' AND ROW(NEW.document_type,NEW.year,NEW.series,NEW.number_format,NEW.starting_value)
      IS DISTINCT FROM ROW(OLD.document_type,OLD.year,OLD.series,OLD.number_format,OLD.starting_value) THEN
   IF EXISTS(SELECT 1 FROM invoicing_invoice WHERE sequence_id=OLD.id AND status='FINALIZED')
      OR EXISTS(SELECT 1 FROM invoicing_creditnote WHERE sequence_id=OLD.id AND status='FINALIZED') THEN
     RAISE EXCEPTION 'Issued sequence configuration is immutable; use a new series' USING ERRCODE='23514'; END IF;
   NEW.verified_by_id:=NULL; NEW.verified_at:=NULL; NEW.verification_digest:=''; NEW.verification_evidence:='';
 END IF;
 IF TG_OP='UPDATE' AND NEW.next_counter<OLD.next_counter THEN
   RAISE EXCEPTION 'Sequence counters cannot move backwards' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER inv_sequence_configuration BEFORE INSERT OR UPDATE ON invoicing_documentsequence FOR EACH ROW EXECUTE FUNCTION inv_sequence_guard();
"""

REVERSE = """
DROP TRIGGER inv_sequence_configuration ON invoicing_documentsequence;
DROP FUNCTION inv_sequence_guard();
DROP TRIGGER inv_reference_append_only ON invoicing_finalreference;
DROP TABLE invoicing_finalreference;
DROP TRIGGER inv_artifact_append_only ON invoicing_documentartifact;
DROP TRIGGER inv_verification_append_only ON invoicing_companyverification;
DROP TRIGGER inv_audit_append_only ON invoicing_invoiceauditevent;
DROP TRIGGER inv_creditallocation_guard ON invoicing_creditallocation;
DROP TRIGGER inv_exclusion_guard ON invoicing_invoicereturnexclusion;
DROP TRIGGER inv_issue_guard ON invoicing_invoiceissueallocation;
DROP TRIGGER inv_line_guard ON invoicing_invoiceline;
DROP TRIGGER inv_credit_guard ON invoicing_creditnote;
DROP TRIGGER inv_invoice_guard ON invoicing_invoice;
DROP FUNCTION inv_child_guard(); DROP FUNCTION inv_document_guard(); DROP FUNCTION inv_fail();
"""


class Migration(migrations.Migration):
    dependencies = [("invoicing", "0001_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
