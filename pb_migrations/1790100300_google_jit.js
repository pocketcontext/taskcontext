migrate((app) => {
  const users = app.findCollectionByNameOrId("users");
  // PocketBase sets this context internally only during OAuth record creation.
  // The Google hook validates the provider identity before this path is reached.
  users.createRule = "@request.context = 'oauth2'";
  app.save(users);
}, (app) => {
  const users = app.findCollectionByNameOrId("users");
  users.createRule = null;
  app.save(users);
});
