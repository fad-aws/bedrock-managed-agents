# Lab 05 — Delete session

**What you learn:** how to delete sessions and why cleanup is on you —
sessions are never auto-deleted.

## Concept

Every session you create in the earlier labs stays around until you remove
it. BMA does **not** auto-delete idle sessions, so cleaning up is an
explicit step. Deleting is a single call:

```python
client.beta.agents.sessions.delete(session_id)
```

One thing worth knowing:

- **Deleting a session removes the session and its conversation history.**
  It does **not** delete any customer-owned files or resources the agent
  touched — those live in your account and are yours to manage separately.

## What you'll run

`delete_session.py` takes one or more session ids and deletes each. It
reports success or failure **per id** and keeps going if one fails (already
gone, wrong id, missing permissions), so a single bad id does not stop the
rest. The process exits non-zero if any delete failed.

## The command

Before your first run, complete the one-time
[prerequisites](../../00-prerequisites.md) (create the venv and configure your
AWS profile). Then, in each new terminal, from the module root
(`modules/01-bma-environment-none`), activate the venv and make sure your AWS
profile is set (`export AWS_PROFILE=<your-aws-profile>` or pass `--aws-profile`):

```bash
# delete one session
python labs/lab-05-delete-session/delete_session.py sess_abc123

# delete several at once
python labs/lab-05-delete-session/delete_session.py sess_abc123 sess_def456

# target a specific profile/region (match how the session was created)
python labs/lab-05-delete-session/delete_session.py --aws-profile <your-aws-profile> --region us-west-2 sess_abc123
```

> **Delete in the same Region the session was created in.** Sessions are
> region-scoped, so you must pass the same `--region` (and profile) used to
> create them. Deleting with the wrong Region returns a `404 no managed agent
> session found` even though the session exists elsewhere.

Use [Lab 04](../lab-04-list-sessions/README.md) first to find the ids you
want to remove.

## Expected output

```text
Deleted session: sess_abc123
Deleted session: sess_def456
```

If one id cannot be deleted, the others still succeed and the run reports
the failure to stderr, exiting non-zero:

```text
Deleted session: sess_abc123
Failed to delete session sess_def456: <error detail>
```

## What to notice

- **Cleanup is manual.** Nothing deletes sessions for you; make it a habit
  to delete the ones you create while learning.
- **Per-id, best-effort.** One failing id does not block the others, and the
  non-zero exit lets scripts detect that something failed.
- Deleting a session is irreversible — its history is gone — but it leaves
  your own files and resources untouched.

## Cleanup

This lab *is* the cleanup step. After running it, confirm with
[Lab 04](../lab-04-list-sessions/README.md) that the sessions are gone.

## Next

You have finished the core labs. Continue to the next lab,
[Lab 06 — AgentCore Gateway](../lab-06-agentcore-gateway/README.md), to give
the agent remote MCP tools at session creation.
