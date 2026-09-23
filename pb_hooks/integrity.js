function invalid(message) { throw new BadRequestError(message); }
function validate(app,r) {
  const name=r.collection().name, old=r.original();
  if (!r.isNew()) {
    const fields = ['created_by','created'];
    if(name==='projects') fields.push('key');
    if(name==='issues') fields.push('key','number','project','reporter');
    if(name==='comments'||name==='references') fields.push('issue');
    if(name==='issue_links') fields.push('source','target','type');
    for(const field of fields) if(JSON.stringify(r.get(field))!==JSON.stringify(old.get(field))) invalid(field+' is immutable');
  }
  if(name==='issues') {
    const type=r.getString('type'), parent=r.getString('parent');
    if(type==='epic' && parent) invalid('An epic cannot have a parent');
    if(type==='subtask' && !parent) invalid('A subtask requires a task or bug parent');
    if(parent) {
      if(parent===r.id) invalid('An issue cannot parent itself');
      const p=app.findRecordById('issues',parent);
      if(p.getString('project')!==r.getString('project')) invalid('Parent must belong to the same project');
      if(type==='subtask' ? !['task','bug'].includes(p.getString('type')) : p.getString('type')!=='epic') invalid('Invalid parent type');
      const seen=[r.id]; let cursor=p;
      while(cursor) { if(seen.includes(cursor.id)) invalid('Issue hierarchy contains a cycle'); seen.push(cursor.id); const next=cursor.getString('parent'); cursor=next ? app.findRecordById('issues',next):null; }
    }
    if(!r.isNew() && type!==old.getString('type')) {
      const children=app.findRecordsByFilter('issues','parent = {:id}','',0,0,{id:r.id});
      for(const child of children) if(child.getString('type')==='subtask' ? !['task','bug'].includes(type) : type!=='epic') invalid('Type is incompatible with existing children');
    }
    if(r.getString('status')==='done') {
      if(!r.getString('resolution')||!r.getString('completed_at')) invalid('Done requires resolution and completed_at');
    } else if(r.getString('resolution')||r.getString('completed_at')) invalid('Open issues must have empty resolution and completed_at');
  }
  if(name==='issue_links') {
    const source=r.getString('source'),target=r.getString('target'),type=r.getString('type');
    if(source===target) invalid('An issue cannot link to itself');
    if(type==='relates') {
      const reverse=app.findRecordsByFilter('issue_links','source = {:target} && target = {:source} && type = "relates" && id != {:id}','',1,0,{source,target,id:r.id});
      if(reverse.length) invalid('This relates link already exists in reverse');
    }
  }
}
function write(e) {
  const originalApp=e.app, r=e.record, name=r.collection().name, fresh=r.isNew(), body=e.requestInfo().body;
  originalApp.runInTransaction((app)=> {
    e.app=app;
    try {
      if(!fresh) {
        const current=app.findRecordById(name,r.id);
        if(typeof body.expected_revision!=='number'||!Number.isInteger(body.expected_revision)) invalid('expected_revision is required as an integer');
        if(current.getInt('revision')!==body.expected_revision || current.getInt('revision')!==r.original().getInt('revision')) throw new ApiError(409,'Revision conflict; read the record again before retrying.',{});
      }
      const actor=e.auth && e.auth.collection().name==='users' ? e.auth.id : '';
      r.set('_audit_actor',actor ? 'user:'+actor : 'superuser:'+(e.auth ? e.auth.id : ''));
      for(const field of ['revision','created_by','updated_by','created','updated']) if(Object.prototype.hasOwnProperty.call(body,field)) invalid(field+' is server managed');
      r.set('revision',fresh ? 1 : r.original().getInt('revision')+1);
      r.set('created_by',fresh ? actor : r.original().getString('created_by')); r.set('updated_by',actor);
      if(name==='issue_links' && fresh && !Object.prototype.hasOwnProperty.call(body,'active')) r.set('active',true);
      if(name==='issues') {
        for(const field of ['key','number','reporter','completed_at']) if(Object.prototype.hasOwnProperty.call(body,field)) invalid(field+' is server managed');
        if(fresh) {
          const project=app.findRecordById('projects',r.getString('project'));
          if(project.getBool('archived')) invalid('Cannot create issues in an archived project');
          const seqs=app.findRecordsByFilter('project_sequences','project = {:id}','',1,0,{id:project.id});
          const seq=seqs.length ? seqs[0] : new Record(app.findCollectionByNameOrId('project_sequences'));
          const number=seq.getInt('number')+1; seq.set('project',project.id);seq.set('number',number);app.save(seq);
          r.set('number',number);r.set('key',project.getString('key')+'-'+number);r.set('reporter',actor);
          if(!r.getString('type'))r.set('type','task');if(!r.getString('priority'))r.set('priority','medium');if(!r.getString('status'))r.set('status','backlog');
        }
        const status=r.getString('status');
        // Reopening is explicit through status; completion time is always server managed.
        r.set('completed_at',status==='done' ? (r.original().getString('completed_at') || new Date().toISOString().replace('T',' ')) : '');
      }
      e.next();
    } finally { e.app=originalApp; }
  });
}
function snapshot(r) { const all=JSON.parse(JSON.stringify(r)), out={};for(const f of r.collection().fields.fieldNames())out[f]=all[f];return out; }
function audit(e,action) {
  const actor=e.record.getString('_audit_actor');if(!actor)return e.next();e.record.set('_audit_actor','');
  const before=action==='update'?snapshot(e.record.original()):null;
  e.next();
  const after=snapshot(e.record),changes=action==='create'?{after}:{before:{},after:{}};
  if(before)for(const field in after)if(JSON.stringify(before[field])!==JSON.stringify(after[field])){changes.before[field]=before[field];changes.after[field]=after[field];}
  const row=new Record(e.app.findCollectionByNameOrId('audit_log'));
  row.set('action',action);row.set('collection',e.record.collection().name);row.set('record',e.record.id);row.set('actor_type',actor.split(':')[0]);row.set('actor',actor.split(':')[1]);row.set('changes',changes);e.app.save(row);
}
module.exports={validate,write,audit};
