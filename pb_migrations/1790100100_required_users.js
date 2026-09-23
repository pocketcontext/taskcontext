migrate((app) => {
  require(`${__hooks}/required_users.js`).ensure(app, false);
}, (app) => {
  // Provisioned identities and their attribution must survive rollback.
});
