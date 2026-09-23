#!/usr/bin/env python3
"""Exercise PocketBase's Google exchange with a local provider and synthetic users."""
import argparse
import base64
import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading
import time
import urllib.parse

from integration import server


@contextlib.contextmanager
def google_fixture():
    codes, tokens = {}, {}

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, data):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != '/token':
                return self.reply(404, {})
            form = urllib.parse.parse_qs(self.rfile.read(int(self.headers.get('Content-Length', 0))).decode())
            get = lambda key: form.get(key, [''])[0]
            pending = codes.get(get('code'))
            challenge = base64.urlsafe_b64encode(hashlib.sha256(get('code_verifier').encode()).digest()).decode().rstrip('=')
            if not pending or challenge != pending['challenge'] or get('redirect_uri') != REDIRECT:
                return self.reply(400, {'error': 'invalid_grant'})
            if get('grant_type') != 'authorization_code':
                return self.reply(400, {'error': 'unsupported_grant_type'})
            del codes[get('code')]
            token = secrets.token_urlsafe(24)
            tokens[token] = pending['user']
            self.reply(200, {'access_token': token, 'token_type': 'Bearer', 'expires_in': 3600})

        def do_GET(self):
            user = tokens.get(self.headers.get('Authorization', '').removeprefix('Bearer '))
            if self.path != '/userinfo' or user is None:
                return self.reply(401, {})
            self.reply(200, user)

    http = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{http.server_port}', codes
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


REDIRECT = 'http://127.0.0.1:8765/callback'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', required=True)
    args = parser.parse_args()
    with google_fixture() as (provider_url, codes), server(args.binary) as request:
        admin = request('POST', '/api/collections/_superusers/auth-with-password', {
            'identity': 'admin@example.com', 'password': 'SyntheticAdminPassword123!',
        })['token']
        collection = request('GET', '/api/collections/users', token=admin)
        assert collection['createRule'] is None
        request('PATCH', '/api/collections/users', {'oauth2': {
            'enabled': True,
            'providers': [{'name': 'google', 'clientId': 'synthetic-client', 'clientSecret': 'synthetic-secret',
                           'authURL': provider_url + '/authorize', 'tokenURL': provider_url + '/token',
                           'userInfoURL': provider_url + '/userinfo'}],
        }}, admin)
        user = request('POST', '/api/collections/users/records', {
            'email': 'member@example.com', 'name': 'Workspace member', 'verified': True,
            'password': 'SyntheticUserPassword123!', 'passwordConfirm': 'SyntheticUserPassword123!',
        }, admin)

        def exchange(email, *, verified=True, expected=200, wrong_verifier=False, subject='workspace-member'):
            methods = request('GET', '/api/collections/users/auth-methods')
            provider = next(p for p in methods['oauth2']['providers'] if p['name'] == 'google')
            assert provider['codeChallengeMethod'] == 'S256'
            code = secrets.token_urlsafe(24)
            codes[code] = {'challenge': provider['codeChallenge'], 'user': {
                'sub': subject, 'email': email, 'email_verified': verified, 'name': 'Google display name',
            }}
            return request('POST', '/api/collections/users/auth-with-oauth2', {
                'provider': 'google', 'code': code, 'redirectURL': REDIRECT,
                'codeVerifier': 'wrong-verifier' if wrong_verifier else provider['codeVerifier'],
            }, expected=expected)

        exchange('member@example.com', wrong_verifier=True, expected=400)
        exchange('outsider@example.com', subject='outsider', expected=(400, 403))
        exchange('member@example.com', verified=False, subject='unverified', expected=(400, 403))
        auth = exchange('member@example.com')
        assert auth['record']['id'] == user['id']
        assert auth['record']['name'] == 'Workspace member'
        # A second login reuses the provider link and user identity.
        assert exchange('member@example.com')['record']['id'] == user['id']
        token = auth['token']
        refreshed = request('POST', '/api/collections/users/auth-refresh', token=token)
        assert refreshed['record']['id'] == user['id'] and refreshed['token']
        for issued in (token, refreshed['token']):
            claims = json.loads(base64.urlsafe_b64decode(issued.split('.')[1] + '=='))
            assert abs(claims['exp'] - time.time() - 604800) < 30
        project = request('POST', '/api/collections/projects/records', {
            'key': 'OAUTH', 'name': 'Synthetic OAuth project',
        }, token)
        assert project['created_by'] == user['id']
        result = request('POST', '/api/context/query', {'sql': 'SELECT key FROM projects'}, token)
        assert 'OAUTH' in json.dumps(result)
        history = request('GET', '/api/collections/audit_log/records', token=token)['items']
        assert any(row['record'] == project['id'] and row['actor'] == user['id'] for row in history)
        assert request('GET', '/api/collections/users/records', token=admin)['totalItems'] == 1
        assert request('GET', '/api/collections/users', token=admin)['createRule'] is None
        # Google login leaves the existing verified user's password login available.
        password = request('POST', '/api/collections/users/auth-with-password', {
            'identity': 'member@example.com', 'password': 'SyntheticUserPassword123!',
        })
        assert password['record']['id'] == user['id']
    print('TaskContext OAuth integration checks passed')


if __name__ == '__main__':
    main()
