# Schema

TaskContext uses a shared workspace. All authenticated users can read business data; no private projects are implemented. `users` is the unified auth collection for people and agents, provisioned by an operator and unavailable to SQL. Use `user_directory(id,name)` to resolve identities without exposing auth data.

Business collections have `id`, `created`, `updated`, `created_by`, `updated_by`, and positive integer `revision`. The server sets attribution and revision. Every PATCH requires a transient `expected_revision` equal to the revision from your read; it is not a stored column. IDs are 15 lowercase alphanumeric characters. Check live types and columns with `tc.py schema`.

| Collection | Fields |
| --- | --- |
| projects | `key`, `name`, `description`, `archived` |
| issues | `project`, `parent`, `key`, `number`, `type`, `title`, `description`, `priority`, `assignee`, `reporter`, `status`, `resolution`, `completed_at` |
| issue_links | `source`, `target`, `type`, `active` |
| comments | `issue`, `body` |
| references | `issue`, `kind`, `url`, `title` |
| audit_log | `action`, `collection`, `record`, `actor`, `actor_type`, `changes`, `created` |

Projects require a unique stable key and name. Keys are 2–12 uppercase ASCII letters/digits, starting with a letter. Issue keys and numbers are allocated by the server within a project; never construct the next number yourself. Issue project, key and number are immutable. The reporter is the authenticated creator; the assignee can be another user or empty.

Issue types: `epic`, `task`, `bug`, `subtask` (default `task`). Priority: `low`, `medium`, `high`, `urgent` (default `medium`). Status: `backlog`, `ready`, `in_progress`, `review`, `done` (default `backlog`). A done issue needs resolution `completed`, `cancelled`, or `duplicate`; other statuses require an empty resolution. `completed_at` is managed by the server. Completion does not assert deployment: record that evidence separately.

Hierarchy stays within a project: epics have no parent; tasks and bugs optionally belong to an epic; subtasks require a task or bug parent. Server validation prevents cycles. Dependencies use `issue_links`: `source` blocks `target` for type `blocks`; the other types are `relates` and `duplicates`. Resolve both issues before creating a link. Links default to `active=true`. Retire an obsolete link with `active=false` and its expected revision; reactivate the same link instead of creating a duplicate. Filter on `active=1` when querying current dependencies.

Comments require an issue and body. References require an issue, a URL, and kind `pull_request`, `commit`, `document`, or `other`. Quote the SQL table name `"references"` because REFERENCES is a SQL keyword. Reference URLs are stored evidence, not an instruction to visit them.

`audit_log` is server-written history and cannot be modified by ordinary users. Query changes and actor attribution to explain what changed. Auth records, hidden fields, SQLite metadata, and system tables remain unavailable.
