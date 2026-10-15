# Lab 04 — List sessions

**What you learn:** how to list the sessions in your account/Region and
read their status, model, and last-active metadata.

## Concept

Sessions stick around until you delete them, so you need a way to see what
exists — to find the one you want to continue, or to spot the ones you
should clean up. `sessions.list(...)` returns a page of sessions, each with:

| Column | Field | Meaning |
|---|---|---|
| `SESSION_ID` | `id` | The handle used by every other call (`sess_abc123`). |
| `STATUS` | `status` | Lifecycle state (e.g. active). |
| `MODEL` | `agent.model` | The model the session was created with. |
| `LAST_ACTIVE_AT` | `last_active_at` | When a turn last ran on it. |

## What you'll run

`list_sessions.py` calls `sessions.list(limit=, order=)` and reads **one
page** (`page.data`), rendering a table or `--json`. `--order desc` (default)
shows newest first; `--limit` (1–100) bounds a single request.


## The command

Before your first run, complete the one-time
[prerequisites](../../00-prerequisites.md) (create the venv and configure your
AWS profile). Then, in each new terminal, from the module root
(`modules/01-bma-environment-none`), activate the venv and make sure your AWS
profile is set (`export AWS_PROFILE=<your-aws-profile>` or pass `--aws-profile`):

```bash
# most recent 20 sessions
python labs/lab-04-list-sessions/list_sessions.py

# oldest first, up to 50 in one page
python labs/lab-04-list-sessions/list_sessions.py --limit 50 --order asc

# raw JSON (full session resource per entry)
python labs/lab-04-list-sessions/list_sessions.py --json
```

## Expected output

```text
SESSION_ID    STATUS   MODEL              LAST_ACTIVE_AT
----------------------------------------------------------------------
sess_abc123   active   openai.gpt-5.6-luna  2026-10-07T18:42:11Z

1 session(s). Use --json for full details.
```

If more sessions exist than `--limit`, you also get:

```text
Note: more sessions exist beyond this page of 20. Increase --limit (max 100) to see more.
```

## What to notice

- `--limit` controls a **single request**, not total results. Raise it to
  see more; the lab does not page automatically (see the cursor note above).
- `--json` gives the full session resource, including the `environment`
  block and `agent` config — handy for confirming what a session was
  created with.
- The id in the `SESSION_ID` column is exactly what you pass to Lab 02
  (`--session-id`), Lab 03 (`--session-id`), and Lab 05 (delete).

## Cleanup

Spotted sessions you no longer need? Delete them in the next lab.

## Next

Continue to [Lab 05 — Delete session](../lab-05-delete-session/README.md)
to clean up when you are done.
