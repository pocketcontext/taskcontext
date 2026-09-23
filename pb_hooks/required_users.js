// Deployment policy, not a second identity store. Existing accounts remain unchanged.
function configured() {
  const raw = $os.getenv("TASKCONTEXT_REQUIRED_USERS").trim();
  if (!raw) return [];
  let users;
  try { users = JSON.parse(raw); } catch (_) {
    throw new Error("TASKCONTEXT_REQUIRED_USERS must be a JSON array of email/name objects");
  }
  if (!Array.isArray(users)) throw new Error("TASKCONTEXT_REQUIRED_USERS must be a JSON array of email/name objects");
  const seen = {};
  return users.map((user) => {
    if (!user || typeof user !== "object" || Array.isArray(user) ||
        typeof user.email !== "string" || typeof user.name !== "string" ||
        Object.keys(user).some((key) => key !== "email" && key !== "name")) {
      throw new Error("TASKCONTEXT_REQUIRED_USERS entries require only email and name strings");
    }
    const email = user.email.trim().toLowerCase();
    const name = user.name.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254 || !name || name.length > 200 || seen[email]) {
      throw new Error("TASKCONTEXT_REQUIRED_USERS contains an invalid or duplicate email/name entry");
    }
    seen[email] = true;
    return {email, name};
  });
}

function ensure(app, allowMissingSchema) {
  const users = configured();
  if (!users.length) return;
  // Bootstrap precedes application migrations on a fresh database. The migration
  // below provisions these accounts once users and its directory are ready.
  if (allowMissingSchema && !app.findAllCollections().some((collection) => collection.name === "user_directory")) return;
  app.runInTransaction((txApp) => {
    const collection = txApp.findCollectionByNameOrId("users");
    txApp.findCollectionByNameOrId("user_directory");
    for (const user of users) {
      const existing = txApp.findRecordsByFilter("users", "email:lower = {:email}", "", 1, 0, {email: user.email});
      if (existing.length) continue;
      const record = new Record(collection);
      record.set("email", user.email);
      record.set("name", user.name);
      // A random password is generated and never logged or retained outside its
      // hash. Google proves the email; operators can arrange password access.
      record.setPassword($security.randomString(64));
      txApp.save(record);
    }
  });
}

function protect(e, deleting) {
  const email = e.record.original().getString("email");
  if (configured().some((user) => user.email === email.toLowerCase()) &&
      (deleting || email !== e.record.getString("email"))) {
    throw new ForbiddenError("This account is required by deployment policy; remove it from TASKCONTEXT_REQUIRED_USERS and restart before changing its email. Disable accounts instead of deleting them.");
  }
  e.next();
}

module.exports = {ensure, protect};
