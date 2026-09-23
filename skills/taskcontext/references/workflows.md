# Workflows

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
