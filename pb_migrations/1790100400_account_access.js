migrate((app) => {
  const users = app.findCollectionByNameOrId("users");
  users.fields.add(new BoolField({name: "disabled"}));
  users.authRule = "disabled = false";
  users.updateRule += " && @request.body.disabled:isset = false";
  app.save(users);
}, () => {
  throw new Error("Account access rollback requires a deliberate backup restore.");
});
