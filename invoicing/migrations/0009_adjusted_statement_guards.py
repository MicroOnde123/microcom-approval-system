from django.db import migrations

SQL = r"""
ALTER TABLE invoicing_finalreference DROP CONSTRAINT invoicing_finalreference_document_type_check;
ALTER TABLE invoicing_finalreference ADD CONSTRAINT invoicing_finalreference_document_type_check CHECK(document_type IN ('INVOICE','CREDIT','RETURN_NOTE','ADJUSTED'));
CREATE FUNCTION inv_as_snapshot(invoice_key bigint) RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE original invoicing_invoice; latest invoicing_materialreturnnote; lines jsonb; notes jsonb;
BEGIN
 SELECT * INTO original FROM invoicing_invoice WHERE id=invoice_key;
 IF original.status IS DISTINCT FROM 'FINALIZED' THEN RAISE EXCEPTION 'Finalized invoice required' USING ERRCODE='23514'; END IF;
 PERFORM inv_rn_validate(invoice_key);
 SELECT * INTO latest FROM invoicing_materialreturnnote WHERE invoice_id=invoice_key ORDER BY finalized_at DESC,id DESC LIMIT 1;
 SELECT jsonb_agg(jsonb_build_object('id',n.id,'number',n.number,'issue_date',n.issue_date::text,'issued_at',n.finalized_at::text,'total',n.total::text,
  'cumulative_returned_value',n.cumulative_returned_value::text,'adjusted_net_value',n.adjusted_net_value::text) ORDER BY n.finalized_at,n.id)
 INTO notes FROM invoicing_materialreturnnote n WHERE n.invoice_id=invoice_key AND n.status='FINALIZED';
 SELECT jsonb_agg(jsonb_build_object('id',l.id,'code',l.material_code_snapshot,'description',l.description_snapshot,'unit',l.unit_snapshot,
  'original_quantity',l.quantity::text,'returned_quantity',COALESCE(a.qty,0)::text,'net_quantity',(l.quantity-COALESCE(a.qty,0))::text,
  'unit_price',l.unit_price::text,'original_value',l.line_total::text,'returned_value',COALESCE(a.val,0)::text,
  'net_value',(l.line_total-COALESCE(a.val,0))::text,'return_movement_ids',COALESCE(a.movements,'[]'::jsonb)) ORDER BY l.position,l.id)
 INTO lines FROM invoicing_invoiceline l LEFT JOIN invoicing_invoiceissueallocation x ON x.line_id=l.id
 LEFT JOIN LATERAL (SELECT sum(b.quantity) qty,sum(b.line_total) val,jsonb_agg(b.return_movement_id ORDER BY b.id) movements
  FROM invoicing_materialreturnnoteline b JOIN invoicing_materialreturnnote n ON n.id=b.note_id
  WHERE b.issue_allocation_id=x.id AND n.invoice_id=invoice_key AND n.status='FINALIZED') a ON true WHERE l.invoice_id=invoice_key;
 IF lines IS NULL THEN RAISE EXCEPTION 'Invoice lines required' USING ERRCODE='23514'; END IF;
 RETURN jsonb_build_object('version',1,'invoice_id',original.id,'invoice_number',original.number,'invoice_date',original.issue_date::text,
  'request_reference',original.request_reference_snapshot,'company',original.company_snapshot,'branch',original.succursale_snapshot,
  'branding',original.branding_snapshot,'currency',original.currency,'timezone',original.business_timezone,
  'original_total',original.total::text,'returned_total',COALESCE(latest.cumulative_returned_value,0)::text,
  'net_total',COALESCE(latest.adjusted_net_value,original.total)::text,'lines',lines,'returns',COALESCE(notes,'[]'::jsonb));
END $$;
CREATE FUNCTION inv_as_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE original invoicing_invoice; seq invoicing_documentsequence; day date; expected jsonb;
BEGIN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Adjusted statements are immutable and retained' USING ERRCODE='23514'; END IF;
 IF current_setting('transaction_isolation')<>'read committed' THEN RAISE EXCEPTION 'READ COMMITTED required' USING ERRCODE='23514'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('microcom.credit:'||NEW.invoice_id::text,0));
 SELECT * INTO original FROM invoicing_invoice WHERE id=NEW.invoice_id FOR UPDATE;
 PERFORM 1 FROM requests_app_request WHERE id=original.request_id FOR UPDATE;
 expected:=inv_as_snapshot(original.id);
 IF NEW.snapshot IS DISTINCT FROM expected OR jsonb_array_length(expected->'returns')=0 THEN
  RAISE EXCEPTION 'Complete current issued BR snapshot required' USING ERRCODE='23514'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(expected->'lines') l WHERE (l->>'net_quantity')::numeric<0 OR (l->>'net_value')::numeric<0)
  OR (expected->>'net_total')::numeric<0 THEN RAISE EXCEPTION 'Negative adjusted statement prohibited' USING ERRCODE='23514'; END IF;
 IF NEW.issuer_name IS DISTINCT FROM (SELECT COALESCE(NULLIF(full_name,''),username) FROM accounts_user WHERE id=NEW.issued_by_id AND is_active)
  OR length(NEW.confirmation_digest)<>64 THEN RAISE EXCEPTION 'Issuer evidence required' USING ERRCODE='23514'; END IF;
 SELECT * INTO seq FROM invoicing_documentsequence WHERE id=NEW.sequence_id FOR UPDATE;
 IF seq.document_type IS DISTINCT FROM 'ADJUSTED' OR seq.verified_by_id IS NULL OR seq.verified_at IS NULL OR seq.verification_digest=''
  OR btrim(seq.verification_evidence)='' OR seq.next_counter<>NEW.sequence_counter+1 OR NEW.sequence_counter<seq.starting_value THEN
  RAISE EXCEPTION 'Verified advanced ADJUSTED sequence required' USING ERRCODE='23514'; END IF;
 IF abs(extract(epoch FROM (NEW.issued_at-statement_timestamp())))>5 THEN RAISE EXCEPTION 'Current issuance time required' USING ERRCODE='23514'; END IF;
 NEW.issued_at:=clock_timestamp();day:=(NEW.issued_at AT TIME ZONE original.business_timezone)::date;
 IF NEW.issue_date<>day OR seq.year<>extract(year FROM day)::int THEN RAISE EXCEPTION 'Current business date required' USING ERRCODE='23514'; END IF;
 INSERT INTO invoicing_finalreference VALUES(NEW.number,'ADJUSTED',NEW.id);
 RETURN NEW;
END $$;
CREATE TRIGGER as_immutable BEFORE INSERT OR UPDATE OR DELETE ON invoicing_adjustedinvoicestatement FOR EACH ROW EXECUTE FUNCTION inv_as_guard();
CREATE TRIGGER as_no_truncate BEFORE TRUNCATE ON invoicing_adjustedinvoicestatement FOR EACH STATEMENT EXECUTE FUNCTION inv_fail();
CREATE FUNCTION inv_as_sequence_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF EXISTS(SELECT 1 FROM invoicing_adjustedinvoicestatement WHERE sequence_id=OLD.id) AND
  ROW(NEW.document_type,NEW.year,NEW.series,NEW.number_format,NEW.starting_value) IS DISTINCT FROM
  ROW(OLD.document_type,OLD.year,OLD.series,OLD.number_format,OLD.starting_value) THEN
  RAISE EXCEPTION 'Issued adjusted sequence identity is immutable' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER aa_as_sequence BEFORE UPDATE ON invoicing_documentsequence FOR EACH ROW EXECUTE FUNCTION inv_as_sequence_guard();
"""

REVERSE = r"""
DO $$ BEGIN IF EXISTS(SELECT 1 FROM invoicing_adjustedinvoicestatement) THEN RAISE EXCEPTION 'Issued statements must be retained; reverse prohibited'; END IF; END $$;
DROP TRIGGER aa_as_sequence ON invoicing_documentsequence;
DROP FUNCTION inv_as_sequence_guard();
DROP TRIGGER as_no_truncate ON invoicing_adjustedinvoicestatement;
DROP TRIGGER as_immutable ON invoicing_adjustedinvoicestatement;
DROP FUNCTION inv_as_guard();
DROP FUNCTION inv_as_snapshot(bigint);
ALTER TABLE invoicing_finalreference DROP CONSTRAINT invoicing_finalreference_document_type_check;
ALTER TABLE invoicing_finalreference ADD CONSTRAINT invoicing_finalreference_document_type_check CHECK(document_type IN ('INVOICE','CREDIT','RETURN_NOTE'));
"""

class Migration(migrations.Migration):
    dependencies = [("invoicing", "0008_adjusted_invoice_statements")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
