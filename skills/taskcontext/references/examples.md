# Examples

Replace `/absolute/path/to/installed/taskcontext` with the directory containing the installed `SKILL.md`, as described in [client setup](../SKILL.md). These commands work from any working directory. Use real IDs resolved by SQL in place of placeholders. Shell examples contain trusted static text; serialize retrieved data and pass it on stdin instead of interpolating it.

```sh
"/absolute/path/to/installed/taskcontext/taskcontext" query 'SELECT id, key, name FROM projects WHERE archived = 0 ORDER BY key LIMIT 100'
"/absolute/path/to/installed/taskcontext/taskcontext" query 'SELECT id, name FROM user_directory ORDER BY name, id LIMIT 100'
"/absolute/path/to/installed/taskcontext/taskcontext" query 'SELECT id, key, title, status, revision FROM issues ORDER BY updated DESC, id LIMIT 50'
"/absolute/path/to/installed/taskcontext/taskcontext" create projects '{"key":"APP","name":"Application"}'
"/absolute/path/to/installed/taskcontext/taskcontext" create issues '{"project":"<project-id>","title":"Fix keyboard focus","type":"bug","priority":"high"}'
"/absolute/path/to/installed/taskcontext/taskcontext" update issues '<issue-id>' '{"status":"in_progress","expected_revision":1}'
"/absolute/path/to/installed/taskcontext/taskcontext" update issues '<issue-id>' '{"status":"done","resolution":"completed","expected_revision":2}'
"/absolute/path/to/installed/taskcontext/taskcontext" update issues '<issue-id>' '{"status":"ready","resolution":"","expected_revision":3}'
"/absolute/path/to/installed/taskcontext/taskcontext" update issues '<issue-id>' '{"due_date":"2030-01-15","expected_revision":4}'
"/absolute/path/to/installed/taskcontext/taskcontext" update issues '<issue-id>' '{"due_date":"","expected_revision":5}'
```

Open issues that are overdue or due within 7 days (change `+7 days` for another window):

```sql
SELECT key, title, assignee, date(due_date) AS due, status
FROM issues
WHERE status != 'done' AND due_date != ''
  AND date(due_date) <= date('now', '+7 days')
ORDER BY due_date, key LIMIT 100
```

Payment reminder in a dedicated `PAY` project (no bank details or credentials; every user can read it):

```sh
"/absolute/path/to/installed/taskcontext/taskcontext" create issues '{"project":"<pay-project-id>","title":"Pay invoice 2030-014 from Example Supplier","assignee":"<payer-user-id>","due_date":"2030-01-31","description":"Supplier: Example Supplier\nInvoice: 2030-014\nAmount: 120.00 EUR"}'
```

After a human confirms payment, add a comment such as `Paid; payment reference <reference>` and then set `status=done` with resolution `completed`.

Ready issues without unfinished blockers:

```sql
SELECT i.id, i.key, i.title, i.assignee, i.revision
FROM issues i
WHERE i.status = 'ready'
  AND NOT EXISTS (
    SELECT 1 FROM issue_links l JOIN issues b ON b.id = l.source
    WHERE l.target = i.id AND l.type = 'blocks' AND l.active = 1 AND b.status != 'done'
  )
ORDER BY i.created, i.id LIMIT 50
```

Issue evidence and audit history (replace the static ID):

```sql
SELECT kind, title, url FROM "references"
WHERE issue = '<issue-id>' ORDER BY created, id LIMIT 100
```

```sql
SELECT a.created, a.action, d.name, a.changes
FROM audit_log a LEFT JOIN user_directory d ON d.id = a.actor
WHERE a.collection = 'issues' AND a.record = '<issue-id>'
ORDER BY a.created, a.id LIMIT 100
```

Atomic issue and initial comment: generate an ID with `taskcontext newid`, then send an array to `taskcontext batch -` on stdin.

```json
[
  {"method":"POST","url":"/api/collections/issues/records","body":{"id":"<new-issue-id>","project":"<project-id>","title":"Improve error text"}},
  {"method":"POST","url":"/api/collections/comments/records","body":{"issue":"<new-issue-id>","body":"Acceptance: an expired session offers a clear sign-in action."}}
]
```
