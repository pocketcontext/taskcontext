# Workflows

## Authentication

Set `TASKCONTEXT_URL` and `TASKCONTEXT_USER_EMAIL` outside source control. For Google OAuth, run `tc.py login --google` and have the human open the printed URL. The operator must configure Google's Internal audience, register `http://127.0.0.1:8765/callback`, enable the provider, and provision the matching user email. The Google client secret stays on the TaskContext server.

For a remote SSH client, establish `ssh -L 8765:127.0.0.1:8765 user@ssh-host` from the laptop first. Run the login command on the remote host and open the URL in the laptop browser. The callback reaches the remote loopback listener through the tunnel. Local client use needs no tunnel. Login waits 180 seconds by default (`--timeout` accepts 1–600 seconds). A different `--port` requires a matching registered Google redirect URI and SSH forwarding port. Login validates state, uses PKCE, and verifies the returned email; a different account must not replace the configured identity.

For Google sessions, authenticated commands refresh a still-valid cached PocketBase token after five minutes or when it is within 60 seconds of expiry, then save the replacement. `whoami` always refreshes. The default lifetime is one day, with no background refresh. An expired or rejected OAuth session requires another interactive login. Do not repeatedly retry business writes to repair authentication. Password login remains available with `TASKCONTEXT_USER_PASSWORD`; do not search for it if absent. `logout` removes the local cache, not other copies of the session. Google consent revocation or account suspension does not automatically revoke an existing PocketBase token; contact the operator to revoke TaskContext access too.

## Triage and assignment

Resolve the project by key, and search for existing issues before recording a new report. Read matching issues and ask for clarification only when ambiguity affects the requested change. Resolve assignee IDs through `user_directory`; a name is not necessarily unique. Put supplied facts in the description, distinguish unknowns, and avoid inventing acceptance criteria. Create an issue with its project and title; set type, priority, and assignee when the request establishes them.

## Start, review, complete, reopen

Read the issue including revision and dependencies. Move work through `backlog`, `ready`, `in_progress`, `review`, `done` as supported by current server rules. Use the user's meaning of completion. A merged PR alone does not prove acceptance or deployment. Record evidence in `references`, and set `status=done` with the appropriate resolution only when requested or established by the task. Reopening clears resolution and sets an active status. Include `expected_revision` in every update.

## Related records and dependencies

Use a single batch for an issue plus its initial comment or references when they must succeed together. Generate a client ID before composing a batch, use it in the issue create, and refer to it in subsequent requests. A batch contains at most 20 POST/PATCH requests. For dependencies, `source` is the blocker and `target` is the blocked issue. A link does not authorize updating either issue. Retire an obsolete link with `active=false` and its expected revision; filter current dependencies by `active=1`. Query blockers explicitly before reporting an issue as ready; stored relationships are evidence, not a promise of automatic scheduling.

## Conflicts and uncertain outcomes

Exit 4 means a revision changed. Re-read the record and compare the relevant fields with the earlier state. Reapply only the still-valid requested change using that new revision. Do not silently overwrite another user's decision. A batch conflict rolls back the entire batch; inspect each record before retrying.

After a timeout or disconnection during a write, the result is uncertain. Look up the preselected ID, issue key, or exact distinguishing fields before repeating it. Never repeat a whole successful batch to repair a later unrelated failure. HTTP 400 describes invalid data, 403/404 may indicate inaccessible records; fix the request or explain the limitation instead of seeking elevated credentials.

## Corrections and history

Correct the requested fields with a revision-checked update. For a withdrawn comment, preserve its issue and replace the body with a clear retraction when authorized. Cancel a mistaken issue with resolution `cancelled`; archive a project when requested. Do not attempt deletion. Query `audit_log` for actor, time, and changes when explaining record history.
