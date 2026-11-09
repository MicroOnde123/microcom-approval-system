"""Run agent checks in a fresh, loopback-only PostgreSQL cluster on Windows.

No .env, deployment settings, shared databases, service control or file deletion.
Retains logs and generated test files under local_artifacts for review.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
BIN = Path(os.environ.get('AGENT_TEST_PG_BIN', r'C:\Program Files\PostgreSQL\17\bin'))
ARTIFACTS = ROOT / 'local_artifacts' / ('agent_final_checks_' + uuid4().hex[:12])
DATA = ARTIFACTS / 'pgdata'


def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=False)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    environment = {**os.environ, 'AGENT_TEST_PG_PORT': str(port), 'PYTHONIOENCODING': 'utf-8'}
    # Full migrations are unconditional in test_agents_settings.
    environment.pop('AGENT_TEST_SCHEMA_ONLY', None)
    summary = {'cluster': str(DATA), 'port': port, 'runs': []}

    def run(label, command, env=environment):
        with (ARTIFACTS / (label + '.log')).open('wb') as log:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    creationflags=subprocess.CREATE_NO_WINDOW, timeout=240)
        summary['runs'].append({'label': label, 'exit_code': result.returncode})
        print(label + ': ' + ('PASS' if result.returncode == 0 else 'FAIL'), flush=True)
        if result.returncode:
            raise RuntimeError(label + ' failed; see ' + str(ARTIFACTS / (label + '.log')))

    run('initdb', [str(BIN / 'initdb.exe'), '-D', str(DATA), '-U', 'agent_test_owner',
                   '-A', 'trust', '--no-locale', '--encoding=UTF8'])
    with (ARTIFACTS / 'postgres.log').open('ab') as log:
        server = subprocess.Popen([str(BIN / 'postgres.exe'), '-D', str(DATA), '-p', str(port),
                                   '-h', '127.0.0.1'], stdout=log, stderr=log,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
    summary['pid'] = server.pid
    verified = False
    try:
        import psycopg2
        for _ in range(100):
            try:
                connection = psycopg2.connect(host='127.0.0.1', port=port, user='agent_test_owner',
                                               dbname='postgres', connect_timeout=1)
                break
            except psycopg2.OperationalError:
                if server.poll() is not None:
                    raise RuntimeError('Owned test PostgreSQL exited during startup')
                time.sleep(.1)
        else:
            raise RuntimeError('Owned test PostgreSQL startup timed out')
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('data_directory'), inet_server_port(), "
                           "current_setting('listen_addresses'), current_user")
            directory, actual_port, host, role = cursor.fetchone()
            assert Path(directory).resolve() == DATA.resolve()
            assert (actual_port, host, role) == (port, '127.0.0.1', 'agent_test_owner')
        connection.close()
        pidfile = (DATA / 'postmaster.pid').read_text().splitlines()
        assert int(pidfile[0]) == server.pid and Path(pidfile[1]).resolve() == DATA.resolve()
        verified = True
        print('Verified fresh owned PostgreSQL cluster: ' + str(DATA), flush=True)
        base = [sys.executable, 'manage.py', 'test']
        options = ['--settings=config.test_agents_settings', '--noinput']
        run('regressions', base + ['requests_app.test_agents', 'requests_app.test_sites.SiteTests',
            'requests_app.test_permission_resubmission.PermissionResubmissionTests',
            'requests_app.test_permission_resubmission.ArchivedPaginationTests', 'requests_app.tests'] + options)
        cases = [
            ('site_name_lock', 'requests_app.test_sites.SiteConcurrencyTests.test_directory_rename_waits_for_snapshot_commit'),
            ('site_resume', 'requests_app.test_sites.SiteConcurrencyTests.test_site_snapshot_resumes_once_under_concurrency'),
            ('site_restart', 'requests_app.test_sites.SiteConcurrencyTests.test_site_correction_restarts_once_under_concurrency'),
            ('snapshot_resume', 'requests_app.test_agent_concurrency.AgentConcurrencyTests.test_concurrent_unchanged_snapshot_resumes_once'),
            ('snapshot_restart', 'requests_app.test_agent_concurrency.AgentConcurrencyTests.test_concurrent_corrected_snapshot_restarts_once'),
            ('resubmission_lock', 'requests_app.test_permission_resubmission.PermissionConcurrencyTests.test_concurrent_resubmissions_create_one_attempt'),
            ('approval_lock', 'requests_app.test_permission_resubmission.PermissionConcurrencyTests.test_concurrent_primary_and_alternate_act_only_once'),
        ]
        for label, case in cases:
            env = {**environment, 'AGENT_TEST_DATABASE': 'test_microcom_agents_' + label}
            run(label, base + [case] + options +
                ['--testrunner=requests_app.agent_concurrency_runner.FreshDatabaseRunner'], env)
        run('system_check', [sys.executable, 'manage.py', 'check', '--settings=config.test_agents_settings'])
        run('migration_drift', [sys.executable, 'manage.py', 'makemigrations', '--check', '--dry-run',
                                '--settings=config.test_agents_settings'])
    finally:
        if verified and server.poll() is None:
            # Exact new-cluster identity verified above; never address a shared service.
            run('stop_owned_cluster', [str(BIN / 'pg_ctl.exe'), '-D', str(DATA), '-w', '-m', 'fast', 'stop'])
            server.wait(timeout=30)
        (ARTIFACTS / 'results.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print('Evidence: ' + str(ARTIFACTS), flush=True)


if __name__ == '__main__':
    main()
