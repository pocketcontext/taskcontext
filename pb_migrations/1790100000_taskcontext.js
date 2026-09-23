migrate((app) => {
  const access = "@request.auth.id != '' && @request.auth.collectionName = 'users'";
  let users;
  try { users = app.findCollectionByNameOrId('users'); } catch (_) { users = new Collection({type:'auth', name:'users'}); }
  users.listRule = null; users.viewRule = "id = @request.auth.id && @request.auth.collectionName = 'users'";
  users.createRule = null;
  users.updateRule = "id = @request.auth.id && @request.auth.collectionName = 'users'" +
    " && @request.body.email:isset = false && @request.body.name:isset = false" +
    " && @request.body.verified:isset = false && @request.body.emailVisibility:isset = false";
  users.deleteRule = null;
  users.fields.removeByName('avatar');
  users.fields.add(new TextField({name:'name', required:true, max:200}));
  users.passwordAuth = {enabled:true, identityFields:['email']};
  users.authToken.duration = 86400; users.authAlert.enabled = false;
  app.save(users);
  const text = (name, required=false, max=500) => ({name,type:'text',required,max});
  const rel = (name, collection, required=false) => ({name,type:'relation',collectionId:app.findCollectionByNameOrId(collection).id,maxSelect:1,required,cascadeDelete:false});
  const select = (name, values, required=true) => ({name,type:'select',values,maxSelect:1,required});
  function create(name, fields, indexes=[], writable=true) {
    app.save(new Collection({name,type:'base',listRule:access,viewRule:access,createRule:writable?access:null,updateRule:writable?access:null,deleteRule:null,
      fields:fields.concat(writable ? [rel('created_by','users'),rel('updated_by','users'),{name:'revision',type:'number',required:true,min:1,onlyInt:true},
        {name:'created',type:'autodate',onCreate:true},{name:'updated',type:'autodate',onCreate:true,onUpdate:true}] : []), indexes}));
  }
  create('user_directory',[text('name',true,200)],[],false);
  create('projects',[{name:'key',type:'text',required:true,max:12,pattern:'^[A-Z][A-Z0-9]{1,11}$'},text('name',true),text('description',false,100000),{name:'archived',type:'bool'}],['CREATE UNIQUE INDEX idx_projects_key ON projects (key)']);
  create('issues',[text('key',true,40),{name:'number',type:'number',required:true,min:1,onlyInt:true},rel('project','projects',true),select('type',['epic','task','bug','subtask']),text('title',true),text('description',false,100000),select('priority',['low','medium','high','urgent']),rel('assignee','users'),rel('reporter','users'),select('status',['backlog','ready','in_progress','review','done']),select('resolution',['completed','cancelled','duplicate'],false),{name:'completed_at',type:'date'}],['CREATE UNIQUE INDEX idx_issues_key ON issues (key)','CREATE UNIQUE INDEX idx_issues_number ON issues (project, number)','CREATE INDEX idx_issues_status ON issues (project, status)']);
  const issues = app.findCollectionByNameOrId('issues'); issues.fields.add(new RelationField(rel('parent','issues'))); app.save(issues);
  create('issue_links',[rel('source','issues',true),rel('target','issues',true),select('type',['blocks','relates','duplicates']),{name:'active',type:'bool'}],['CREATE UNIQUE INDEX idx_issue_links_unique ON issue_links (source,target,type)']);
  create('comments',[rel('issue','issues',true),text('body',true,100000)]);
  create('references',[rel('issue','issues',true),select('kind',['pull_request','commit','document','other']),{name:'url',type:'url',required:true},text('title',false)]);
  create('audit_log',[select('action',['create','update','delete']),text('collection',true),text('record',true),text('actor'),select('actor_type',['user','superuser']),{name:'changes',type:'json',maxSize:5242880},{name:'created',type:'autodate',onCreate:true}],['CREATE INDEX idx_audit_record ON audit_log (collection,record,created)'],false);
  app.save(new Collection({name:'project_sequences',type:'base',fields:[rel('project','projects',true),{name:'number',type:'number',onlyInt:true,min:0}],indexes:['CREATE UNIQUE INDEX idx_sequence_project ON project_sequences (project)']}));
  const settings = app.settings(); settings.batch.enabled=true; settings.batch.maxRequests=20; settings.batch.timeout=5; app.save(settings);
}, (app) => { throw new Error('Initial schema rollback requires a deliberate backup restore.'); });
