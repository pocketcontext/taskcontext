onRecordValidate((e) => { e.next(); require(`${__hooks}/integrity.js`).validate(e.app,e.record); }, 'projects','issues','issue_links','comments','references');
onRecordCreateRequest((e) => require(`${__hooks}/integrity.js`).write(e), 'projects','issues','issue_links','comments','references');
onRecordUpdateRequest((e) => require(`${__hooks}/integrity.js`).write(e), 'projects','issues','issue_links','comments','references');
onRecordDeleteRequest((e) => { throw new ForbiddenError('Records are retained for history; archive projects or resolve issues instead.'); }, 'projects','issues','issue_links','comments','references');
onRecordCreateExecute((e) => require(`${__hooks}/integrity.js`).audit(e,'create'), 'projects','issues','issue_links','comments','references');
onRecordUpdateExecute((e) => require(`${__hooks}/integrity.js`).audit(e,'update'), 'projects','issues','issue_links','comments','references');
