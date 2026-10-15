"""Lab 03 — Durable, server-side session state (a shared to-do list).

A BMA session keeps its full conversation history on the server, not in
your client process. This lab makes that concrete with a **shared to-do
list**: several people, each from their own terminal, send items to the
SAME session, and every reply shows the full list accumulated so far.

Because the list lives in the session's server-side history — not in any
one client — it does not matter who adds the next item or from which
machine. Alice can add "buy milk" from her laptop, Bob can add "book
flights" from his, and the next reply (to either of them) shows both. That
is session persistence, and the fact that any terminal holding the session
id sees the same list is session sharing across users.

Two modes:

  * No --session-id: create a NEW shared list (prints the session id to
    share with your teammates), and add the first item.
  * With --session-id: join an EXISTING shared list and add another item,
    from this fresh process / terminal / person.

Use --user to attribute an item to a person (optional but makes the shared
nature obvious in the output).

Run it (from the module root, with the venv active):

    # person A — start the shared list (prints the id)
    python labs/lab-03-session-state/session_state.py \\
        --user Alice "buy milk"

    # person B — join the SAME list from another terminal and add to it
    python labs/lab-03-session-state/session_state.py \\
        --session-id sess_abc123 --user Bob "book flights"

Docs:
  https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-managed-agents-openai-sessions.html
"""

import argparse
import os
import sys

MODULE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, MODULE_ROOT)

import bma_common  # noqa: E402
# The default model, failure-event set, and the turn-draining loop are shared
# across the Module 1 labs (see bma_common.py). What is unique to THIS lab is
# the shared-to-do-list instructions below — the whole point of the demo.

# Instructions that turn the agent into a keeper of a shared to-do list.
# Every user message is an instruction to add (or complete) items, and the
# agent replies with the WHOLE current list — rebuilt each turn from the
# session's server-side history. Because the agent reconstructs the list
# from that shared history (not from anything the client stores), a correct,
# growing list across turns submitted by different terminals/people is
# direct evidence the session state is persisted and shared server-side.
TODO_INSTRUCTIONS = (
    "You maintain a single shared to-do list for this session. Treat every "
    "user message as a request to update the list: add the item(s) it "
    "describes, and if a message says an item is done, mark it done. Items "
    "may arrive from different people; if a message is prefixed with a name "
    "like 'Alice:', record who added that item. "
    "On every reply, output the ENTIRE current list, numbered, one item per "
    "line, in the order items were added, each line showing the item text, "
    "who added it (if known), and whether it is done. Rebuild the full list "
    "by reviewing the whole conversation history, not just the latest "
    "message. Never drop or reorder items that were added earlier, and never "
    "invent items nobody asked for. Keep any preamble to one short sentence."
)


def _message_event(text: str) -> dict:
    """Build an input-message event to submit a follow-up turn."""
    return {
        "type": "agent.session.input.message",
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            }
        ],
    }


def _compose_item(user: str | None, item: str) -> str:
    """Prefix the item with the person's name, if one was given.

    'Alice' + 'buy milk' -> 'Alice: buy milk'. The name prefix is just text
    in the user message; the agent's instructions tell it to read a leading
    'Name:' as who added the item. There is no separate per-user identity in
    BMA — a session is shared by whoever holds its id.
    """
    return f"{user}: {item}" if user else item


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Add an item to a shared BMA to-do list, demonstrating durable, "
            "server-side session state. Creates a new shared list unless "
            "--session-id is given, in which case it joins that list."
        )
    )
    parser.add_argument(
        "item",
        metavar="ITEM",
        help="The to-do item to add this turn (e.g. \"buy milk\").",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help=(
            "Existing shared list to join (e.g. sess_abc123). Share this id "
            "with teammates so they can add to the same list. If omitted, a "
            "new shared list is created."
        ),
    )
    parser.add_argument(
        "--user",
        default=None,
        help=(
            "Optional name to attribute this item to (e.g. --user Alice). "
            "Sent as an 'Alice: <item>' prefix so the list shows who added "
            "what. There is no real per-user identity — a session is shared "
            "by whoever has its id."
        ),
    )
    parser.add_argument(
        "--model",
        default=bma_common.DEFAULT_MODEL,
        help=f"Model id, used only when creating a new session (default: {bma_common.DEFAULT_MODEL}).",
    )
    bma_common.add_connection_args(parser)
    bma_common.add_role_arn_arg(parser)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    client = bma_common.make_client(args.region, args.aws_profile)

    message = _compose_item(args.user, args.item)

    if args.session_id:
        # Join an existing shared list. This process shares no local state
        # with whoever created the session or added earlier items — the only
        # link is the session id. The new item goes in via the events
        # endpoint; the agent rebuilds the list from the server-side history,
        # so the reply shows every item added so far, by anyone.
        session_id = args.session_id
        print(f"Joining shared list: {session_id}", file=sys.stderr)
        print(f"--- adding: {message!r}", file=sys.stderr)
        client.beta.agents.sessions.events.create(
            session_id, events=[_message_event(message)]
        )
        bma_common.drain_turn(client, session_id)
    else:
        # Create a new shared list and add the first item.
        role_arn = bma_common.resolve_role_arn(args.role_arn, args.aws_profile)
        sess = client.beta.agents.sessions.create(
            agent={"model": args.model, "instructions": TODO_INSTRUCTIONS},
            environment={"type": "none"},
            extra_body={"role_arn": role_arn},
            input=[
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": message}],
                }
            ],
            stream=False,
        )
        session_id = sess.id
        print(f"Created shared list: {session_id}", file=sys.stderr)
        print(f"--- adding: {message!r}", file=sys.stderr)
        bma_common.drain_turn(client, session_id)
        # Reproduce the connection flags so the follow-up command hits the SAME
        # Region/profile — sessions are region-scoped (a mismatch gives a 404).
        conn = bma_common.connection_flags(args)
        print(
            "\nShare this session id with others so they can add to the SAME "
            "list from their own terminal:\n"
            "  python labs/lab-03-session-state/session_state.py"
            f"{conn} --session-id {session_id} --user Bob \"book flights\"\n"
            "Every reply shows the full list rebuilt from the shared, "
            "server-side session history.",
            file=sys.stderr,
        )

    print(f"\nSession kept open: {session_id}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
