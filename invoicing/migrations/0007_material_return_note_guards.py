"""Return-note guards only; prior E-B functions and migrations are untouched."""
from django.db import migrations


SQL = r"""
ALTER TABLE invoicing_finalreference ALTER COLUMN document_type TYPE varchar(11);
ALTER TABLE invoicing_finalreference DROP CONSTRAINT invoicing_finalreference_document_type_check;
ALTER TABLE invoicing_finalreference ADD CONSTRAINT invoicing_finalreference_document_type_check
 CHECK(document_type IN ('INVOICE','CREDIT','RETURN_NOTE'));

CREATE FUNCTION inv_rn_exclusive(invoice_key bigint, ledger text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN
  RAISE EXCEPTION 'Return documentation requires READ COMMITTED' USING ERRCODE='23514'; END IF;
 -- Same coordinator as E-B, always before document row locks. Volatile SQL
 -- statements after the wait see the winner's committed evidence at RC.
 PERFORM pg_advisory_xact_lock(hashtextextended('microcom.credit:'||invoice_key::text,0));
 IF ledger='RETURN_NOTE' AND EXISTS(SELECT 1 FROM invoicing_creditallocation a
   JOIN invoicing_creditnote c ON c.id=a.credit_note_id WHERE c.invoice_id=invoice_key AND a.released_at IS NULL)
 OR ledger='CREDIT' AND EXISTS(SELECT 1 FROM invoicing_materialreturnnote WHERE invoice_id=invoice_key) THEN
  RAISE EXCEPTION 'Invoice financial ledgers are exclusive; administrator review required' USING ERRCODE='23514'; END IF;
END $$;

CREATE FUNCTION inv_rn_credit_exclusive() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE invoice_key bigint; op invoicing_creditoperation;
BEGIN
 SELECT invoice_id INTO invoice_key FROM invoicing_creditnote WHERE id=NEW.credit_note_id;
 -- Enforce E-B attribution before its allocation trigger takes credit row locks.
 op:=inv_eb_operation(invoice_key);
 IF NEW.released_at IS NULL THEN PERFORM inv_rn_exclusive(invoice_key,'CREDIT'); END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER aa_rn_credit_exclusive BEFORE INSERT OR UPDATE ON invoicing_creditallocation
 FOR EACH ROW EXECUTE FUNCTION inv_rn_credit_exclusive();

CREATE FUNCTION inv_rn_operation_insert() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM inv_rn_exclusive(NEW.invoice_id,'RETURN_NOTE');
 IF btrim(NEW.reason)='' OR jsonb_typeof(NEW.payload) IS DISTINCT FROM 'object'
 OR NOT EXISTS(SELECT 1 FROM accounts_user WHERE id=NEW.actor_id AND is_active)
 OR NOT EXISTS(SELECT 1 FROM invoicing_invoice WHERE id=NEW.invoice_id AND status='FINALIZED') THEN
  RAISE EXCEPTION 'Valid return note attribution and finalized invoice required' USING ERRCODE='23514'; END IF;
 NEW.transaction_id:=pg_current_xact_id()::text; NEW.created_at:=clock_timestamp();
 RETURN NEW;
END $$;
CREATE TRIGGER rn_operation_insert BEFORE INSERT ON invoicing_materialreturnnoteaudit
 FOR EACH ROW EXECUTE FUNCTION inv_rn_operation_insert();
CREATE TRIGGER rn_operation_frozen BEFORE UPDATE OR DELETE ON invoicing_materialreturnnoteaudit
 FOR EACH ROW EXECUTE FUNCTION inv_fail();

CREATE FUNCTION inv_rn_operation(operation_key uuid, invoice_key bigint) RETURNS invoicing_materialreturnnoteaudit LANGUAGE plpgsql AS $$
DECLARE op invoicing_materialreturnnoteaudit;
BEGIN
 SELECT * INTO op FROM invoicing_materialreturnnoteaudit WHERE id=operation_key
 AND invoice_id=invoice_key AND transaction_id=pg_current_xact_id()::text;
 IF NOT FOUND THEN RAISE EXCEPTION 'A current return note operation is required' USING ERRCODE='23514'; END IF;
 PERFORM inv_rn_exclusive(invoice_key,'RETURN_NOTE');
 RETURN op;
END $$;

CREATE FUNCTION inv_rn_header_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE op invoicing_materialreturnnoteaudit; original invoicing_invoice; seq invoicing_documentsequence; day date;
BEGIN
 IF TG_OP='DELETE' OR (TG_OP='UPDATE' AND OLD.status='FINALIZED') THEN
  RAISE EXCEPTION 'Return notes are retained and issued notes are immutable' USING ERRCODE='23514'; END IF;
 op:=inv_rn_operation(NEW.operation_id,NEW.invoice_id);
 SELECT * INTO original FROM invoicing_invoice WHERE id=NEW.invoice_id FOR UPDATE;
 PERFORM 1 FROM requests_app_request WHERE id=original.request_id FOR UPDATE;
 IF original.status IS DISTINCT FROM 'FINALIZED' OR NEW.currency IS DISTINCT FROM original.currency
 OR NEW.business_timezone<>'Africa/Kinshasa' OR NEW.created_by_id<>op.actor_id
 OR (NEW.issuance_operation_token IS NOT NULL AND op.payload->>'issuance_token' IS DISTINCT FROM NEW.issuance_operation_token::text) THEN
  RAISE EXCEPTION 'Finalized invoice, original currency and attributed token required' USING ERRCODE='23514'; END IF;
 IF TG_OP='INSERT' THEN
  IF NEW.status<>'DRAFT' THEN RAISE EXCEPTION 'Build return note evidence before issuance' USING ERRCODE='23514'; END IF;
  NEW.created_at:=clock_timestamp();
 ELSIF ROW(OLD.id,OLD.invoice_id,OLD.operation_id,OLD.issuance_operation_token,OLD.created_by_id,OLD.created_at)
   IS DISTINCT FROM ROW(NEW.id,NEW.invoice_id,NEW.operation_id,NEW.issuance_operation_token,NEW.created_by_id,NEW.created_at) THEN
  RAISE EXCEPTION 'Return note identity is immutable' USING ERRCODE='23514'; END IF;
 IF NEW.status='FINALIZED' THEN
  IF NEW.finalized_by_id IS DISTINCT FROM op.actor_id OR NEW.company_snapshot IS DISTINCT FROM original.company_snapshot
   OR NEW.succursale_snapshot IS DISTINCT FROM original.succursale_snapshot OR NEW.branding_snapshot IS DISTINCT FROM original.branding_snapshot
   OR NEW.request_reference_snapshot IS DISTINCT FROM original.request_reference_snapshot
   OR NEW.original_invoice_snapshot IS DISTINCT FROM jsonb_build_object('version',1,'number',original.number,
      'issue_date',original.issue_date::text,'total',original.total::text,'currency',original.currency,
      'request_reference',original.request_reference_snapshot,'snapshot_version',original.snapshot_version,'rounding_policy',original.rounding_policy)
   OR NEW.rounding_policy<>'RETURN_CUMULATIVE_HALF_UP_2_V1' OR NEW.snapshot_version<>1 OR btrim(NEW.amount_words_fr)='' THEN
   RAISE EXCEPTION 'Return note snapshots must match the original finalized invoice' USING ERRCODE='23514'; END IF;
  SELECT * INTO seq FROM invoicing_documentsequence WHERE id=NEW.sequence_id FOR UPDATE;
  IF seq.document_type IS DISTINCT FROM 'RETURN_NOTE' OR seq.verified_by_id IS NULL OR seq.verified_at IS NULL
   OR seq.verification_digest='' OR btrim(seq.verification_evidence)='' OR NEW.sequence_counter<seq.starting_value THEN
   RAISE EXCEPTION 'Verified RETURN_NOTE sequence required' USING ERRCODE='23514'; END IF;
  IF NEW.finalized_at<statement_timestamp()-interval '5 seconds' OR NEW.finalized_at>statement_timestamp()+interval '5 seconds' THEN
   RAISE EXCEPTION 'Backdated or future issuance prohibited' USING ERRCODE='23514'; END IF;
  NEW.finalized_at:=clock_timestamp(); day:=(NEW.finalized_at AT TIME ZONE NEW.business_timezone)::date;
  IF NEW.issue_date IS DISTINCT FROM day OR seq.year<>extract(year FROM day)::int THEN
   RAISE EXCEPTION 'Return note numbering must use the current business year' USING ERRCODE='23514'; END IF;
  INSERT INTO invoicing_finalreference VALUES(NEW.number,'RETURN_NOTE',NEW.id);
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER rn_header_guard BEFORE INSERT OR UPDATE OR DELETE ON invoicing_materialreturnnote
 FOR EACH ROW EXECUTE FUNCTION inv_rn_header_guard();

CREATE FUNCTION inv_rn_line_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE note invoicing_materialreturnnote; op invoicing_materialreturnnoteaudit;
BEGIN
 -- All line evidence is append-only, including transaction-local construction.
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Return note lines are append-only' USING ERRCODE='23514'; END IF;
 SELECT * INTO note FROM invoicing_materialreturnnote WHERE id=NEW.note_id;
 op:=inv_rn_operation(note.operation_id,note.invoice_id);
 SELECT * INTO note FROM invoicing_materialreturnnote WHERE id=NEW.note_id FOR UPDATE;
 IF note.status<>'DRAFT' THEN RAISE EXCEPTION 'Issued return note lines are immutable' USING ERRCODE='23514'; END IF;
 PERFORM 1 FROM requests_app_stockmovement WHERE id=NEW.return_movement_id FOR UPDATE;
 RETURN NEW;
END $$;
CREATE TRIGGER rn_line_guard BEFORE INSERT OR UPDATE OR DELETE ON invoicing_materialreturnnoteline
 FOR EACH ROW EXECUTE FUNCTION inv_rn_line_guard();

CREATE FUNCTION inv_rn_validate(invoice_key bigint) RETURNS void LANGUAGE plpgsql AS $$
DECLARE original invoicing_invoice; line record; allocation record; movement requests_app_stockmovement;
 source requests_app_stockmovement; note record; q numeric; value numeric; expected numeric; cumulative numeric:=0;
BEGIN
 PERFORM inv_rn_exclusive(invoice_key,'RETURN_NOTE');
 SELECT * INTO original FROM invoicing_invoice WHERE id=invoice_key;
 IF original.status IS DISTINCT FROM 'FINALIZED' THEN RAISE EXCEPTION 'Finalized original required' USING ERRCODE='23514'; END IF;
 FOR note IN SELECT * FROM invoicing_materialreturnnote WHERE invoice_id=invoice_key ORDER BY finalized_at,id LOOP
  IF note.status<>'FINALIZED' OR NOT EXISTS(SELECT 1 FROM invoicing_materialreturnnoteline WHERE note_id=note.id)
    OR note.total IS DISTINCT FROM (SELECT sum(line_total) FROM invoicing_materialreturnnoteline WHERE note_id=note.id) THEN
   RAISE EXCEPTION 'Return note construction must complete atomically before commit' USING ERRCODE='23514'; END IF;
  cumulative:=cumulative+note.total;
  IF cumulative>original.total OR note.cumulative_returned_value<>cumulative OR note.adjusted_net_value<>original.total-cumulative THEN
   RAISE EXCEPTION 'Invalid cumulative return note totals' USING ERRCODE='23514'; END IF;
 END LOOP;
 FOR line IN SELECT l.*,x.id AS allocation_id,x.quantity AS billed,x.out_movement_id
   FROM invoicing_invoiceline l JOIN invoicing_invoiceissueallocation x ON x.line_id=l.id WHERE l.invoice_id=invoice_key LOOP
  q:=0; value:=0;
  FOR allocation IN SELECT a.* FROM invoicing_materialreturnnoteline a JOIN invoicing_materialreturnnote n ON n.id=a.note_id
   WHERE a.issue_allocation_id=line.allocation_id AND n.invoice_id=invoice_key ORDER BY n.finalized_at,n.id,a.id LOOP
   SELECT * INTO movement FROM requests_app_stockmovement WHERE id=allocation.return_movement_id;
   SELECT * INTO source FROM requests_app_stockmovement WHERE id=line.out_movement_id;
   expected:=least(line.line_total,round((q+allocation.quantity)*line.unit_price,2))-value;
   q:=q+allocation.quantity; value:=value+allocation.line_total;
   IF movement.movement_type IS DISTINCT FROM 'RETURN' OR movement.quantity<=0 OR allocation.quantity<>movement.quantity
    OR movement.request_id IS DISTINCT FROM original.request_id OR movement.material_id IS DISTINCT FROM line.material_id
    OR movement.created_at<=original.finalized_at OR movement.created_at>clock_timestamp() OR movement.created_at<source.created_at
    OR EXISTS(SELECT 1 FROM invoicing_invoicereturnexclusion WHERE return_movement_id=movement.id)
    OR source.movement_type IS DISTINCT FROM 'OUT' OR source.quantity<=0 OR source.request_id IS DISTINCT FROM original.request_id
    OR source.material_id IS DISTINCT FROM line.material_id
    OR source.quantity IS DISTINCT FROM line.billed+COALESCE((SELECT sum(quantity) FROM invoicing_invoicereturnexclusion WHERE issue_allocation_id=line.allocation_id),0)
    OR allocation.unit_price_snapshot IS DISTINCT FROM line.unit_price OR allocation.material_code_snapshot IS DISTINCT FROM line.material_code_snapshot
    OR allocation.description_snapshot IS DISTINCT FROM line.description_snapshot OR allocation.unit_snapshot IS DISTINCT FROM line.unit_snapshot
    OR q>line.billed OR allocation.line_total IS DISTINCT FROM expected OR value>line.line_total THEN
    RAISE EXCEPTION 'Invalid return attribution, frozen valuation or quantity cap' USING ERRCODE='23514'; END IF;
   IF (SELECT count(*) FROM requests_app_requestmaterialitem WHERE request_id=original.request_id AND material_id=line.material_id)<>1
    OR NOT EXISTS(SELECT 1 FROM requests_app_requestmaterialitem WHERE request_id=original.request_id AND material_id=line.material_id AND quantity=source.quantity)
    OR (SELECT count(*) FROM requests_app_stockmovement WHERE request_id=original.request_id AND material_id=line.material_id AND movement_type='OUT')<>1
    OR EXISTS(SELECT 1 FROM requests_app_stockmovement WHERE request_id=original.request_id AND material_id=line.material_id AND movement_type='RETURN' AND (quantity<=0 OR created_at<source.created_at))
    OR COALESCE((SELECT sum(quantity) FROM requests_app_stockmovement WHERE request_id=original.request_id AND material_id=line.material_id AND movement_type='RETURN'),0)>source.quantity
    OR EXISTS(SELECT 1 FROM invoicing_invoicereturnexclusion e JOIN requests_app_stockmovement m ON m.id=e.return_movement_id
      WHERE e.issue_allocation_id=line.allocation_id AND (m.quantity<>e.quantity OR m.movement_type<>'RETURN' OR m.request_id IS DISTINCT FROM original.request_id OR m.material_id IS DISTINCT FROM line.material_id)) THEN
    RAISE EXCEPTION 'Ambiguous historical stock evidence; administrator review required' USING ERRCODE='23514'; END IF;
  END LOOP;
 END LOOP;
 IF EXISTS(SELECT 1 FROM invoicing_materialreturnnoteline a JOIN invoicing_materialreturnnote n ON n.id=a.note_id
  JOIN invoicing_invoiceissueallocation x ON x.id=a.issue_allocation_id JOIN invoicing_invoiceline l ON l.id=x.line_id
  WHERE n.invoice_id=invoice_key AND l.invoice_id<>invoice_key) THEN
  RAISE EXCEPTION 'Return note line belongs to another invoice' USING ERRCODE='23514'; END IF;
END $$;

CREATE FUNCTION inv_rn_deferred() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE invoice_key bigint;
BEGIN
 IF TG_TABLE_NAME='invoicing_materialreturnnote' THEN invoice_key:=NEW.invoice_id;
 ELSE SELECT invoice_id INTO invoice_key FROM invoicing_materialreturnnote WHERE id=NEW.note_id; END IF;
 PERFORM inv_rn_validate(invoice_key); RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER rn_header_ledger AFTER INSERT OR UPDATE ON invoicing_materialreturnnote
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION inv_rn_deferred();
CREATE CONSTRAINT TRIGGER rn_line_ledger AFTER INSERT ON invoicing_materialreturnnoteline
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION inv_rn_deferred();

CREATE FUNCTION inv_rn_artifact_insert() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM invoicing_materialreturnnote WHERE id=NEW.note_id AND status='FINALIZED') THEN
  RAISE EXCEPTION 'Artifacts require issued return notes' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER rn_artifact_insert BEFORE INSERT ON invoicing_materialreturnnoteartifact FOR EACH ROW EXECUTE FUNCTION inv_rn_artifact_insert();
CREATE TRIGGER rn_artifact_frozen BEFORE UPDATE OR DELETE ON invoicing_materialreturnnoteartifact FOR EACH ROW EXECUTE FUNCTION inv_fail();

-- Add a preceding sequence guard; retain the existing sequence guard unchanged.
CREATE FUNCTION inv_rn_sequence_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='UPDATE' AND ROW(NEW.document_type,NEW.year,NEW.series,NEW.number_format,NEW.starting_value)
  IS DISTINCT FROM ROW(OLD.document_type,OLD.year,OLD.series,OLD.number_format,OLD.starting_value)
  AND EXISTS(SELECT 1 FROM invoicing_materialreturnnote WHERE sequence_id=OLD.id AND status='FINALIZED') THEN
  RAISE EXCEPTION 'Issued return note sequence is immutable' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER aa_rn_sequence_guard BEFORE UPDATE ON invoicing_documentsequence FOR EACH ROW EXECUTE FUNCTION inv_rn_sequence_guard();

DO $$ DECLARE r record; BEGIN
 FOR r IN SELECT DISTINCT invoice_id FROM invoicing_materialreturnnote LOOP
  PERFORM inv_rn_validate(r.invoice_id);
 END LOOP;
END $$;
"""

REVERSE = r"""
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM invoicing_materialreturnnoteaudit)
 OR EXISTS(SELECT 1 FROM invoicing_materialreturnnote)
 OR EXISTS(SELECT 1 FROM invoicing_documentsequence WHERE document_type='RETURN_NOTE') THEN
  RAISE EXCEPTION 'E-R1 evidence/configuration exists: use a reviewed forward correction'; END IF;
END $$;
DROP TRIGGER aa_rn_sequence_guard ON invoicing_documentsequence;
DROP FUNCTION inv_rn_sequence_guard();
DROP TRIGGER rn_artifact_frozen ON invoicing_materialreturnnoteartifact;
DROP TRIGGER rn_artifact_insert ON invoicing_materialreturnnoteartifact;
DROP FUNCTION inv_rn_artifact_insert();
DROP TRIGGER rn_line_ledger ON invoicing_materialreturnnoteline;
DROP TRIGGER rn_header_ledger ON invoicing_materialreturnnote;
DROP FUNCTION inv_rn_deferred();
DROP FUNCTION inv_rn_validate(bigint);
DROP TRIGGER rn_line_guard ON invoicing_materialreturnnoteline;
DROP FUNCTION inv_rn_line_guard();
DROP TRIGGER rn_header_guard ON invoicing_materialreturnnote;
DROP FUNCTION inv_rn_header_guard();
DROP FUNCTION inv_rn_operation(uuid,bigint);
DROP TRIGGER rn_operation_frozen ON invoicing_materialreturnnoteaudit;
DROP TRIGGER rn_operation_insert ON invoicing_materialreturnnoteaudit;
DROP FUNCTION inv_rn_operation_insert();
DROP TRIGGER aa_rn_credit_exclusive ON invoicing_creditallocation;
DROP FUNCTION inv_rn_credit_exclusive();
DROP FUNCTION inv_rn_exclusive(bigint,text);
ALTER TABLE invoicing_finalreference DROP CONSTRAINT invoicing_finalreference_document_type_check;
ALTER TABLE invoicing_finalreference ADD CONSTRAINT invoicing_finalreference_document_type_check CHECK(document_type IN ('INVOICE','CREDIT'));
ALTER TABLE invoicing_finalreference ALTER COLUMN document_type TYPE varchar(10);
"""


class Migration(migrations.Migration):
    dependencies = [("invoicing", "0006_material_return_note_schema")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
