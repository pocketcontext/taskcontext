/// <reference path="../pb_data/types.d.ts" />
// Model hooks also cover dashboard and internal writes, preserving account IDs
// referenced by assignments and audit history.
onRecordUpdate((e) => require(`${__hooks}/required_users.js`).protect(e, false), "users");
onRecordDelete((e) => require(`${__hooks}/required_users.js`).protect(e, true), "users");
