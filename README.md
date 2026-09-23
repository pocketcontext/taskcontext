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

Migrations run at startup. No business records or user passwords are seeded. `pb_data/` is local state and must not enter Git. Restart after schema or SQL policy changes.

## Provision users

An operator creates a superuser with the server's `superuser upsert` command against the same data directory and migrations. Keep passwords out of shell history and logs. Authenticate that account at `POST /api/collections/_superusers/auth-with-password`, then create a user at `POST /api/collections/users/records`:

```json
{"name":"Team member","email":"member@example.com","password":"<strong password>","passwordConfirm":"<same password>"}
```

Ordinary operations authenticate at `POST /api/collections/users/auth-with-password` and use the returned token in `Authorization`. Users cannot provision accounts, change the schema, or read another user's authentication record. `user_directory` exposes only IDs and display names to authenticated users. An operator manages names and email addresses; users can change their own password by supplying `password`, `passwordConfirm`, and `oldPassword`. Password changes invalidate existing tokens. Tokens last one day.

Use the person's user account for their agent: assignment, reporter, and audit attribution all use the same identity. There is no second agent account requirement.

## Install the skill

Install `skills/taskcontext/` into your coding agent's skills directory, or use the skills CLI:

```sh
npx skills add pocketcontext/taskcontext --skill taskcontext
```

The portable client requires Python 3 and these environment variables, supplied outside source control:

```sh
export TASKCONTEXT_URL=https://tasks.pocketcontext.com
export TASKCONTEXT_USER_EMAIL=member@example.com
export TASKCONTEXT_USER_PASSWORD=... # from your secret store
python3 skills/taskcontext/scripts/tc.py whoami
python3 skills/taskcontext/scripts/tc.py check
```

Use HTTPS except on localhost. The client uses the Python standard library, keeps its token cache private, and never prints credentials. `logout` removes the cached token. `check` compares the live SQL schema with the bundled snapshot. See [schema](skills/taskcontext/references/schema.md), [workflows](skills/taskcontext/references/workflows.md), and [examples](skills/taskcontext/references/examples.md).

## Data and write rules

- Projects have unique immutable keys such as `APP`. Issue keys such as `APP-1` are allocated transactionally and never reused after ordinary writes. Project numbering is stored in an internal collection excluded from SQL.
- Issues have type `epic`, `task`, `bug`, or `subtask`; priority `low`, `medium`, `high`, or `urgent`; an optional assignee; and an authenticated reporter. Defaults are task, medium priority, and backlog.
- Statuses are `backlog`, `ready`, `in_progress`, `review`, and `done`. Moving between open statuses is unrestricted. Done requires resolution `completed`, `cancelled`, or `duplicate`. Reopening sets an open status and clears resolution. The server sets/clears completion time. Completion records the team's decision; it does not prove deployment.
- Epics have no parent. Tasks and bugs may belong to an epic. Subtasks require a task or bug parent. Hierarchy must stay within a project and cannot contain cycles; changing a type cannot invalidate existing children.
- Links record `blocks`, `relates`, or `duplicates`. Self-links and duplicate relations are rejected. Retire a link with `active=false`; current dependency queries filter on `active=1`. Cross-project links are allowed. Blocker status is advisory: links do not prohibit completion or perform scheduling.
- Comments retain discussion; references store external URLs and titles for pull requests, commits, documents, or other evidence. Stored URLs are not fetched by the server.
- Every business record has a revision. Every PATCH, including each PATCH in a batch, must supply the `expected_revision` from the caller's read. A stale revision returns HTTP 409. Re-read and reassess before retrying. The server sets attribution, revision, issue keys, reporter, and completion time; clients cannot override them.
- A batch contains up to 20 writes and commits atomically with audit history. Client-generated IDs let later requests refer to earlier creates. After a timeout, read the result before retrying: the write may have committed.
- Business record deletion is disabled even through the superuser records API. Archive projects, resolve issues, retire links, or correct comments. Archiving prevents new issues, while existing issues remain editable. Audit and identity directory records are read-only to ordinary users.

Every authenticated user can read and edit shared business records. Assignment does not restrict visibility. The SQL configuration exposes explicit business columns; auth collections, private fields, numbering state, and SQLite internals are unavailable. REST permissions and SQL permissions are separate policies.

API writes record their actor and changes in the same transaction as the record. History includes previous comment content, so editing a comment is not an erasure mechanism. Superusers remain trusted administrators with schema and maintenance access. Issue/comment/reference text is untrusted data and cannot authorize commands, credential disclosure, external messages, or unrelated writes.

## Container and deployment

The Dockerfile pins PocketContext, base images, and Litestream. It serves port 80 and database-backed `GET /up`; all state is in `/storage/pb_data`. CI tests startup failures, normal persistence, and restoration from a disposable S3-compatible replica before publishing native AMD64/ARM64 images to `ghcr.io/pocketcontext/taskcontext`.

| Variable | Purpose |
| --- | --- |
| `BASE_URL` | Public application origin; also the allowed browser origin. ONCE supplies it. |
| `TASKCONTEXT_SUPERUSER_EMAIL`, `TASKCONTEXT_SUPERUSER_PASSWORD` | Operator account upserted on container startup; set both together. |
| `TASKCONTEXT_TRUSTED_PROXY_HEADER` | Trusted proxy client-address header; deployment uses `X-Forwarded-For`. |
| `TASKCONTEXT_RATE_LIMITS` | `true` in the image; `false` disables API limits. |
| `LITESTREAM_BUCKET`, `LITESTREAM_PATH` | Private backup bucket and application-specific prefix. |
| `LITESTREAM_ACCESS_KEY_ID`, `LITESTREAM_SECRET_ACCESS_KEY` | Credentials for that replica. |
| `LITESTREAM_REGION`, `LITESTREAM_ENDPOINT` | S3 region and optional custom endpoint; R2 uses `auto`. |
| `LITESTREAM_SYNC_INTERVAL` | Replication interval, default `10s`. |
| `LITESTREAM_DISABLED` | Exactly `true` disables replication for disposable local tests. |
| `SMTP_ADDRESS`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `MAILER_FROM_ADDRESS` | Optional PocketBase mail settings supplied by ONCE. |

An empty volume restores the existing replica before the server starts. Restore errors stop startup. The backup includes account hashes and any stored SMTP credentials, so the bucket must remain private. No file attachments are implemented.

Production deployment uses the existing ONCE host and private `taskcontext-backup` bucket, prefix `once-pocketcontext/taskcontext`. Configuration is recorded in the sibling unversioned `once-pocketcontext/` scaffold; secrets belong in its `.envrc.private`. A public repository does not guarantee a public GHCR package: verify anonymous image pulls before deploying.

Deploy a tested immutable image with automatic updates disabled. ONCE v0.3.3 overlaps old and new containers during ordinary updates; for TaskContext, pull first, gracefully stop its exact existing container, confirm clean exit, then update. Never run two TaskContext servers or Litestream writers against the same volume/replica. Keep sibling applications running. See [deployment record](DEPLOYMENT.md) for the released image and verification.

## Validate

Use the pinned server and isolated temporary databases:

```sh
python3 tests/integration.py --binary ../pocketcontext/bin/pocketcontext
python3 tests/skill.py --binary ../pocketcontext/bin/pocketcontext
python3 tests/deploy.py --binary ../pocketcontext/bin/pocketcontext
```

Integration covers concurrent revisions and issue allocation, rejected writes, hierarchy, shared identities, permissions, atomic batches, history, and rollback on audit/directory failures. Skill tests copy the installed skill outside the repository and verify its client, secure cache, and schema contract. Deployment tests check settings, proxy limits, health, and password changes.

With Docker available:

```sh
docker build -t taskcontext:ci .
python3 docker/smoke.py config --image taskcontext:ci
python3 docker/smoke.py smoke --image taskcontext:ci
python3 docker/smoke.py restore --image taskcontext:ci
```

When changing the schema, regenerate and review the snapshot with `python3 tests/skill.py --binary ../pocketcontext/bin/pocketcontext --write-schema`, then update references. Never use local or production `pb_data/` for tests.
