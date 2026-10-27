migrate((app) => {
  const issues = app.findCollectionByNameOrId("issues");
  issues.fields.add(new DateField({name: "due_date"}));
  app.save(issues);
}, () => {
  throw new Error("Issue due date rollback requires a deliberate backup restore.");
});
