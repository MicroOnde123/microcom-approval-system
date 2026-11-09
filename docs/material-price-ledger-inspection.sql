-- READ ONLY. Run as the intended migration/inspection principal, never paste
-- passwords. No role names, grants, ownership changes or data writes are assumed.
-- Repeat identity and effective-rights checks using the Django backend connection.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';

-- 1. Identity/schema; application settings source DB_USER from the environment.
SELECT current_database(), session_user, current_user,
       current_schema(), current_setting('search_path') AS search_path;

-- 2. Principals and memberships (no password catalogs are queried).
SELECT rolname, rolcanlogin, rolsuper, rolinherit, rolcreaterole,
       rolcreatedb, rolreplication, rolbypassrls
FROM pg_roles ORDER BY rolname;
SELECT parent.rolname AS granted_role, member.rolname AS member,
       m.admin_option,
       to_jsonb(m)->>'inherit_option' AS inherit_option,
       to_jsonb(m)->>'set_option' AS set_option
FROM pg_auth_members m
JOIN pg_roles parent ON parent.oid=m.roleid
JOIN pg_roles member ON member.oid=m.member
ORDER BY 1,2;

-- 3. Existing ownership/schema ACLs. The ledger is absent before applying 0007.
-- Unexpected same-named objects in another schema require investigation.
SELECT n.nspname AS schema_name, pg_get_userbyid(n.nspowner) AS schema_owner,
       n.nspacl, c.relname, c.relkind, pg_get_userbyid(c.relowner) AS object_owner,
       c.relacl, c.relrowsecurity, c.relforcerowsecurity
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE c.relname IN ('inventory_material','inventory_materialpricechange',
                    'inventory_materialpricechange_id_seq')
ORDER BY n.nspname,c.relname;

-- 4. Creator-scoped defaults: global and schema-specific defaults both matter.
-- defaclobjtype: r=tables, S=sequences, f=functions, n=schemas.
SELECT pg_get_userbyid(d.defaclrole) AS creator_role,
       COALESCE(n.nspname,'ALL SCHEMAS') AS schema_name, d.defaclobjtype,
       CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS grantee,
       a.privilege_type, a.is_grantable
FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace
CROSS JOIN LATERAL aclexplode(d.defaclacl) a
ORDER BY 1,2,3,4,5;

-- 5. Effective rights, including PUBLIC and inherited grants. No rows for an
-- absent ledger is expected before 0007; it is not evidence of safe future ACLs.
SELECT r.rolname, n.nspname AS schema_name, c.relname,
       pg_get_userbyid(c.relowner) AS object_owner,
       pg_has_role(r.oid,c.relowner,'MEMBER') AS owner_role_membership,
       has_schema_privilege(r.oid,n.oid,'USAGE') AS schema_usage,
       has_schema_privilege(r.oid,n.oid,'CREATE') AS schema_create,
       has_database_privilege(r.oid,current_database(),'TEMP') AS database_temp,
       has_table_privilege(r.oid,c.oid,'SELECT') AS can_read,
       has_table_privilege(r.oid,c.oid,'INSERT') AS can_insert,
       has_table_privilege(r.oid,c.oid,'UPDATE') AS can_update,
       has_table_privilege(r.oid,c.oid,'DELETE') AS can_delete,
       has_table_privilege(r.oid,c.oid,'TRUNCATE') AS can_truncate,
       has_table_privilege(r.oid,c.oid,'TRIGGER') AS can_create_trigger
FROM pg_roles r CROSS JOIN pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE c.relname='inventory_materialpricechange' AND c.relkind IN ('r','p')
ORDER BY n.nspname,r.rolname;

-- 6. Column ACLs can retain rights even after table-level revocation.
SELECT n.nspname,c.relname,att.attname,
       CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS grantee,
       a.privilege_type,a.is_grantable
FROM pg_attribute att JOIN pg_class c ON c.oid=att.attrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
CROSS JOIN LATERAL aclexplode(att.attacl) a
WHERE c.relname='inventory_materialpricechange' AND att.attnum>0 AND NOT att.attisdropped
ORDER BY 1,2,3,4;

-- 7. Ledger sequence rights required by invoker-mode audit inserts.
SELECT r.rolname,n.nspname,c.relname,
       pg_get_userbyid(c.relowner) AS sequence_owner,
       has_sequence_privilege(r.oid,c.oid,'USAGE') AS sequence_usage,
       has_sequence_privilege(r.oid,c.oid,'SELECT') AS sequence_select,
       has_sequence_privilege(r.oid,c.oid,'UPDATE') AS sequence_update
FROM pg_roles r CROSS JOIN pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE c.relkind='S' AND c.relname='inventory_materialpricechange_id_seq'
ORDER BY 2,3,1;

-- 8. RLS and actual enabled trigger definitions.
SELECT schemaname,tablename,policyname,permissive,roles,cmd,qual,with_check
FROM pg_policies WHERE tablename='inventory_materialpricechange';
SELECT n.nspname,c.relname,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid)
FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE NOT t.tgisinternal AND c.relname IN ('inventory_material','inventory_materialpricechange')
ORDER BY 1,2,3;
SELECT n.nspname,p.proname,pg_get_userbyid(p.proowner) AS function_owner,
       p.prosecdef AS security_definer,p.proconfig,p.proacl
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE p.proname IN ('inventory_price_audit_guard','inventory_record_price_change',
                    'inventory_price_audit_no_truncate');

-- 9. Selected API/schema settings only; do not dump arbitrary role settings.
SELECT COALESCE(d.datname,'ALL DATABASES') AS database_name,
       CASE WHEN s.setrole=0 THEN 'ALL ROLES' ELSE pg_get_userbyid(s.setrole) END AS role_name,
       setting
FROM pg_db_role_setting s LEFT JOIN pg_database d ON d.oid=s.setdatabase
CROSS JOIN LATERAL unnest(s.setconfig) AS settings(setting)
WHERE split_part(setting,'=',1) IN
 ('search_path','pgrst.db_schemas','pgrst.db_extra_search_path','pgrst.db_anon_role')
ORDER BY 1,2,3;
SELECT current_setting('pgrst.db_schemas',true) AS session_api_schemas,
       current_setting('pgrst.db_extra_search_path',true) AS session_api_extra_search_path;
-- NULL API settings here do NOT prove PostgREST has no exposed schemas.
-- Also inspect the Supabase API Exposed Schemas configuration read-only.
COMMIT;
