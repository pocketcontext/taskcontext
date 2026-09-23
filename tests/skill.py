#!/usr/bin/env python3
"""Test the installable skill in skills/taskcontext; no third-party Python dependencies.

  python3 tests/skill.py --binary /path/to/pocketcontext
  python3 tests/skill.py --binary /path/to/pocketcontext --write-schema

The first form checks the skill's files, then copies the skill outside the repository and runs its
scripts/tc.py against a temporary server. The second form rewrites skills/taskcontext/references/schema.json
from a temporary server; run it after a migration changes the SQL-readable tables or columns.
"""
import argparse
import contextlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'taskcontext'
EMAIL, PASSWORD = 'skill-user@example.com', 'SkillAgentPassword123!'
FORBIDDEN = ['POCKETBASE_ADMIN', '.envrc', '.env.admin', '_superusers', 'superuser upsert']
REGENERATE = 'If a migration changed the schema, regenerate references/schema.json: python3 tests/skill.py --binary <pocketcontext> --write-schema'


@contextlib.contextmanager
def item(label):
    try:
        yield
    except Exception as error:
        raise AssertionError(f'FAILED skill check: {label}', repr(error)) from error


@contextlib.contextmanager
def task_server(binary, tmp):
    """Start a server on a temporary database and provision one user. Yields (base URL, user record)."""
    hooks = tmp / 'pb_hooks'
    shutil.copytree(ROOT / 'pb_hooks', hooks)
    (hooks / 'sql_read_fixture.pb.js').write_text("onRecordViewRequest((e) => { throw new ForbiddenError('Use SQL for business reads'); }, 'projects', 'issues', 'comments', 'references', 'issue_links', 'audit_log', 'user_directory');")
    common = [binary, '--dir', str(tmp / 'pb_data'), '--migrationsDir', str(ROOT / 'pb_migrations'), '--hooksDir', str(hooks)]
    subprocess.run(common + ['superuser', 'upsert', 'test-admin@example.com', 'TestAdminPassword123!'], cwd=ROOT, check=True, capture_output=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    log = open(tmp / 'server.log', 'w+')
    server = subprocess.Popen(common + ['serve', '--http', f'127.0.0.1:{port}'], cwd=ROOT, stdout=log, stderr=log)

    def request(method, path, body=None, token=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = token
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read())
    try:
        for _ in range(150):
            try:
                request('GET', '/api/health')
                break
            except OSError:
                if server.poll() is not None:
                    raise RuntimeError('Server exited during startup')
                time.sleep(.1)
        else:
            raise RuntimeError('Server did not start')
        admin = request('POST', '/api/collections/_superusers/auth-with-password', {'identity': 'test-admin@example.com', 'password': 'TestAdminPassword123!'})['token']
        user = request('POST', '/api/collections/users/records', {'email': EMAIL, 'password': PASSWORD, 'passwordConfirm': PASSWORD, 'name': 'Skill user'}, admin)
        yield base, user
    except Exception:
        log.flush()
        log.seek(0)
        print(log.read())
        raise
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
        log.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', required=True)
    parser.add_argument('--write-schema', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='taskcontext-skill-') as temporary:
        tmp = Path(temporary)
        with task_server(str(Path(args.binary).resolve()), tmp) as (base, user):
            installed = tmp / 'installed'
            shutil.copytree(SKILL, installed)
            script = installed / 'scripts/tc.py'
            environment = {'PATH': os.environ.get('PATH', ''), 'HOME': str(tmp / 'home'), 'XDG_CACHE_HOME': str(tmp / 'cache'),
                           'TASKCONTEXT_URL': base, 'TASKCONTEXT_USER_EMAIL': EMAIL, 'TASKCONTEXT_USER_PASSWORD': PASSWORD}
            outputs = []
            def run(*arguments, expected=0, stdin=None, **overrides):
                env = {k:v for k,v in {**environment, **overrides}.items() if v is not None}
                result = subprocess.run([sys.executable, str(script), *arguments], cwd=tmp, env=env,
                                        input=stdin, text=True, capture_output=True, timeout=30)
                assert result.returncode == expected, (arguments, result.returncode, result.stdout, result.stderr)
                outputs.append(result.stdout + result.stderr)
                return result.stdout, result.stderr
            def data(*arguments, **options):
                return json.loads(run(*arguments, **options)[0])
            if args.write_schema:
                schema = data('schema')
                snapshot = {'tables': sorted([{'name': t['name'], 'columns': sorted(t['columns'], key=lambda c:c['name'])} for t in schema['tables']], key=lambda t:t['name'])}
                (SKILL / 'references/schema.json').write_text(json.dumps(snapshot, indent=2) + '\n')
                print('Wrote schema snapshot from isolated server')
                return
            for key in ('TASKCONTEXT_URL','TASKCONTEXT_USER_EMAIL','TASKCONTEXT_USER_PASSWORD'):
                assert key in run('whoami', expected=2, **{key:None})[1]
            run('create','projects','{oops',expected=2)
            run('update','issues','missing','{}',expected=2)
            run('delete','issues','missing',expected=2)
            run('batch','[{"method":"DELETE","url":"/api/collections/issues/records/abcdefghijklmno"}]',expected=2)
            assert not (tmp/'cache/taskcontext').exists()
            assert re.fullmatch('[a-z0-9]{15}', run('newid', TASKCONTEXT_URL=None)[0].strip())
            assert data('whoami')['id'] == user['id']
            session_file, = (tmp/'cache/taskcontext').glob('*.json')
            assert stat.S_IMODE(session_file.stat().st_mode) == 0o600
            assert stat.S_IMODE(session_file.parent.stat().st_mode) == 0o700
            assert PASSWORD not in session_file.read_text()
            token = json.loads(session_file.read_text())['token']
            assert data('whoami',TASKCONTEXT_USER_PASSWORD='bad')['id'] == user['id']
            assert run('check')[0].startswith('OK')
            snapshot = installed/'references/schema.json'
            original = snapshot.read_text(); snapshot.write_text('{"tables":[]}')
            assert 'projects' in run('check',expected=3)[0]; snapshot.write_text(original)
            names = {t['name'] for t in data('schema')['tables']}
            assert 'users' not in names and {'issues','projects','user_directory','audit_log'} <= names
            project = data('create','projects','-',stdin='{"key":"SKILL","name":"Skill test"}')
            issue = data('create','issues',json.dumps({'project':project['id'],'title':'Portable test'}))
            assert issue['revision'] == 1 and issue['created_by'] == user['id']
            updated = data('update','issues',issue['id'],'{"title":"Renamed","expected_revision":1}')
            assert updated['revision'] == 2 and updated['title'] == 'Renamed'
            assert data('get','issues',issue['id'])['title'] == 'Renamed'
            assert data('get','user_directory',user['id'])['name'] == 'Skill user'
            assert '404' in run('get','issues','missing00000000',expected=1)[1]
            run('get','users',user['id'],expected=2)
            run('get','issues" WHERE 1=1 --',issue['id'],expected=2)
            run('get','issues',"' OR 1=1 --",expected=2)
            assert '409' in run('update','issues',issue['id'],'{"title":"Lost change","expected_revision":1}',expected=4)[1]
            assert data('get','issues',issue['id'])['title'] == 'Renamed'
            result = data('query','-',stdin='SELECT NULL AS missing, \'\' AS empty FROM issues LIMIT 1')
            assert result['rows'] == [[None,'']]
            assert data('sql','SELECT count(*) FROM issues')['rows'] == [[1]]
            run('query','SELECT * FROM users',expected=1)
            identifier = run('newid')[0].strip()
            batch = [{'method':'POST','url':'/api/collections/issues/records','body':{'id':identifier,'project':project['id'],'title':'Batch issue'}},
                     {'method':'POST','url':'/api/collections/comments/records','body':{'issue':identifier,'body':'Evidence'}}]
            assert len(data('batch','-',stdin=json.dumps(batch))) == 2
            batch[0]['body']['id'] = run('newid')[0].strip()
            batch[0]['body']['title'] = 'Must roll back'
            batch[1]['body']['issue'] = 'missing00000000'
            assert 'Nothing in this batch was saved' in run('batch',json.dumps(batch),expected=1)[1]
            assert data('query',"SELECT count(*) FROM issues WHERE title = 'Must roll back'")['rows'] == [[0]]
            conflicting = [{'method':'PATCH','url':f'/api/collections/issues/records/{issue["id"]}','body':{'title':'Conflict','expected_revision':1}}]
            assert '409' in run('batch',json.dumps(conflicting),expected=4)[1]
            session = json.loads(session_file.read_text()); session['token'] = 'expired-token'; session_file.write_text(json.dumps(session))
            assert data('get','issues',issue['id'])['title'] == 'Renamed'
            assert json.loads(session_file.read_text())['token'] != 'expired-token'
            run('logout',TASKCONTEXT_USER_PASSWORD=None)
            assert not session_file.exists()
            for output in outputs:
                assert PASSWORD not in output and token not in output
            print('PASS: portable client, users identity, schema snapshot, private cache, revision conflict, atomic batches, token recovery, secret-free output')

if __name__ == '__main__':
    main()
