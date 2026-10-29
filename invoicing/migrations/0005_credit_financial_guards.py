"""Credit-only guards. Invoice trigger functions from 0002 remain untouched."""
from django.db import migrations


SQL = r"""
CREATE FUNCTION inv_eb_operation(invoice_key bigint) RETURNS invoicing_creditoperation LANGUAGE plpgsql AS $$
DECLARE op invoicing_creditoperation;
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN
  RAISE EXCEPTION 'Credit writes require READ COMMITTED' USING ERRCODE='23514'; END IF;
 SELECT * INTO op FROM invoicing_creditoperation
 WHERE id=nullif(current_setting('microcom.credit_operation',true),'')::uuid
 AND invoice_id=invoice_key AND transaction_id=pg_current_xact_id()::text;
 IF NOT FOUND THEN RAISE EXCEPTION 'A current attributed credit operation is required' USING ERRCODE='23514'; END IF;
 RETURN op;
END $$;

CREATE FUNCTION inv_eb_operation_insert() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.kind NOT IN ('CREATE','RESERVE','REBALANCE','RELEASE','REVIEW','FINALIZE')
 OR btrim(NEW.reason)='' OR jsonb_typeof(NEW.payload)<>'object'
 OR NOT EXISTS(SELECT 1 FROM accounts_user WHERE id=NEW.actor_id AND is_active)
 OR NOT EXISTS(SELECT 1 FROM invoicing_invoice WHERE id=NEW.invoice_id AND status='FINALIZED') THEN
  RAISE EXCEPTION 'Valid credit operation attribution required' USING ERRCODE='23514'; END IF;
 -- Obtain this coordinator BEFORE credit row locks. It prevents cross-draft
 -- rebalancers from each holding one credit row while waiting on the other.
 PERFORM pg_advisory_xact_lock(hashtextextended('microcom.credit:'||NEW.invoice_id::text,0));
 NEW.transaction_id:=pg_current_xact_id()::text;
 NEW.created_at:=clock_timestamp();
 RETURN NEW;
END $$;
CREATE TRIGGER eb_operation_insert BEFORE INSERT ON invoicing_creditoperation FOR EACH ROW EXECUTE FUNCTION inv_eb_operation_insert();
CREATE TRIGGER eb_operation_frozen BEFORE UPDATE OR DELETE ON invoicing_creditoperation FOR EACH ROW EXECUTE FUNCTION inv_fail();
CREATE TRIGGER eb_audit_frozen BEFORE UPDATE OR DELETE ON invoicing_creditreservationaudit FOR EACH ROW EXECUTE FUNCTION inv_fail();
CREATE FUNCTION inv_eb_audit_insert() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF pg_trigger_depth()<2 THEN RAISE EXCEPTION 'Reservation audits are database generated' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER eb_audit_insert BEFORE INSERT ON invoicing_creditreservationaudit FOR EACH ROW EXECUTE FUNCTION inv_eb_audit_insert();

CREATE FUNCTION inv_eb_review_payload(credit_key bigint) RETURNS jsonb LANGUAGE sql STABLE AS $$
 SELECT jsonb_build_object('credit_note_id',c.id,'reservation_revision',c.reservation_revision,
  'allocations',COALESCE((SELECT jsonb_agg(jsonb_build_array(a.id,a.issue_allocation_id,a.return_movement_id,
      a.quantity,a.unit_price_snapshot,a.line_total) ORDER BY a.id)
    FROM invoicing_creditallocation a WHERE a.credit_note_id=c.id AND a.released_at IS NULL),'[]'::jsonb))
 FROM invoicing_creditnote c WHERE c.id=credit_key
$$;

CREATE FUNCTION inv_eb_snapshot_valid(c invoicing_creditnote) RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT c.company_snapshot=i.company_snapshot AND c.succursale_snapshot=i.succursale_snapshot
  AND c.branding_snapshot=i.branding_snapshot AND c.request_reference_snapshot=i.request_reference_snapshot
  AND c.currency=i.currency AND c.snapshot_version=2
  AND c.rounding_policy='CREDIT_CUMULATIVE_HALF_UP_2_V1'
  AND c.audit_metadata->'credit_snapshot'=jsonb_build_object('version',1,'invoice_number',i.number,
      'invoice_issue_date',i.issue_date::text,'invoice_rounding_policy',i.rounding_policy,'invoice_snapshot_version',i.snapshot_version)
 FROM invoicing_invoice i WHERE i.id=c.invoice_id AND i.status='FINALIZED'
$$;

CREATE FUNCTION inv_eb_header_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE op invoicing_creditoperation; inv invoicing_invoice; s invoicing_documentsequence; day date;
BEGIN
 IF TG_OP<>'INSERT' AND OLD.status='FINALIZED' THEN
  RAISE EXCEPTION 'Finalized financial documents are immutable' USING ERRCODE='23514'; END IF;
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Credit evidence cannot be deleted; release draft reservations explicitly' USING ERRCODE='23514'; END IF;
 op:=inv_eb_operation(NEW.invoice_id);
 IF TG_OP='UPDATE' AND (OLD.id<>NEW.id OR OLD.invoice_id<>NEW.invoice_id OR OLD.created_by_id<>NEW.created_by_id OR OLD.created_at<>NEW.created_at
    OR OLD.creation_operation_token IS DISTINCT FROM NEW.creation_operation_token) THEN
  RAISE EXCEPTION 'Credit parent and creation identity cannot be reassigned' USING ERRCODE='23514'; END IF;
 SELECT * INTO inv FROM invoicing_invoice WHERE id=NEW.invoice_id FOR UPDATE;
 IF inv.status<>'FINALIZED' OR NEW.currency<>inv.currency OR NEW.business_timezone<>'Africa/Kinshasa'
 OR NEW.business_timezone IS DISTINCT FROM (SELECT business_timezone FROM core_companydocumentsettings
   WHERE id=(SELECT configuration_id FROM invoicing_companyverification WHERE id=inv.company_verification_id)) THEN
  RAISE EXCEPTION 'Finalized original invoice, currency and business timezone required' USING ERRCODE='23514'; END IF;
 IF TG_OP='INSERT' THEN
  IF op.kind<>'CREATE' OR NEW.created_by_id<>op.actor_id OR NEW.status<>'DRAFT' OR NEW.reservation_revision<>0 OR NEW.reviewed_revision IS NOT NULL
    OR NEW.reviewed_at IS NOT NULL OR NEW.reviewed_by_id IS NOT NULL OR NEW.review_operation_id IS NOT NULL THEN
   RAISE EXCEPTION 'Credits must start as unreviewed drafts' USING ERRCODE='23514'; END IF;
  IF NEW.creation_operation_token IS NOT NULL AND
    op.payload->>'creation_token' IS DISTINCT FROM NEW.creation_operation_token::text THEN
   RAISE EXCEPTION 'Creation token must match operation payload' USING ERRCODE='23514'; END IF;
 ELSE
  IF NEW.reservation_revision<>OLD.reservation_revision THEN
   IF pg_trigger_depth()<2 OR NEW.reservation_revision<>OLD.reservation_revision+1
    OR NEW.reviewed_revision IS NOT NULL OR NEW.reviewed_at IS NOT NULL OR NEW.reviewed_by_id IS NOT NULL
    OR NEW.review_operation_id IS NOT NULL THEN
    RAISE EXCEPTION 'Reservation revisions are database managed' USING ERRCODE='23514'; END IF;
  ELSIF ROW(NEW.reviewed_revision,NEW.reviewed_by_id,NEW.reviewed_at,NEW.review_operation_id)
      IS DISTINCT FROM ROW(OLD.reviewed_revision,OLD.reviewed_by_id,OLD.reviewed_at,OLD.review_operation_id) THEN
   IF op.kind<>'REVIEW' OR NEW.review_operation_id IS DISTINCT FROM op.id
    OR NEW.reviewed_by_id IS DISTINCT FROM op.actor_id OR NEW.reviewed_revision IS DISTINCT FROM OLD.reservation_revision
    OR op.payload IS DISTINCT FROM inv_eb_review_payload(OLD.id)
    OR NOT EXISTS(SELECT 1 FROM invoicing_creditallocation WHERE credit_note_id=OLD.id AND released_at IS NULL) THEN
    RAISE EXCEPTION 'Explicit review of current reservation amounts required' USING ERRCODE='23514'; END IF;
   NEW.reviewed_at:=clock_timestamp();
  END IF;
 END IF;
 IF NEW.status='FINALIZED' THEN
  IF TG_OP='INSERT' OR op.kind<>'FINALIZE' OR NEW.finalized_by_id IS DISTINCT FROM op.actor_id
   OR NEW.reviewed_revision IS DISTINCT FROM NEW.reservation_revision OR NEW.review_operation_id IS NULL
   OR NEW.reviewed_by_id IS NULL OR NEW.reviewed_at IS NULL
   OR (SELECT payload FROM invoicing_creditoperation WHERE id=NEW.review_operation_id)
       IS DISTINCT FROM inv_eb_review_payload(NEW.id) THEN
   RAISE EXCEPTION 'Credit amounts changed or have not been explicitly reviewed' USING ERRCODE='23514'; END IF;
  IF inv_eb_snapshot_valid(NEW) IS DISTINCT FROM true OR NEW.amount_words_fr=''
    OR NOT EXISTS(SELECT 1 FROM invoicing_creditallocation WHERE credit_note_id=NEW.id AND released_at IS NULL)
    OR NEW.total IS DISTINCT FROM (SELECT sum(line_total) FROM invoicing_creditallocation WHERE credit_note_id=NEW.id AND released_at IS NULL)
    OR EXISTS(SELECT 1 FROM invoicing_creditallocation a JOIN invoicing_invoiceissueallocation x ON x.id=a.issue_allocation_id
       JOIN invoicing_invoiceline l ON l.id=x.line_id WHERE a.credit_note_id=NEW.id AND a.released_at IS NULL
       AND (a.description_snapshot IS DISTINCT FROM l.description_snapshot
        OR a.audit_metadata->'line_snapshot' IS DISTINCT FROM jsonb_build_object('version',1,
           'material_code',l.material_code_snapshot,'unit',l.unit_snapshot,'rounding_policy',l.rounding_policy))) THEN
   RAISE EXCEPTION 'Complete consistent frozen credit snapshots and totals required' USING ERRCODE='23514'; END IF;
  SELECT * INTO s FROM invoicing_documentsequence WHERE id=NEW.sequence_id FOR UPDATE;
  IF s.document_type IS DISTINCT FROM 'CREDIT' OR s.verified_by_id IS NULL OR s.verified_at IS NULL
   OR s.verification_digest='' OR s.verification_evidence='' THEN
   RAISE EXCEPTION 'Verified CREDIT sequence required' USING ERRCODE='23514'; END IF;
  IF NEW.finalized_at<statement_timestamp()-interval '5 seconds' OR NEW.finalized_at>statement_timestamp()+interval '5 seconds' THEN
   RAISE EXCEPTION 'Backdated or future finalization prohibited' USING ERRCODE='23514'; END IF;
  NEW.finalized_at:=clock_timestamp(); day:=(NEW.finalized_at AT TIME ZONE NEW.business_timezone)::date;
  IF NEW.issue_date IS DISTINCT FROM day OR s.year<>extract(year FROM day)::int THEN
   RAISE EXCEPTION 'Credit date and numbering must use the current business year' USING ERRCODE='23514'; END IF;
  INSERT INTO invoicing_finalreference(number,document_type,document_id) VALUES(NEW.number,'CREDIT',NEW.id);
 END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION inv_eb_allocation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE c invoicing_creditnote; l invoicing_invoiceline; x invoicing_invoiceissueallocation;
 inv invoicing_invoice; m requests_app_stockmovement; source requests_app_stockmovement; op invoicing_creditoperation;
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Credit allocations are retained; release drafts explicitly' USING ERRCODE='23514'; END IF;
 SELECT * INTO c FROM invoicing_creditnote WHERE id=NEW.credit_note_id FOR UPDATE;
 IF c.status='FINALIZED' OR (TG_OP='UPDATE' AND OLD.released_at IS NOT NULL) THEN
  RAISE EXCEPTION 'Finalized or released credit evidence is immutable' USING ERRCODE='23514'; END IF;
 op:=inv_eb_operation(c.invoice_id);
 IF op.kind NOT IN ('RESERVE','REBALANCE','RELEASE','FINALIZE') THEN
  RAISE EXCEPTION 'Attributed reservation adjustment required' USING ERRCODE='23514'; END IF;
 IF TG_OP='UPDATE' AND (OLD.id<>NEW.id OR OLD.credit_note_id<>NEW.credit_note_id OR OLD.issue_allocation_id<>NEW.issue_allocation_id
  OR OLD.return_movement_id<>NEW.return_movement_id) THEN
  RAISE EXCEPTION 'Credit allocation identity cannot be reassigned' USING ERRCODE='23514'; END IF;
 SELECT * INTO x FROM invoicing_invoiceissueallocation WHERE id=NEW.issue_allocation_id;
 SELECT * INTO l FROM invoicing_invoiceline WHERE id=x.line_id;
 SELECT * INTO inv FROM invoicing_invoice WHERE id=l.invoice_id FOR UPDATE;
 SELECT * INTO m FROM requests_app_stockmovement WHERE id=NEW.return_movement_id FOR UPDATE;
 SELECT * INTO source FROM requests_app_stockmovement WHERE id=x.out_movement_id;
 IF inv.id IS DISTINCT FROM c.invoice_id OR inv.status IS DISTINCT FROM 'FINALIZED'
  OR m.movement_type IS DISTINCT FROM 'RETURN' OR m.quantity<=0 OR source.movement_type IS DISTINCT FROM 'OUT' OR source.quantity<=0
  OR source.request_id IS DISTINCT FROM inv.request_id OR source.material_id IS DISTINCT FROM l.material_id
  OR m.request_id IS DISTINCT FROM source.request_id OR m.material_id IS DISTINCT FROM source.material_id
  OR m.created_at<=inv.finalized_at OR m.created_at>clock_timestamp() OR m.created_at<source.created_at
  OR EXISTS(SELECT 1 FROM invoicing_invoicereturnexclusion WHERE return_movement_id=m.id)
  OR NEW.unit_price_snapshot IS DISTINCT FROM l.unit_price OR c.currency<>inv.currency THEN
  RAISE EXCEPTION 'Return is not eligible for original invoice credit' USING ERRCODE='23514'; END IF;
 IF NEW.released_at IS NULL AND (
   NEW.quantity+COALESCE((SELECT sum(quantity) FROM invoicing_creditallocation WHERE return_movement_id=m.id
      AND released_at IS NULL AND id<>COALESCE(NEW.id,0)),0)>m.quantity
   OR NEW.quantity+COALESCE((SELECT sum(quantity) FROM invoicing_creditallocation WHERE issue_allocation_id=x.id
      AND released_at IS NULL AND id<>COALESCE(NEW.id,0)),0)>x.quantity) THEN
  RAISE EXCEPTION 'Credit exceeds eligible returned or invoiced quantity' USING ERRCODE='23514'; END IF;
 IF NEW.released_at IS NOT NULL THEN
  IF TG_OP='INSERT' OR op.kind<>'RELEASE' OR NEW.release_operation_id IS DISTINCT FROM op.id
   OR ROW(NEW.quantity,NEW.line_total,NEW.unit_price_snapshot,NEW.description_snapshot,NEW.audit_metadata)
       IS DISTINCT FROM ROW(OLD.quantity,OLD.line_total,OLD.unit_price_snapshot,OLD.description_snapshot,OLD.audit_metadata) THEN
   RAISE EXCEPTION 'Release must retain original reservation evidence' USING ERRCODE='23514'; END IF;
  NEW.released_at:=clock_timestamp();
 END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION inv_eb_adjustment_audit() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE op invoicing_creditoperation; invoice_key bigint; old_amount numeric; old_quantity numeric;
BEGIN
 IF TG_OP='INSERT' OR ROW(NEW.quantity,NEW.line_total,NEW.released_at,NEW.unit_price_snapshot,NEW.description_snapshot,NEW.audit_metadata)
     IS DISTINCT FROM ROW(OLD.quantity,OLD.line_total,OLD.released_at,OLD.unit_price_snapshot,OLD.description_snapshot,OLD.audit_metadata) THEN
  SELECT invoice_id INTO invoice_key FROM invoicing_creditnote WHERE id=NEW.credit_note_id;
  op:=inv_eb_operation(invoice_key);
  IF TG_OP='UPDATE' THEN old_amount:=OLD.line_total; old_quantity:=OLD.quantity; END IF;
  INSERT INTO invoicing_creditreservationaudit(allocation_id,operation_id,previous_amount,new_amount,previous_quantity,new_quantity,created_at)
   VALUES(NEW.id,op.id,old_amount,CASE WHEN NEW.released_at IS NULL THEN NEW.line_total ELSE 0 END,
     old_quantity,CASE WHEN NEW.released_at IS NULL THEN NEW.quantity ELSE 0 END,clock_timestamp());
  UPDATE invoicing_creditnote SET reservation_revision=reservation_revision+1,
   reviewed_revision=NULL,reviewed_at=NULL,reviewed_by_id=NULL,review_operation_id=NULL WHERE id=NEW.credit_note_id;
 END IF;
 RETURN NULL;
END $$;

CREATE FUNCTION inv_eb_validate_ledger(invoice_key bigint) RETURNS void LANGUAGE plpgsql AS $$
DECLARE l record; a record; q numeric; value numeric; expected numeric; m record;
BEGIN
 -- Coordinator lock is acquired at operation creation, before any row writes.
 -- This function also serves the read-only historical migration preflight.
 IF EXISTS(SELECT 1 FROM invoicing_creditallocation ca JOIN invoicing_creditnote c ON c.id=ca.credit_note_id
   JOIN invoicing_invoiceissueallocation x ON x.id=ca.issue_allocation_id JOIN invoicing_invoiceline original_line ON original_line.id=x.line_id
   WHERE c.invoice_id=invoice_key AND (original_line.invoice_id<>c.invoice_id OR original_line.currency<>c.currency)) THEN
  RAISE EXCEPTION 'Credit ledger parent or currency is inconsistent' USING ERRCODE='23514'; END IF;
 FOR l IN SELECT line.*,x.id AS allocation_id,x.quantity AS billed,x.out_movement_id
   FROM invoicing_invoiceline line JOIN invoicing_invoiceissueallocation x ON x.line_id=line.id
   WHERE line.invoice_id=invoice_key ORDER BY line.id LOOP
  q:=0; value:=0;
  FOR a IN SELECT ca.*,c.status,c.finalized_at FROM invoicing_creditallocation ca
    JOIN invoicing_creditnote c ON c.id=ca.credit_note_id
    WHERE ca.issue_allocation_id=l.allocation_id AND ca.released_at IS NULL
    ORDER BY CASE WHEN c.status='FINALIZED' THEN 0 ELSE 1 END,
      CASE WHEN c.status='FINALIZED' THEN c.finalized_at ELSE 'infinity'::timestamptz END,c.id,ca.id LOOP
   IF a.quantity<=0 OR a.unit_price_snapshot IS DISTINCT FROM l.unit_price THEN
    RAISE EXCEPTION 'Invalid credit quantity or frozen price' USING ERRCODE='23514'; END IF;
   expected:=least(l.line_total,round((q+a.quantity)*l.unit_price,2))-value;
   q:=q+a.quantity; value:=value+a.line_total;
   IF q>l.billed OR a.line_total<>expected OR a.line_total<0 OR value>l.line_total THEN
    RAISE EXCEPTION 'Credit ledger requires complete cumulative rebalance within invoice caps' USING ERRCODE='23514'; END IF;
   SELECT * INTO m FROM requests_app_stockmovement WHERE id=a.return_movement_id;
   IF m.movement_type IS DISTINCT FROM 'RETURN' OR m.quantity<=0
    OR m.request_id IS DISTINCT FROM (SELECT request_id FROM invoicing_invoice WHERE id=invoice_key)
    OR m.material_id IS DISTINCT FROM l.material_id
    OR m.created_at<=(SELECT finalized_at FROM invoicing_invoice WHERE id=invoice_key)
    OR m.created_at>clock_timestamp()
    OR EXISTS(SELECT 1 FROM invoicing_invoicereturnexclusion WHERE return_movement_id=m.id)
    OR (SELECT sum(quantity) FROM invoicing_creditallocation WHERE return_movement_id=m.id AND released_at IS NULL)>m.quantity THEN
    RAISE EXCEPTION 'Credit ledger exceeds or mismatches eligible return evidence' USING ERRCODE='23514'; END IF;
  END LOOP;
  IF q>0 AND ((SELECT count(*) FROM requests_app_stockmovement WHERE request_id=(SELECT request_id FROM invoicing_invoice WHERE id=invoice_key)
       AND material_id=l.material_id AND movement_type='OUT')<>1
   OR NOT EXISTS(SELECT 1 FROM requests_app_stockmovement WHERE id=l.out_movement_id AND movement_type='OUT'
      AND quantity=l.billed+COALESCE((SELECT sum(quantity) FROM invoicing_invoicereturnexclusion WHERE issue_allocation_id=l.allocation_id),0))
   OR (SELECT count(*) FROM requests_app_requestmaterialitem WHERE request_id=(SELECT request_id FROM invoicing_invoice WHERE id=invoice_key)
       AND material_id=l.material_id)<>1
   OR NOT EXISTS(SELECT 1 FROM requests_app_requestmaterialitem WHERE request_id=(SELECT request_id FROM invoicing_invoice WHERE id=invoice_key)
       AND material_id=l.material_id AND quantity=l.billed+COALESCE((SELECT sum(quantity) FROM invoicing_invoicereturnexclusion WHERE issue_allocation_id=l.allocation_id),0))
   OR EXISTS(SELECT 1 FROM requests_app_stockmovement WHERE request_id=(SELECT request_id FROM invoicing_invoice WHERE id=invoice_key)
       AND material_id=l.material_id AND movement_type='RETURN' AND quantity<=0)
   OR COALESCE((SELECT sum(quantity) FROM requests_app_stockmovement WHERE request_id=(SELECT request_id FROM invoicing_invoice WHERE id=invoice_key)
       AND material_id=l.material_id AND movement_type='RETURN'),0)>(SELECT quantity FROM requests_app_stockmovement WHERE id=l.out_movement_id)
   OR EXISTS(SELECT 1 FROM invoicing_invoicereturnexclusion e JOIN requests_app_stockmovement excluded ON excluded.id=e.return_movement_id
       WHERE e.issue_allocation_id=l.allocation_id AND (excluded.movement_type<>'RETURN' OR excluded.quantity<>e.quantity))) THEN
    RAISE EXCEPTION 'Original issue attribution is ambiguous' USING ERRCODE='23514'; END IF;
 END LOOP;
 IF EXISTS(SELECT 1 FROM invoicing_creditnote c WHERE c.invoice_id=invoice_key AND c.total IS NOT NULL
   AND c.total IS DISTINCT FROM COALESCE((SELECT sum(line_total) FROM invoicing_creditallocation WHERE credit_note_id=c.id AND released_at IS NULL),0)) THEN
  RAISE EXCEPTION 'Credit header total does not match active allocations' USING ERRCODE='23514'; END IF;
END $$;

CREATE FUNCTION inv_eb_deferred_check() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE invoice_key bigint;
BEGIN
 IF TG_TABLE_NAME='invoicing_creditnote' THEN invoice_key:=NEW.invoice_id;
 ELSE SELECT invoice_id INTO invoice_key FROM invoicing_creditnote WHERE id=NEW.credit_note_id; END IF;
 PERFORM inv_eb_validate_ledger(invoice_key);
 RETURN NULL;
END $$;

DROP TRIGGER inv_credit_guard ON invoicing_creditnote;
CREATE TRIGGER inv_credit_guard BEFORE INSERT OR UPDATE OR DELETE ON invoicing_creditnote FOR EACH ROW EXECUTE FUNCTION inv_eb_header_guard();
DROP TRIGGER inv_creditallocation_guard ON invoicing_creditallocation;
CREATE TRIGGER inv_creditallocation_guard BEFORE INSERT OR UPDATE OR DELETE ON invoicing_creditallocation FOR EACH ROW EXECUTE FUNCTION inv_eb_allocation_guard();
CREATE TRIGGER eb_adjustment_audit AFTER INSERT OR UPDATE ON invoicing_creditallocation FOR EACH ROW EXECUTE FUNCTION inv_eb_adjustment_audit();
CREATE CONSTRAINT TRIGGER eb_credit_ledger AFTER INSERT OR UPDATE ON invoicing_creditnote
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION inv_eb_deferred_check();
CREATE CONSTRAINT TRIGGER eb_allocation_ledger AFTER INSERT OR UPDATE ON invoicing_creditallocation
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION inv_eb_deferred_check();

-- Evaluate existing synthetic/authorized credit ledgers without rewriting them.
DO $$ DECLARE r record; BEGIN
 FOR r IN SELECT DISTINCT invoice_id FROM invoicing_creditnote LOOP
  PERFORM inv_eb_validate_ledger(r.invoice_id);
 END LOOP;
END $$;
"""

REVERSE = r"""
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM invoicing_creditoperation) OR EXISTS(SELECT 1 FROM invoicing_creditreservationaudit) THEN
  RAISE EXCEPTION 'E-B evidence exists: use a reviewed forward correction, not guard rollback'; END IF;
END $$;
DROP TRIGGER eb_allocation_ledger ON invoicing_creditallocation;
DROP TRIGGER eb_credit_ledger ON invoicing_creditnote;
DROP TRIGGER eb_adjustment_audit ON invoicing_creditallocation;
DROP TRIGGER inv_creditallocation_guard ON invoicing_creditallocation;
CREATE TRIGGER inv_creditallocation_guard BEFORE INSERT OR UPDATE OR DELETE ON invoicing_creditallocation FOR EACH ROW EXECUTE FUNCTION inv_child_guard();
DROP TRIGGER inv_credit_guard ON invoicing_creditnote;
CREATE TRIGGER inv_credit_guard BEFORE INSERT OR UPDATE OR DELETE ON invoicing_creditnote FOR EACH ROW EXECUTE FUNCTION inv_document_guard();
DROP TRIGGER eb_audit_insert ON invoicing_creditreservationaudit;
DROP TRIGGER eb_audit_frozen ON invoicing_creditreservationaudit;
DROP TRIGGER eb_operation_frozen ON invoicing_creditoperation;
DROP TRIGGER eb_operation_insert ON invoicing_creditoperation;
DROP FUNCTION inv_eb_deferred_check();
DROP FUNCTION inv_eb_validate_ledger(bigint);
DROP FUNCTION inv_eb_adjustment_audit();
DROP FUNCTION inv_eb_allocation_guard();
DROP FUNCTION inv_eb_header_guard();
DROP FUNCTION inv_eb_snapshot_valid(invoicing_creditnote);
DROP FUNCTION inv_eb_review_payload(bigint);
DROP FUNCTION inv_eb_audit_insert();
DROP FUNCTION inv_eb_operation_insert();
DROP FUNCTION inv_eb_operation(bigint);
"""


class Migration(migrations.Migration):
    dependencies = [("invoicing", "0004_credit_reservation_schema")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
