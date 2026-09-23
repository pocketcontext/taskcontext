migrate((app) => {
  const users = app.findCollectionByNameOrId("users");
  users.authToken.duration = 604800;
  app.save(users);
}, (app) => {
  const users = app.findCollectionByNameOrId("users");
  users.authToken.duration = 86400;
  app.save(users);
});
