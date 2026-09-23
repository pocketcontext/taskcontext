#!/usr/bin/env python3
"""Command-line client for a TaskContext issue tracker server. Python 3 standard library only.

Configuration comes from three environment variables:
  TASKCONTEXT_URL             server address, for example https://tasks.example.com
  TASKCONTEXT_USER_EMAIL     email of an account in the `users` collection
  TASKCONTEXT_USER_PASSWORD  password of that account

Exit codes: 0 success; 1 HTTP or transport error; 2 usage or configuration error;
3 `check` found schema differences; 4 HTTP 409 (read the record again, then retry).
"""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

ENV = ['TASKCONTEXT_URL', 'TASKCONTEXT_USER_EMAIL', 'TASKCONTEXT_USER_PASSWORD']
SCHEMA_FILE = Path(__file__).resolve().parent.parent / 'references' / 'schema.json'
STAMPS = ('created_by', 'updated_by')
ID_ALPHABET = 'abcdefghijklmnopqrstuvwxyz0123456789'
TIMEOUT = 30
USER_AGENT = 'TaskContext/1.0'
hidden = []  # The password and tokens. say() masks them in everything it prints.


class Fail(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def hide(value):
    if value:
        hidden.append(value)
    return value


def say(text, stream=sys.stderr):
    for value in hidden:
        text = text.replace(value, '***')
    print(text, file=stream)


def dump(data, pretty=False):
    if pretty:
        return json.dumps(data, indent=2, ensure_ascii=False)
    return json.dumps(data, separators=(',', ':'), ensure_ascii=False)


def config(names=ENV):
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise Fail(2, 'missing environment variable: ' + ', '.join(missing) + '. Ask the user to set every missing variable; do not look for credentials elsewhere.')
    url = os.environ[ENV[0]].rstrip('/')
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise Fail(2, 'TASKCONTEXT_URL must be an HTTP(S) URL without credentials, query, or fragment')
    if parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise Fail(2, 'Use HTTPS for a remote TaskContext server')
    return {'url': url, 'email': os.environ[ENV[1]], 'password': hide(os.environ.get(ENV[2]))}


# Token cache: one file per server URL and email, readable only by the current user.

def cache_file(cfg):
    base = os.environ.get('XDG_CACHE_HOME') or str(Path.home() / '.cache')
    key = hashlib.sha256((cfg['url'] + '\n' + cfg['email']).encode()).hexdigest()[:32]
    return Path(base) / 'taskcontext' / (key + '.json')


def load_session(cfg):
    try:
        session = json.loads(cache_file(cfg).read_text())
        return session if hide(session['token']) else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_session(cfg, session):
    path = cache_file(cfg)
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.session-', delete=False) as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            json.dump(session, handle)
        os.replace(temporary, path)
    except OSError as error:
        say(f'note: token not cached ({error.strerror}); the next command logs in again')


# HTTP

class NoRedirect(urllib.request.HTTPRedirectHandler):
    """A followed redirect would turn a POST into a GET and could send the token to another host."""
    def redirect_request(self, *args):
        return None


opener = urllib.request.build_opener(NoRedirect)


def send(cfg, method, path, body=None, token=None, timeout=TIMEOUT):
    """Send one request. Returns (status, parsed JSON body, or the text when it is not JSON)."""
    headers = {'Content-Type': 'application/json', 'User-Agent': USER_AGENT}
    if token:
        headers['Authorization'] = token
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(cfg['url'] + path, data=data, headers=headers, method=method)
    try:
        with opener.open(request, timeout=timeout) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
        if 300 <= status < 400:
            raise Fail(1, f'HTTP {status}: the server redirects to {error.headers.get("Location")}. Set TASKCONTEXT_URL to the final address.')
    except (OSError, ValueError, http.client.HTTPException) as error:
        reason = getattr(error, 'reason', error)
        raise Fail(1, f'cannot reach {cfg["url"]}: {reason}')
    text = raw.decode('utf-8', 'replace')
    try:
        return status, json.loads(text) if text else None
    except ValueError:
        return status, text[:2000]


def login(cfg):
    status, data = send(cfg, 'POST', '/api/collections/users/auth-with-password', {'identity': cfg['email'], 'password': cfg['password']})
    if status != 200 or not isinstance(data, dict) or 'token' not in data:
        raise Fail(1, f'login as {cfg["email"]} failed: HTTP {status}\n{dump(data)}\nCheck the three TASKCONTEXT_ variables with the user. User credentials only.')
    session = {'url': cfg['url'], 'email': cfg['email'], 'token': hide(data['token'])}
    save_session(cfg, session)
    return session


def token_rejected(cfg, token):
    return send(cfg, 'POST', '/api/context/query', {'sql': 'SELECT 1'}, token)[0] == 401


def call(cfg, method, path, body=None):
    """Authenticated request. Returns (status, data).

    Only the SQL endpoints answer an expired or revoked token with 401. The records API treats it as no
    token and answers 400, 403, or 404. So after such an error with a cached token, check the token,
    and if the server rejects it, log in once and send the request once more. The first attempt wrote nothing.
    """
    session = load_session(cfg)
    cached = session is not None
    if not cached:
        session = login(cfg)
    status, data = send(cfg, method, path, body, session['token'])
    if cached and 400 <= status < 500 and status != 409 and (status == 401 or token_rejected(cfg, session['token'])):
        session = login(cfg)
        status, data = send(cfg, method, path, body, session['token'])
    return status, data


def batch_failures(data):
    """The failed requests of a rejected batch as (index, status, message). The server reports them under data.requests."""
    try:
        failures = []
        for index, entry in data['data']['requests'].items():
            response = entry['response']
            fields = [f'{name}: {detail.get("message")}' for name, detail in (response.get('data') or {}).items() if isinstance(detail, dict)]
            failures.append((index, response.get('status'), ' '.join([response.get('message') or ''] + fields)))
        return failures
    except (AttributeError, KeyError, TypeError):
        return []


def must(cfg, method, path, body=None):
    """Like call(), but an HTTP error ends the command with the server's status and body on stderr."""
    status, data = call(cfg, method, path, body)
    if status < 400:
        return data
    lines = [f'HTTP {status} from {method} {path}', dump(data, pretty=True)]
    conflict = status == 409
    if path == '/api/batch':
        lines.append('Nothing in this batch was saved.')
        for index, inner_status, message in batch_failures(data):
            lines.append(f'Failed request index {index}: HTTP {inner_status}: {message}')
            conflict = conflict or inner_status == 409
    if conflict:
        lines.append('HTTP 409: another request changed the record first. Read it again, confirm the change still applies, then retry.')
    raise Fail(4 if conflict else 1, '\n'.join(lines))


# Commands

def read_json(text, kind, what):
    if text == '-':
        text = sys.stdin.read()
    try:
        value = json.loads(text)
    except ValueError as error:
        raise Fail(2, f'{what} is not valid JSON: {error}')
    if not isinstance(value, kind):
        raise Fail(2, f'{what} must be a JSON {"array" if kind is list else "object"}')
    return value


def require_revision(body):
    if type(body.get('expected_revision')) is not int or body['expected_revision'] < 1:
        raise Fail(2, 'updates require expected_revision from your last read; read the record before changing it')


def record_body(text):
    body = read_json(text, dict, 'the record body')
    for field in STAMPS:
        if field in body:
            del body[field]
            say(f'note: removed {field} from the body; the server sets it from your login')
    if not body:
        raise Fail(2, 'the record body has no fields to send')
    return body


def records(collection, record=None):
    path = f'/api/collections/{urllib.parse.quote(collection, safe="")}/records'
    return path if record is None else f'{path}/{urllib.parse.quote(record, safe="")}'


def columns(tables):
    return {table['name']: {column['name']: column.get('type') for column in table['columns']} for table in tables}


def check(cfg):
    """Compare the live SQL schema with references/schema.json. Returns the exit code."""
    try:
        reference = columns(json.loads(SCHEMA_FILE.read_text())['tables'])
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise Fail(2, f'cannot read {SCHEMA_FILE}: {error}')
    live = columns(must(cfg, 'GET', '/api/context/schema')['tables'])
    differences = []
    for table in sorted(set(live) | set(reference)):
        if table not in reference:
            differences.append(f'table {table}: on the server, not in the reference files')
        elif table not in live:
            differences.append(f'table {table}: in the reference files, not on the server')
        else:
            for column in sorted(set(live[table]) | set(reference[table])):
                if column not in reference[table]:
                    differences.append(f'column {table}.{column}: on the server, not in the reference files')
                elif column not in live[table]:
                    differences.append(f'column {table}.{column}: in the reference files, not on the server')
                elif live[table][column] != reference[table][column]:
                    differences.append(f'column {table}.{column}: type {live[table][column]} on the server, {reference[table][column]} in the reference files')
    if not differences:
        say(f'OK: the live schema matches references/schema.json ({len(live)} tables)', sys.stdout)
        return 0
    for line in differences:
        say(line, sys.stdout)
    say('The server is authoritative: run `tc.py schema` and follow the server\'s error messages where the reference files disagree. '
        'Ask the user to update this skill.', sys.stdout)
    return 3


def run(args):
    if args.command == 'newid':
        print(''.join(secrets.choice(ID_ALPHABET) for _ in range(15)))
        return 0
    if args.command == 'logout':
        cfg = config(ENV[:2])
        path = cache_file(cfg)
        path.unlink(missing_ok=True)
        say(f'removed {path}', sys.stdout)
        return 0
    cfg = config()
    # Reject malformed writes before authentication or any network request.
    body = None
    if args.command in ('create', 'update'):
        body = record_body(args.json)
        if args.command == 'update':
            require_revision(body)
    elif args.command == 'batch':
        requests = read_json(args.json, list, 'the batch')
        if not all(isinstance(entry, dict) for entry in requests):
            raise Fail(2, 'each batch entry must be an object with method, url, and body')
        for entry in requests:
            method, url = entry.get('method'), entry.get('url', '')
            if method not in ('POST', 'PATCH') or not isinstance(url, str) or not re.fullmatch(r'/api/collections/(projects|issues|issue_links|comments|references)/records(?:/[a-z0-9]{15})?', url):
                raise Fail(2, 'batch accepts only POST/PATCH business record URLs')
            if not isinstance(entry.get('body'), dict):
                raise Fail(2, 'each batch body must be an object')
            if method == 'PATCH':
                require_revision(entry['body'])
        body = {'requests': requests}
    if args.command == 'check':
        return check(cfg)
    if args.command == 'whoami':
        # auth-refresh returns the account behind the token. The new token it also returns is not used.
        refreshed = must(cfg, 'POST', '/api/collections/users/auth-refresh')
        hide(refreshed.get('token'))
        record = refreshed['record']
        data = {'id': record['id'], 'name': record.get('name', ''), 'email': cfg['email'], 'url': cfg['url']}
    elif args.command == 'schema':
        data = must(cfg, 'GET', '/api/context/schema')
    elif args.command in ('sql', 'query'):
        query = sys.stdin.read() if args.query == '-' else args.query
        data = must(cfg, 'POST', '/api/context/query', {'sql': query})
        if isinstance(data, dict) and data.get('truncated'):
            say(f'WARNING: result truncated to {len(data.get("rows", []))} rows by the server\'s row or byte limit. Select fewer columns, narrow the query, or page with ORDER BY and LIMIT/OFFSET.')
    elif args.command == 'get':
        if not re.fullmatch(r'[a-z0-9]{15}', args.id):
            raise Fail(2, 'record id must be 15 lowercase letters or digits')
        schema = must(cfg, 'GET', '/api/context/schema')
        table = next((table for table in schema['tables'] if table['name'] == args.collection), None)
        if table is None or not any(column['name'] == 'id' for column in table['columns']):
            raise Fail(2, 'collection is not an SQL-readable table with an id column')
        identifier = '"' + table['name'].replace('"', '""') + '"'
        result = must(cfg, 'POST', '/api/context/query', {
            'sql': f"SELECT * FROM {identifier} WHERE id = '{args.id}' LIMIT 1"
        })
        if result.get('truncated'):
            raise Fail(1, 'record exceeds the SQL response limit; query only the needed fields')
        if not result['rows']:
            raise Fail(1, f'HTTP 404: record not found in {args.collection}')
        data = dict(zip(result['columns'], result['rows'][0]))
    elif args.command == 'create':
        data = must(cfg, 'POST', records(args.collection), body)
    elif args.command == 'update':
        data = must(cfg, 'PATCH', records(args.collection, args.id), body)
    elif args.command == 'batch':
        data = must(cfg, 'POST', '/api/batch', body)
    say(dump(data, args.pretty), sys.stdout)
    return 0


def parse(argv):
    pretty = argparse.ArgumentParser(add_help=False)
    pretty.add_argument('--pretty', action='store_true', default=argparse.SUPPRESS, help='indent the JSON output')
    parser = argparse.ArgumentParser(prog='tc.py', parents=[pretty], description='TaskContext issue tracker client. Reads with SQL, writes through the records API. There is no delete command: users cannot delete records.',
                                     epilog='Environment: ' + ', '.join(ENV) + '. JSON arguments may be "-" to read standard input. Exit codes: 0 ok, 1 HTTP or transport error, 2 usage or configuration, 3 check found differences, 4 HTTP 409.')
    commands = parser.add_subparsers(dest='command', required=True, metavar='command')
    def add(name, text, *arguments):
        command = commands.add_parser(name, parents=[pretty], help=text, description=text)
        for argument, argument_help in arguments:
            command.add_argument(argument, help=argument_help)
    add('whoami', 'print the user id, name, and server URL; use the id for `assignee`')
    add('check', 'compare the live schema with references/schema.json; exit 3 when they differ')
    add('schema', 'print the live SQL tables and columns')
    add('query', 'run one read-only SELECT', ('query', 'SQL text, or - for standard input'))
    add('sql', 'run one read-only SELECT', ('query', 'SQL text, or - for standard input'))
    add('get', 'read one record as an SQL row object', ('collection', 'collection name'), ('id', 'record id'))
    add('create', 'create one record', ('collection', 'collection name'), ('json', 'JSON object, or -'))
    add('update', 'change fields of one record', ('collection', 'collection name'), ('id', 'record id'), ('json', 'JSON object with the fields to change, or -'))
    add('batch', 'send up to 20 writes as one transaction', ('json', 'JSON array of {"method","url","body"}, or -'))
    add('newid', 'print a new 15-character record id for use inside a batch')
    add('logout', 'remove the cached token')
    args = parser.parse_args(argv)
    args.pretty = getattr(args, 'pretty', False)
    return args


def main():
    try:
        return run(parse(sys.argv[1:]))
    except Fail as error:
        say(f'tc.py: {error}')
        return error.code
    except KeyboardInterrupt:
        return 130
    except Exception as error:  # No traceback: keep the output short and free of request data.
        say(f'tc.py: unexpected {type(error).__name__}: {error}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
