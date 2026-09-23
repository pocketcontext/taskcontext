#!/usr/bin/env python3
"""Exercise TaskContext through HTTP against an isolated temporary database."""
import argparse
import concurrent.futures
import contextlib
import json
from pathlib import Path
import socket
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

@contextlib.contextmanager
def server(binary):
    with tempfile.TemporaryDirectory(prefix='taskcontext-test-') as tmp:
        hooks=Path(tmp)/'pb_hooks'
        shutil.copytree(ROOT/'pb_hooks',hooks)
        (hooks/'failure_fixture.pb.js').write_text('''
onRecordCreateExecute((e) => {
  if(e.record.getString('record') === 'auditfailure001') throw new Error('Synthetic audit failure');
  e.next();
}, 'audit_log');
onRecordCreateExecute((e) => {
  if(e.record.id === 'dirfailure00001') throw new Error('Synthetic directory failure');
  e.next();
}, 'user_directory');
''')
        common = [str(Path(binary).resolve()), '--dir', str(Path(tmp)/'pb_data'), '--migrationsDir', str(ROOT/'pb_migrations'), '--hooksDir', str(hooks)]
        result = subprocess.run(common+['superuser','upsert','admin@example.com','SyntheticAdminPassword123!'],cwd=ROOT,capture_output=True,text=True)
        assert result.returncode == 0, result.stdout+result.stderr
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        with open(Path(tmp)/'server.log','w+') as log:
            proc=subprocess.Popen(common+['serve','--http',f'127.0.0.1:{port}'],cwd=ROOT,stdout=log,stderr=log)
            def request(method,path,body=None,token=None,expected=200):
                headers={'Content-Type':'application/json'}
                if token: headers['Authorization']=token
                req=urllib.request.Request(f'http://127.0.0.1:{port}'+path,data=None if body is None else json.dumps(body).encode(),headers=headers,method=method)
                try:
                    with urllib.request.urlopen(req,timeout=20) as r: status,raw=r.status,r.read()
                except urllib.error.HTTPError as e: status,raw=e.code,e.read()
                assert status in (expected if isinstance(expected,tuple) else (expected,)), (method,path,status,raw.decode())
                return json.loads(raw) if raw else None
            try:
                for _ in range(150):
                    try: request('GET','/api/health'); break
                    except (OSError,AssertionError):
                        if proc.poll() is not None: log.seek(0); raise AssertionError(log.read())
                        time.sleep(.1)
                else: raise AssertionError('Server startup timed out')
                request.base_url = f'http://127.0.0.1:{port}'
                yield request
            finally:
                proc.terminate();proc.wait(timeout=15)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--binary',required=True);args=parser.parse_args()
    with server(args.binary) as request:
        path=lambda table: '/api/collections/'+table+'/records'
        admin=request('POST','/api/collections/_superusers/auth-with-password',{'identity':'admin@example.com','password':'SyntheticAdminPassword123!'})['token']
        def user(email,name):
            u=request('POST',path('users'),{'email':email,'name':name,'password':'SyntheticUserPassword123!','passwordConfirm':'SyntheticUserPassword123!'},admin)
            t=request('POST','/api/collections/users/auth-with-password',{'identity':email,'password':'SyntheticUserPassword123!'})['token'];return u,t
        u,token=user('user@example.com','Test person');u2,t2=user('agent@example.com','Test agent')
        create=lambda table,body: request('POST',path(table),body,token)
        def patch(table,row,body,expected=200,auth=None):
            return request('PATCH',path(table)+'/'+row['id'],dict(expected_revision=row['revision'],**body),auth or token,expected)
        query=lambda sql: request('POST','/api/context/query',{'sql':sql},token)
        request('POST',path('users'),{'id':'dirfailure00001','email':'failure@example.com','name':'Failure','password':'SyntheticUserPassword123!','passwordConfirm':'SyntheticUserPassword123!'},admin,(400,500))
        request('GET',path('users')+'/dirfailure00001',token=admin,expected=404)
        p=create('projects',{'key':'TEST','name':'Test project'})
        request('POST',path('issues'),{'id':'auditfailure001','project':p['id'],'title':'Audit rollback'},token,(400,500))
        request('GET',path('issues')+'/auditfailure001',token=token,expected=404)
        assert p['revision']==1 and p['created_by']==u['id']
        issue=create('issues',{'project':p['id'],'title':'First task','assignee':u2['id']})
        assert issue['key']=='TEST-1' and issue['revision']==1 and issue['reporter']==u['id'] and issue['status']=='backlog'
        request('PATCH',path('issues')+'/'+issue['id'],{'title':'Missing revision'},token,400)
        updated=patch('issues',issue,{'title':'Updated title'})
        patch('issues',issue,{'title':'Stale'},409)
        patch('issues',updated,{'status':'done'},400)
        done=patch('issues',updated,{'status':'done','resolution':'completed'})
        assert done['completed_at']
        patch('issues',done,{'status':'ready'},400)
        reopened=patch('issues',done,{'status':'ready','resolution':''})
        assert not reopened['completed_at']
        for field,value in [('key','FORGED-1'),('number',90),('reporter',u2['id']),('revision',20),('completed_at','nonsense')]:
            patch('issues',reopened,{field:value},400)
        epic=create('issues',{'project':p['id'],'type':'epic','title':'Epic'})
        task=create('issues',{'project':p['id'],'parent':epic['id'],'title':'Child task'})
        sub=create('issues',{'project':p['id'],'type':'subtask','parent':task['id'],'title':'Subtask'})
        patch('issues',task,{'type':'epic'},400)
        patch('issues',epic,{'parent':sub['id']},400)
        p2=create('projects',{'key':'OTHER','name':'Other project'})
        request('POST',path('issues'),{'project':p2['id'],'parent':epic['id'],'title':'Wrong project'},token,400)
        request('POST',path('issues'),{'project':p['id'],'type':'subtask','title':'Orphan'},token,400)
        link=create('issue_links',{'source':task['id'],'target':epic['id'],'type':'relates'})
        assert link['active']
        retired=patch('issue_links',link,{'active':False})
        assert not retired['active']
        request('POST',path('issue_links'),{'source':epic['id'],'target':task['id'],'type':'relates'},token,400)
        request('POST',path('issue_links'),{'source':task['id'],'target':task['id'],'type':'blocks'},token,400)
        comment=create('comments',{'issue':task['id'],'body':'Synthetic discussion'})
        patch('comments',comment,{'body':'Updated discussion'})
        create('references',{'issue':task['id'],'kind':'pull_request','url':'https://example.com/pr/1','title':'Evidence'})
        # Concurrent compare-and-swap: exactly one writer can commit the revision.
        def race(i):
            return patch('issues',reopened,{'title':f'Concurrent {i}'},(200,409))
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(race,range(2)))
        assert sum('id' in r for r in results)==1, results
        # Atomic issue numbering under concurrent creates.
        def make(i): return create('issues',{'project':p['id'],'title':f'Parallel {i}'})
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: records=list(pool.map(make,range(8)))
        assert len({r['key'] for r in records})==8
        audit_before=request('GET',path('audit_log')+'?perPage=1',token=token)['totalItems']
        before=request('GET',path('issues')+'?perPage=1',token=token)['totalItems']
        request('POST','/api/batch',{'requests':[{'method':'POST','url':path('issues'),'body':{'project':p['id'],'title':'Rollback'}},{'method':'POST','url':path('issues'),'body':{'project':p['id'],'type':'subtask','title':'Invalid'}}]},token,400)
        assert request('GET',path('issues')+'?perPage=1',token=token)['totalItems']==before
        assert request('GET',path('audit_log')+'?perPage=1',token=token)['totalItems']==audit_before
        batch=request('POST','/api/batch',{'requests':[{'method':'POST','url':path('issues'),'body':{'id':'batchissue00001','project':p['id'],'title':'Batch task'}},{'method':'POST','url':path('comments'),'body':{'issue':'batchissue00001','body':'Batch comment'}}]},token)
        assert len(batch)==2
        schema=request('GET','/api/context/schema',token=token)
        assert 'user_directory' in json.dumps(schema) and 'project_sequences' not in json.dumps(schema)
        assert u['id'] in json.dumps(query('SELECT id, name FROM user_directory'))
        request('POST','/api/context/query',{'sql':'SELECT * FROM users'},token,400)
        request('POST','/api/context/query',{'sql':'SELECT * FROM project_sequences'},token,400)
        request('GET','/api/context/schema',expected=401)
        for table in ['users','user_directory','audit_log','project_sequences']:
            request('POST',path(table),{},token,(400,403) if table=='users' else 403)
        request('DELETE',path('issues')+'/'+issue['id'],token=token,expected=403)
        request('POST','/api/collections',{'name':'forbidden'},token,403)
        directory=request('GET',path('user_directory')+'/'+u['id'],token=token);assert directory['name']=='Test person'
        request('PATCH',path('users')+'/'+u['id'],{'name':'Renamed'},admin)
        assert request('GET',path('user_directory')+'/'+u['id'],token=token)['name']=='Renamed'
        audits=request('GET',path('audit_log')+'?perPage=200',token=token)['items']
        history=[a for a in audits if a['record']==issue['id']]
        assert len(history)==5, history
        assert all(a['actor']==u['id'] and a['actor_type']=='user' for a in history)
        archived=patch('projects',p2,{'archived':True})
        request('POST',path('issues'),{'project':archived['id'],'title':'Archived'},token,400)
        print('TaskContext integration checks passed')

if __name__=='__main__': main()
