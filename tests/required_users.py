#!/usr/bin/env python3
"""Required-user lifecycle over HTTP against an isolated database."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
EMAIL = 'required@example.test'
ADMIN = 'operator@example.test'
PASSWORD = 'SyntheticRequiredUserPassword123!'
CONFIG = json.dumps([{'email': EMAIL, 'name': 'Required member'}])


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', required=True)
    args = parser.parse_args()
    binary = str(Path(args.binary).resolve())
    clean = {key: value for key, value in os.environ.items()
             if not key.startswith(('TASKCONTEXT_', 'SMTP_', 'MAILER_')) and key != 'BASE_URL'}
    with tempfile.TemporaryDirectory(prefix='taskcontext-required-users-') as tmp:
        common = [binary, '--dir', str(Path(tmp) / 'data'), '--migrationsDir', str(ROOT / 'pb_migrations'),
                  '--hooksDir', str(ROOT / 'pb_hooks'), '--contextConfig', str(ROOT / 'pocketcontext.json')]
        state = {'server': None}

        def request(method, path, body=None, token=None, expected=200):
            headers = {'Content-Type': 'application/json'}
            if token:
                headers['Authorization'] = token
            req = urllib.request.Request(state['base'] + path, method=method, headers=headers,
                                         data=None if body is None else json.dumps(body).encode())
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    status, content = response.status, response.read()
            except urllib.error.HTTPError as error:
                status, content = error.code, error.read()
            assert status in (expected if isinstance(expected, tuple) else (expected,)), (method, path, status, content)
            return json.loads(content) if content else None

        def stop():
            if state['server'] is None:
                return
            state['server'].terminate()
            try:
                state['server'].wait(timeout=10)
            except subprocess.TimeoutExpired:
                state['server'].kill()
                state['server'].wait()
            state['log'].close()
            state['server'] = None

        def start(config=None):
            port = free_port()
            state['base'] = f'http://127.0.0.1:{port}'
            state['log'] = tempfile.TemporaryFile(mode='w+')
            env = dict(clean)
            if config is not None:
                env['TASKCONTEXT_REQUIRED_USERS'] = config
            state['server'] = subprocess.Popen(common + ['serve', '--http', f'127.0.0.1:{port}'], cwd=ROOT,
                                               env=env, stdout=state['log'], stderr=state['log'])
            for _ in range(150):
                if state['server'].poll() is not None:
                    state['log'].seek(0)
                    raise AssertionError(state['log'].read())
                try:
                    request('GET', '/api/health')
                    return
                except (OSError, AssertionError):
                    time.sleep(.1)
            raise AssertionError('Server startup timed out')

        def login(collection, email, password=PASSWORD):
            return request('POST', f'/api/collections/{collection}/auth-with-password',
                           {'identity': email, 'password': password})['token']

        def users(admin):
            query = urllib.parse.urlencode({'filter': 'email:lower = "' + EMAIL + '"'})
            return request('GET', '/api/collections/users/records?' + query, token=admin)['items']

        try:
            # The feature is opt-in, including on a completely empty database.
            original_data = common[common.index('--dir') + 1]
            common[common.index('--dir') + 1] = str(Path(tmp) / 'absent-data')
            start()
            stop()
            subprocess.run(common + ['superuser', 'upsert', ADMIN, PASSWORD], cwd=ROOT, env=clean,
                           check=True, capture_output=True, text=True)
            start()
            assert users(login('_superusers', ADMIN)) == []
            stop()
            common[common.index('--dir') + 1] = original_data
            # Fresh startup must run application migrations before provisioning.
            start(CONFIG)
            stop()
            subprocess.run(common + ['superuser', 'upsert', ADMIN, PASSWORD], cwd=ROOT, env=clean,
                           check=True, capture_output=True, text=True)
            start(CONFIG)
            admin = login('_superusers', ADMIN)
            records = users(admin)
            assert len(records) == 1, records
            first = records[0]
            assert (first['email'], first['name'], first['verified']) == (EMAIL, 'Required member', False), first
            path = '/api/collections/users/records/' + first['id']
            directory = '/api/collections/user_directory/records/' + first['id']
            assert request('GET', directory, token=admin)['name'] == 'Required member'
            # Operators can manage name, verification, and password without losing the required identity.
            request('PATCH', path, {'name': 'Operator edited', 'verified': True,
                                   'password': PASSWORD, 'passwordConfirm': PASSWORD}, admin)
            token = login('users', EMAIL)
            changed = 'ChangedSyntheticPassword123!'
            request('PATCH', path, {'oldPassword': PASSWORD, 'password': changed, 'passwordConfirm': changed}, token)
            login('users', EMAIL, changed)
            request('DELETE', path, token=admin, expected=(400, 403))
            request('PATCH', path, {'email': 'moved@example.test'}, admin, expected=(400, 403))
            # Unrelated operator-managed accounts retain their ordinary lifecycle.
            other = request('POST', '/api/collections/users/records',
                            {'email': 'other@example.test', 'name': 'Other', 'password': PASSWORD,
                             'passwordConfirm': PASSWORD}, admin)
            other_path = '/api/collections/users/records/' + other['id']
            request('PATCH', other_path, {'email': 'renamed@example.test'}, admin)
            request('DELETE', other_path, token=admin, expected=(400, 403))
            stop()
            start(json.dumps([{'email': EMAIL.upper(), 'name': 'Changed configuration name'}]))
            admin = login('_superusers', ADMIN)
            stored = users(admin)
            assert len(stored) == 1 and stored[0]['id'] == first['id'], stored
            assert (stored[0]['name'], stored[0]['verified']) == ('Operator edited', True), stored
            assert request('GET', directory, token=admin)['name'] == 'Operator edited'
            login('users', EMAIL, changed)
            # Removing the requirement permits email maintenance, but never account deletion.
            stop()
            start()
            admin = login('_superusers', ADMIN)
            assert users(admin)[0]['id'] == first['id']
            request('DELETE', path, token=admin, expected=(400, 403))
            request('PATCH', path, {'email': 'retired@example.test', 'disabled': True}, admin)
            assert users(admin) == []
            # Adopt an operator-provisioned mixed-case identity without creating a duplicate.
            adopted = request('POST', '/api/collections/users/records',
                              {'email': EMAIL.upper(), 'name': 'Existing member', 'password': PASSWORD,
                               'passwordConfirm': PASSWORD}, admin)
            stop()
            start(CONFIG)
            admin = login('_superusers', ADMIN)
            assert len(users(admin)) == 1 and users(admin)[0]['id'] == adopted['id']
            assert users(admin)[0]['name'] == 'Existing member'
            login('users', adopted['email'], PASSWORD)
            request('DELETE', '/api/collections/users/records/' + adopted['id'], token=admin, expected=(400, 403))
            stop()
            start()
            admin = login('_superusers', ADMIN)
            request('PATCH', '/api/collections/users/records/' + adopted['id'],
                    {'email': 'retired-adopted@example.test', 'disabled': True}, admin)
            stop()
            start(CONFIG)
            admin = login('_superusers', ADMIN)
            recreated = users(admin)
            assert len(recreated) == 1 and recreated[0]['email'] == EMAIL, recreated
            assert recreated[0]['id'] != first['id']
            assert recreated[0]['verified'] is False
            assert request('GET', '/api/collections/user_directory/records/' + recreated[0]['id'], token=admin)['name'] == 'Required member'
            stop()
            # Invalid configuration must fail closed before accepting HTTP traffic.
            for invalid in ('not-json', '{}', '[{}]', '[null]', '[{"email":"one@example.test"}]',
                            '[{"email":"one@example.test","name":""}]',
                            '[{"email":"one@example.test","name":"One","password":"forbidden"}]', '[{"email":"invalid","name":"Member"}]',
                            '[{"email":"one@example.test","name":"One"},{"email":"one@example.test","name":"Duplicate"}]'):
                result = subprocess.run(common + ['serve', '--http', f'127.0.0.1:{free_port()}'], cwd=ROOT,
                                        env={**clean, 'TASKCONTEXT_REQUIRED_USERS': invalid},
                                        capture_output=True, text=True, timeout=15)
                assert result.returncode != 0, 'Invalid configuration allowed startup'
                assert 'TASKCONTEXT_REQUIRED_USERS' in result.stdout + result.stderr
                assert 'Server started' not in result.stdout + result.stderr
        finally:
            stop()
    print('PASS: required users provisioned after migrations, preserved on restart, protected from deletion and email changes, '
          'recreated after maintenance, directory synchronized, account history and password changes preserved, invalid configuration rejected')


if __name__ == '__main__':
    main()
