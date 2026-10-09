# Lab 03 — Session state (a shared to-do list)

**What you learn:** that a session's state (its full conversation history)
is durable and server-side — so multiple people, each from their own
terminal, can add to the same list and everyone sees the same result.

## Concept

Where does a session's memory live? Not in your client process — on the
server. BMA keeps the full conversation history for each session, so a
follow-up turn always sees everything that came before, even when it is
submitted by a brand-new process on a different machine by a different
person.

This lab makes that concrete with a **shared to-do list**. The agent is
told to keep one running list for the session: every message adds (or
completes) items, and every reply shows the whole list so far. Alice adds
"buy milk" from her terminal; Bob joins the same session id from his and
adds "book flights"; the next reply shows both. Nothing is stored on
Alice's or Bob's machine — the list is rebuilt each turn from the session's
server-side history, which is exactly why any terminal holding the session
id sees the same list.


A follow-up turn is submitted through the **events** endpoint:

```python
client.beta.agents.sessions.events.create(
    session_id,
    events=[{
        "type": "agent.session.input.message",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": text}]}],
    }],
)
```

…then you drain the turn's events exactly like Lab 01.

## What you'll run

`session_state.py` runs in two modes:

- **no `--session-id`** — creates a new shared list, adds the first item,
  and prints the session id to share with teammates.
- **with `--session-id`** — joins that existing list and adds another item,
  from this fresh process / terminal / person.

Use `--user <name>` to attribute an item to a person (optional).

## The command

Before your first run, complete the one-time
[prerequisites](../../00-prerequisites.md) (create the venv and configure your
AWS profile). Then, in each new terminal, from the module root
(`modules/01-bma-environment-none`), activate the venv and make sure your AWS
profile is set (`export AWS_PROFILE=<your-aws-profile>` or pass `--aws-profile`):

```bash
source .venv/bin/activate

# person A — start the shared list (prints the id)
python labs/lab-03-session-state/session_state.py --user Alice "buy milk"

# person B — join the SAME list from another terminal
python labs/lab-03-session-state/session_state.py \
    --session-id sess_abc123 --user Bob "book flights"

# person A again — add another item, or mark one done
python labs/lab-03-session-state/session_state.py \
    --session-id sess_abc123 --user Alice "milk is done"
```

Each run is a fresh process with no shared local state, so reusing the same
`--session-id` across runs in one terminal already demonstrates the point —
separate terminals (or people) just make it extra convincing.

## Expected output

```text
# person A starts the list (create)
Created shared list: sess_abc123
--- adding: 'Alice: buy milk'
{"type": "agent.session.turn.output_text.done", "text": "Added. Current list:\n1. buy milk (Alice) — not done"}

# person B joins from another terminal and adds an item
Joining shared list: sess_abc123
--- adding: 'Bob: book flights'
{"type": "agent.session.turn.output_text.done", "text": "Added. Current list:\n1. buy milk (Alice) — not done\n2. book flights (Bob) — not done"}

# person A marks the first item done — the list still carries Bob's item
Joining shared list: sess_abc123
--- adding: 'Alice: milk is done'
{"type": "agent.session.turn.output_text.done", "text": "Updated. Current list:\n1. buy milk (Alice) — done\n2. book flights (Bob) — not done"}
```

(The exact wording varies with the model; the structure — a growing list
that remembers every earlier item and who added it — is the point.)

## What to notice

- **The list persists across processes and people.** Bob's turn runs in a
  new process that shares nothing with Alice's except the session id — yet
  his reply includes Alice's earlier item, and hers later includes his.
- **The list lives server-side.** No client writes anything to disk; the
  agent rebuilds the whole list each turn from the session history BMA
  keeps. Delete the session (Lab 05) and the list is gone.
- Instructions are fixed at session creation, so `--model` only applies
  when creating a new list.

## Cleanup

Delete the session when you are done with
[Lab 05](../lab-05-delete-session/README.md):

```bash
python labs/lab-05-delete-session/delete_session.py sess_abc123
```

## Next

Continue to [Lab 04 — List sessions](../lab-04-list-sessions/README.md) to
find your sessions and read their metadata.
