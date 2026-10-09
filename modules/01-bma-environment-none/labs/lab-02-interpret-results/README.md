# Lab 02 — Interpret results

**What you learn:** how to list a session's items and read the
tagged-union result shape (messages, reasoning, tool calls).

## Concept

Streaming a turn (Lab 01) shows the live reply, but a session also keeps a
durable, ordered log of everything that happened. Each entry is an
**item**, and listing items is how you inspect a session after the fact —
and the best way to debug what an agent actually did.

Items are a **tagged union**: every item has a `type` and an `id`, but the
rest of its fields depend on the type.

| `type` | Key fields | Meaning |
|---|---|---|
| `message` (role `user`) | `role`, `content[]` | A prompt you submitted. |
| `message` (role `assistant`) | `role`, `content[]` | The agent's reply. Each `content` part has its own `text` / `type`. |
| `reasoning` | summary content | The model's internal reasoning for the turn. |
| `mcp_call` | `server_label`, `name`, `arguments`, `error` | A remote MCP tool call (see Lab 06). `error` is `null` on success. |
| `command_execution` | `command`, `output` | A command the agent ran — only appears with an execution environment, so **not** in `environment=none`. |

Because the fields vary, read each item by its `type`. For raw inspection,
use `model_dump(mode="json")` (the `--json` mode here) — it avoids noisy
pydantic warnings on this preview API's union-typed fields.

## What you'll run

`interpret_results.py` either reuses a `--session-id` you pass or creates a
throwaway session, asks one prompt, and then lists. It reads **one page**
(`page.data`) with `items.list(session_id, limit=, order=)` and renders a
table, or raw JSON with `--json`.

> **Why one page?** The SDK's auto-pager builds its own `after` cursor,
> which this preview endpoint rejects as `malformed base64`. `--limit`
> (max 100) bounds a single request, which is all these labs need.

## The command

Before your first run, complete the one-time
[prerequisites](../../00-prerequisites.md) (create the venv and configure your
AWS profile). Then, in each new terminal, from the module root
(`modules/01-bma-environment-none`), activate the venv and make sure your AWS
profile is set (`export AWS_PROFILE=<your-aws-profile>` or pass `--aws-profile`):

```bash
source .venv/bin/activate

# inspect the session you created in Lab 01
python labs/lab-02-interpret-results/interpret_results.py --session-id sess_abc123

# or let it create a throwaway session, ask once, then list
python labs/lab-02-interpret-results/interpret_results.py

# raw JSON (full field detail per item)
python labs/lab-02-interpret-results/interpret_results.py --session-id sess_abc123 --json
```

## Expected output

Table mode renders one row per item, oldest first:

```text
ITEM_ID       TYPE               STATUS     PREVIEW
----------------------------------------------------------------
item_000001   message:user                  What is the capital of France?
item_000002   reasoning          completed   Identifying the capital city of France.
item_000003   message:assistant  completed   The capital of France is Paris.

3 item(s). Use --json for full details.
```

`--json` prints the full items array instead:

```json
[
  {
    "id": "item_000003",
    "type": "message",
    "role": "assistant",
    "status": "completed",
    "content": [
      { "type": "output_text", "text": "The capital of France is Paris." }
    ]
  }
]
```

## What to notice

- The `TYPE` column shows `message:user` vs `message:assistant` by joining
  `type` and `role` — bare `message` would hide who said what.
- With `environment=none` you will see `message` and `reasoning` items, but
  **no** `command_execution` items — there is no sandbox to run commands.
- `--order asc` reads the conversation top to bottom; `--json` is the
  go-to for debugging tool calls (inspect each `mcp_call` item's `error`).

## Cleanup

If you created a throwaway session here, delete it with
[Lab 05](../lab-05-delete-session/README.md).

## Next

Continue to [Lab 03 — Session state](../lab-03-session-state/README.md) to
see server-side history stay consistent across separate processes.
