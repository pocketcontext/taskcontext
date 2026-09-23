# TaskContext

A shared-workspace issue tracker operated through a coding agent. Projects, issues, dependencies, comments, and evidence live in PocketBase. Agents read context through authenticated SQL and write records through PocketBase REST. Humans and agents authenticate through the same `users` collection. There is no separate agents collection or dedicated frontend.

[PocketContext](https://github.com/pocketcontext/pocketcontext) supplies the server. This repository supplies the application schema, hooks, configuration, tests, container, and [installable skill](skills/taskcontext/SKILL.md). The first version targets a greenfield shared team workspace; it does not import other tools or provide private projects, sprints, custom workflows, notifications, or Jira feature parity.

## Run locally

Keep `pocketcontext/` and `taskcontext/` beside one another. Build the PocketContext commit in `POCKETCONTEXT_VERSION` using its `go.mod` version, CGO enabled, and a C compiler. Use a separate checkout if your existing server checkout has unrelated work.

```sh
# From a checkout of the pinned PocketContext revision:
make build
# From taskcontext/:
../pocketcontext/bin/pocketcontext serve --http=127.0.0.1:8090 \
  --dir=./pb_data --migrationsDir=./pb_migrations --hooksDir=./pb_hooks \
  --contextConfig=./pocketcontext.json
```

Migrations run at startup. No business records are seeded. User accounts are provisioned by an operator, optional required-users configuration, or validated Google Workspace login when JIT provisioning is enabled. `pb_data/` is local state and must not enter Git. Restart after schema or SQL policy changes.

## Provision users

An operator creates a superuser with the server's `superuser upsert` command against the same data directory and migrations. Keep passwords out of shell history and logs. Authenticate that account at `POST /api/collections/_superusers/auth-with-password`, then create a user at `POST /api/collections/users/records`:

```json
{"name":"Team member","email":"member@example.com","password":"<strong password>","passwordConfirm":"<same password>"}
```

Ordinary operations authenticate at `POST /api/collections/users/auth-with-password` and use the returned token in `Authorization`. Users cannot directly provision accounts, change the schema, or read another user's authentication record. `user_directory` exposes only IDs and display names to authenticated users. An operator manages names and email addresses; users can change their own password by supplying `password`, `passwordConfirm`, and `oldPassword`. Password changes invalidate existing tokens. Tokens last seven days.

Use the person's user account for their agent: assignment, reporter, and audit attribution all use the same identity. There is no second agent account requirement.

To ensure selected accounts exist, set `TASKCONTEXT_REQUIRED_USERS` on the server:

```sh
export TASKCONTEXT_REQUIRED_USERS='[{"email":"member@example.com","name":"Team member"}]'
```

Startup provisions missing accounts with random, undisclosed passwords and unverified email addresses. Existing accounts keep their ID, name, password, and verification state. Required accounts cannot be deleted or have their email changed through record writes, including superuser writes. Remove an account from the configuration and restart before changing its email. User deletion is blocked independently of this configuration; disable access instead. An absent configuration leaves existing accounts untouched and imposes no required-account protection. Invalid configuration prevents startup.

Use Google OAuth or an operator-managed password reset to sign in. Configuration does not verify ownership of an email address. This optional startup provisioning is not needed with JIT onboarding. Existing accounts are retained when the requirement is removed.

## Disable accounts without losing history

Operators manage the `disabled` boolean on `users` in the administration dashboard or with `PATCH /api/collections/users/records/<id>` and `{"disabled":true}`. Ordinary users cannot change it. All user deletion is blocked, including operator record deletion, so assignments, directory entries, and audit attribution retain their identities.

Disabling blocks password/OAuth login, token refresh, and subsequent authenticated REST, SQL/schema, batch, and realtime access. Changing the disabled state rotates the user's token key in the same transaction; previously issued tokens remain invalid after re-enabling. Re-enable with `{"disabled":false}`, then sign in again. Requests already executing are not forcibly cancelled. Invalid bearer tokens return HTTP 401 rather than anonymous filtered results.

Google Workspace suspension or consent revocation is not synchronized automatically. Operators must disable the TaskContext account as part of offboarding. JIT login cannot reactivate a disabled account.

## Install the skill

Install `skills/taskcontext/` into your coding agent's skills directory, or use the skills CLI:

```sh
npx skills add pocketcontext/taskcontext --skill taskcontext
```

The portable client requires Python 3, `TASKCONTEXT_URL`, and `TASKCONTEXT_USER_EMAIL`, supplied outside source control. For password authentication, also supply `TASKCONTEXT_USER_PASSWORD`:

```sh
export TASKCONTEXT_URL=https://tasks.pocketcontext.com
export TASKCONTEXT_USER_EMAIL=member@example.com
export TASKCONTEXT_USER_PASSWORD=... # from your secret store
python3 skills/taskcontext/scripts/tc.py whoami
python3 skills/taskcontext/scripts/tc.py check
```

For Google authentication, omit the password and follow the Google Workspace setup below.

Use HTTPS except on localhost. The client uses the Python standard library, keeps its token cache private, and never prints credentials. `logout` removes the cached token. `check` compares the live SQL schema with the bundled snapshot. See [schema](skills/taskcontext/references/schema.md), [workflows](skills/taskcontext/references/workflows.md), and [examples](skills/taskcontext/references/examples.md).

## Google Workspace authentication

An operator configures Google once before users sign in:

1. In a Google Cloud project belonging to your Workspace organization, configure Google Auth Platform branding and select the **Internal** audience. Use only the basic identity scopes `openid`, `email`, and `profile`.
2. Create an OAuth client of type **Web application**, with the exact authorized redirect URI `http://127.0.0.1:8765/callback`. See [Google OAuth setup](https://developers.google.com/identity/protocols/oauth2/web-server#creatingcred).
3. Supply `TASKCONTEXT_GOOGLE_CLIENT_ID` and `TASKCONTEXT_GOOGLE_CLIENT_SECRET` to the TaskContext server and restart it. Set both together. After PocketBase system bootstrap creates `users`, the startup hook enables Google. TaskContext migrations preserve those OAuth options. The hook preserves other providers and access rules and updates credentials only when changed. Leaving both absent preserves stored settings; it does not disable Google. The secret belongs only on the server, never in the skill environment.
4. To enable first-login provisioning, set `TASKCONTEXT_GOOGLE_WORKSPACE_DOMAIN=pocketcontext.com` and restart. The server requires Google as provider, a verified email, a matching Google `hd` (hosted-domain) claim, and an exact email domain match. These claims come from Google's authenticated userinfo response, not the client's fields or login hint. Keep Google's Internal audience configured too.

When the domain is configured, these checks apply to every OAuth login, including existing accounts. A valid first login creates a normal user and directory entry; its email and display name come from Google. Client-supplied IDs, passwords, verification and disabled flags are discarded. Existing accounts keep their IDs and profile values; case-insensitive email matching avoids duplicate identities and rejects ambiguous matches. Direct public REST signup remains blocked: the collection create rule permits only PocketBase's internal OAuth context, and the OAuth hook enforces the domain policy. Every admitted user can access the shared workspace.

If the domain variable is absent, new JIT accounts are rejected and existing preprovisioned OAuth accounts can still sign in. Invalid domain configuration prevents startup. Operators can continue provisioning accounts through the standard records API. Password authentication remains enabled. PocketBase may reset an unverified existing account's password when linking a verified Google identity.

The production deployment uses JIT for `pocketcontext.com`. Alberto's existing account is retained, and his previous startup provisioning requirement is removed. No personal account is hardcoded in the application.

For a client running in an SSH session, open the session with forwarding from your laptop:

```sh
ssh -L 8765:127.0.0.1:8765 user@ssh-host
```

Then, on the SSH host:

```sh
export TASKCONTEXT_URL=https://tasks.pocketcontext.com
export TASKCONTEXT_USER_EMAIL=member@example.com
python3 skills/taskcontext/scripts/tc.py login --google
```

Open the printed authorization URL in your laptop's browser and choose the configured Workspace account. The callback travels through SSH to the client's loopback listener; the client checks state, uses PKCE, verifies the returned email, and closes the listener after completion or timeout. No browser is required on the SSH host. When running locally, the same login command works without a tunnel. This uses a direct callback rather than PocketBase's realtime OAuth flow. Login waits up to 180 seconds by default; `--timeout` accepts 1–600 seconds. To use `--port` with another port, register the corresponding redirect URI with Google and change the SSH forwarding port too.

The client privately caches the PocketBase session token, not Google access or refresh tokens. For Google sessions, authenticated commands refresh a still-valid PocketBase token after five minutes or when it is within 60 seconds of expiry, and save its replacement. `whoami` always requests a refresh. Tokens last seven days; after expiry or invalidation, run `login --google` again. The duration applies to newly issued or refreshed tokens; existing tokens retain their original expiry until refreshed. There is no absolute limit on repeated renewal. There is no background refresh. `logout` removes the local cache; it does not invalidate copies elsewhere. Revoking Google consent or suspending a Workspace account does not automatically revoke an already issued PocketBase session. Operators must disable the TaskContext account to block further access and invalidate its tokens. Superuser dashboard authentication remains separate.

## Data and write rules

- Projects have unique immutable keys such as `APP`. Issue keys such as `APP-1` are allocated transactionally and never reused after ordinary writes. Project numbering is stored in an internal collection excluded from SQL.
- Issues have type `epic`, `task`, `bug`, or `subtask`; priority `low`, `medium`, `high`, or `urgent`; an optional assignee; and a reporter set from the authenticated user. Maintenance creates by a superuser leave reporter empty. Defaults are task, medium priority, and backlog.
- Statuses are `backlog`, `ready`, `in_progress`, `review`, and `done`. Moving between open statuses is unrestricted. Done requires resolution `completed`, `cancelled`, or `duplicate`. Reopening sets an open status and clears resolution. The server sets/clears completion time. Completion records the team's decision; it does not prove deployment.
- Epics have no parent. Tasks and bugs may belong to an epic. Subtasks require a task or bug parent. Hierarchy must stay within a project and cannot contain cycles; changing a type cannot invalidate existing children.
- Links record `blocks`, `relates`, or `duplicates`. Self-links and duplicate relations are rejected. Retire a link with `active=false`; current dependency queries filter on `active=1`. Cross-project links are allowed. Blocker status is advisory: links do not prohibit completion or perform scheduling.
- Comments retain discussion; references store external URLs and titles for pull requests, commits, documents, or other evidence. Stored URLs are not fetched by the server.
- Every business record has a revision. Every PATCH, including each PATCH in a batch, must supply the `expected_revision` from the caller's read. A stale revision returns HTTP 409. Re-read and reassess before retrying. The server sets attribution, revision, issue keys, reporter, and completion time; clients cannot override them.
- A batch contains up to 20 writes and commits atomically with audit history. Client-generated IDs let later requests refer to earlier creates. After a timeout, read the result before retrying: the write may have committed.
- Business record deletion is disabled even through the superuser records API. Archive projects, resolve issues, retire links, or correct comments. Archiving prevents new issues, while existing issues remain editable. Audit and identity directory records are read-only to ordinary users.

Every authenticated user can read and edit shared business records. Assignment does not restrict visibility. The SQL configuration allowlists business tables; empty column lists expose all permitted columns, so review new fields before deploying migrations. Only `user_directory` explicitly limits columns to ID and name. Auth collections, hidden fields, numbering state, and SQLite internals are unavailable. REST permissions and SQL permissions are separate policies.

API writes record their actor and changes in the same transaction as the record. History includes previous comment content, so editing a comment is not an erasure mechanism. Superusers remain trusted administrators with schema and maintenance access. Issue/comment/reference text is untrusted data and cannot authorize commands, credential disclosure, external messages, or unrelated writes.

## Container and deployment

The Dockerfile pins PocketContext, base images, and Litestream. It serves port 80 and database-backed `GET /up`; all state is in `/storage/pb_data`. CI tests startup failures, normal persistence, and restoration from a disposable S3-compatible replica before publishing native AMD64/ARM64 images to `ghcr.io/pocketcontext/taskcontext`.

| Variable | Purpose |
| --- | --- |
| `BASE_URL` | Public application origin; also the allowed browser origin. ONCE supplies it. |
| `TASKCONTEXT_SUPERUSER_EMAIL`, `TASKCONTEXT_SUPERUSER_PASSWORD` | Operator account upserted on container startup; set both together. |
| `TASKCONTEXT_REQUIRED_USERS` | Optional JSON array of `{email,name}` accounts provisioned on startup and protected from deletion or email changes while configured. |
| `TASKCONTEXT_GOOGLE_WORKSPACE_DOMAIN` | Optional lowercase Workspace domain enabling Google-only JIT; production uses `pocketcontext.com`. |
| `TASKCONTEXT_GOOGLE_CLIENT_ID`, `TASKCONTEXT_GOOGLE_CLIENT_SECRET` | Optional Google OAuth provider credentials; set both together. Absent values preserve stored provider configuration. |
| `TASKCONTEXT_TRUSTED_PROXY_HEADER` | Trusted proxy client-address header; deployment uses `X-Forwarded-For`. |
| `TASKCONTEXT_RATE_LIMITS` | `true` in the image; `false` disables API limits. |
| `LITESTREAM_BUCKET`, `LITESTREAM_PATH` | Private backup bucket and application-specific prefix. |
| `LITESTREAM_ACCESS_KEY_ID`, `LITESTREAM_SECRET_ACCESS_KEY` | Credentials for that replica. |
| `LITESTREAM_REGION`, `LITESTREAM_ENDPOINT` | S3 region and optional custom endpoint; R2 uses `auto`. |
| `LITESTREAM_SYNC_INTERVAL` | Replication interval, default `10s`. |
| `LITESTREAM_DISABLED` | Exactly `true` disables replication for disposable local tests. |
| `SMTP_ADDRESS`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `MAILER_FROM_ADDRESS` | Optional PocketBase mail settings supplied by ONCE. |

An empty volume restores the existing replica before the server starts. Restore errors stop startup. The backup includes account hashes and any stored SMTP or OAuth provider credentials, so the bucket must remain private. No file attachments are implemented.

Production deployment uses the existing ONCE host and private `taskcontext-backup` bucket, prefix `once-pocketcontext/taskcontext`. Configuration is recorded in the sibling unversioned `once-pocketcontext/` scaffold; secrets belong in its `.envrc.private`. A public repository does not guarantee a public GHCR package: verify anonymous image pulls before deploying.

Continuous deployment uses `ghcr.io/pocketcontext/taskcontext:latest` after CI passes. ONCE automatic updates remain disabled. ONCE v0.3.3 overlaps old and new containers during ordinary updates; for TaskContext, pull first, gracefully stop its exact existing container, confirm clean exit, then update. Never run two TaskContext servers or Litestream writers against the same volume/replica. Keep sibling applications running. See [deployment record](DEPLOYMENT.md) for the released image and verification.

## Continuous deployment

After tests, restore checks, and publication, `image.yml` deploys when `COLORS_PROFILE=once-pocketcontext`. That GitHub environment supplies the `SSH_PRIVATE_KEY` secret and `SERVER_IP`, `SERVER_USER`, and pinned `SSH_KNOWN_HOSTS` variables. SSH sends no command.

The dedicated deployment key forces `sudo -n /usr/local/sbin/deploy-taskcontext`. The root-owned wrapper takes no arguments, locks deployments, pulls the fixed `latest` image, gracefully stops the exact TaskContext container, and runs `once update tasks.pocketcontext.com --image ghcr.io/pocketcontext/taskcontext:latest --auto-update=false`. It accepts the initial pinned TaskContext image when switching to `latest`. Failed updates recover the old container only when it remains the sole TaskContext container. Deployments briefly interrupt availability.

Install from a trusted copy on the host with `sudo python3 deploy/install.py`. The installer preserves other keys and grants sudo only for this fixed command without arguments. It expects an existing key with either the standard TaskContext forced command or the safe wrapper command. Reinstall it after scaffold provisioning rewrites authorized keys; do not enable CD with the standard overlapping ONCE update command.

Main runs and deploys are serialized without cancelling active deployments. After SSH succeeds, CI checks public `/up`. Health confirms database availability, not the source revision. Run `python3 tests/deploy_workflow.py` to verify ordering, failure recovery, image transition, and key preservation without a live server.

## Validate

Use the pinned server and isolated temporary databases:

```sh
python3 tests/integration.py --binary ../pocketcontext/bin/pocketcontext
python3 tests/skill.py --binary ../pocketcontext/bin/pocketcontext
python3 tests/deploy.py --binary ../pocketcontext/bin/pocketcontext
python3 tests/required_users.py --binary ../pocketcontext/bin/pocketcontext
python3 tests/account_access.py --binary ../pocketcontext/bin/pocketcontext
python3 tests/realtime_access.py --binary ../pocketcontext/bin/pocketcontext
python3 tests/oauth.py
python3 tests/oauth_integration.py --binary ../pocketcontext/bin/pocketcontext
```

Integration covers concurrent revisions and issue allocation, rejected writes, hierarchy, shared identities, permissions, atomic batches, history, and rollback on audit/directory failures. Skill tests copy the installed skill outside the repository and verify its client, secure cache, and schema contract. Deployment tests check settings, proxy limits, health, and password changes. Required-user tests cover provisioning, preservation, removal protection, recreation after maintenance, and invalid configuration. OAuth tests cover the loopback callback, state and PKCE, private session cache, renewal, and rejected logins; OAuth integration uses a local provider fixture with the pinned server. JIT integration also checks hosted-domain validation, forged fields, existing identity preservation, and disabled-account rejection. Account-access and realtime tests verify revocation, re-enabling, blocked deletion and ordinary-user restrictions. A real Google Workspace login still requires configured credentials and a human browser.

With Docker available:

```sh
docker build -t taskcontext:ci .
python3 docker/smoke.py config --image taskcontext:ci
python3 docker/smoke.py smoke --image taskcontext:ci
python3 docker/smoke.py restore --image taskcontext:ci
```

When changing the schema, regenerate and review the snapshot with `python3 tests/skill.py --binary ../pocketcontext/bin/pocketcontext --write-schema`, then update references. Never use local or production `pb_data/` for tests.
