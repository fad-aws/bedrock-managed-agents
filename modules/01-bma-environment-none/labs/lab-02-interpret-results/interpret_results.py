"""Lab 02 — Interpret a session's results (list its items).

Streaming a turn (Lab 01) shows you the live output, but a session also
keeps a durable, ordered log of everything that happened: user messages,
assistant messages, reasoning, tool calls, command executions, and so on.
Each entry is an **item**. Reading the items is how you inspect a session
after the fact — and the best way to debug what an agent actually did.

This lab lists a session's items and renders them. It can either reuse a
session you pass with --session-id, or create a throwaway session, submit
one prompt, and then list — so you can run it with no prior setup.

Items are a **tagged union**: every item has a ``type`` and ``id``, but the
other fields depend on the type:

  * ``message``            — a user or assistant message; ``role`` plus a
                             list of ``content`` parts (each with its own
                             ``text`` / ``type``).
  * ``reasoning``          — the model's internal reasoning summary.
  * ``mcp_call``           — a remote MCP tool call; ``server_label``,
                             ``name``, ``arguments``, ``error``.
  * ``command_execution``  — a command the agent ran; ``command`` + ``output``
                             (only with an execution environment, not
                             environment=none).

Run it (from the module root, with the venv active):

    # list items of a session you already created in Lab 01
    python labs/lab-02-interpret-results/interpret_results.py --session-id sess_abc123

    # or let it create a throwaway session, ask once, then list
    python labs/lab-02-interpret-results/interpret_results.py

    # raw JSON instead of the table
    python labs/lab-02-interpret-results/interpret_results.py --session-id sess_abc123 --json

Docs:
  https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-managed-agents-openai-api-reference.html
"""

import argparse
import json
import os
import sys

# Import the shared helpers from the module root (two dirs up from here).
MODULE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, MODULE_ROOT)

import bma_common  # noqa: E402
from openai import OpenAI  # noqa: E402
# The model, system instructions, failure-event set, and the turn-draining
# loop are shared across the Module 1 labs (see bma_common.py). This lab only
# adds a prompt for the throwaway session it can create.
DEFAULT_PROMPT = "In one sentence, what is Amazon Bedrock?"


def _create_demo_session(client: OpenAI, args: argparse.Namespace) -> str:
    """Create a throwaway session, ask one prompt, and return its id."""
    role_arn = bma_common.resolve_role_arn(args.role_arn, args.aws_profile)
    sess = client.beta.agents.sessions.create(
        agent={"model": args.model, "instructions": bma_common.DEFAULT_INSTRUCTIONS},
        environment={"type": "none"},
        extra_body={"role_arn": role_arn},
        input=[
            {
                "role": "user",
                "content": [{"type": "input_text", "text": DEFAULT_PROMPT}],
            }
        ],
        stream=False,
    )
    print(f"Created session: {sess.id}", file=sys.stderr)
    print(f"--- prompt: {DEFAULT_PROMPT!r}", file=sys.stderr)
    # This lab inspects the durable items afterward, so it drains the turn
    # without echoing the streamed text (print_output=False).
    bma_common.drain_turn(client, sess.id, print_output=False)
    return sess.id


def _preview(item) -> str:
    """A short, human-readable one-line preview for the table view.

    Different item types carry different fields, so pull out whatever is
    most useful for a glance and fall back to empty for types we do not
    special-case.
    """
    text = ""
    if item.type == "message":
        parts = []
        for part in item.content or []:
            part_text = getattr(part, "text", None)
            if part_text:
                parts.append(part_text)
            elif getattr(part, "type", None):
                parts.append(f"<{part.type}>")
        text = " ".join(parts)
    elif item.type == "command_execution":
        text = f"$ {item.command}"
        if item.output:
            text += f"  -> {item.output}"
    elif item.type == "mcp_call":
        text = f"{item.server_label}.{item.name}({item.arguments or ''})"
    else:
        text = ""

    text = " ".join(text.split())  # collapse whitespace/newlines for one line
    max_len = 80
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List and interpret the items (results) of a BMA session."
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help=(
            "Session to inspect (e.g. sess_abc123). If omitted, a throwaway "
            "session is created, asked one prompt, then listed."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max items to list, 1-100 (default: 20).",
    )
    parser.add_argument(
        "--order",
        choices=("asc", "desc"),
        default="asc",
        help="Sort order (default: asc, chronological — reads top to bottom).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON instead of a formatted table.",
    )
    parser.add_argument(
        "--model",
        default=bma_common.DEFAULT_MODEL,
        help=f"Model id, used only if a throwaway session is created (default: {bma_common.DEFAULT_MODEL}).",
    )
    bma_common.add_connection_args(parser)
    bma_common.add_role_arn_arg(parser)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    client = bma_common.make_client(args.region, args.aws_profile)

    session_id = args.session_id or _create_demo_session(client, args)

    # List the items. Read page.data (just the requested page) rather than
    # iterating the pager: the SDK's auto-pager builds its own `after`
    # cursor, which this preview endpoint rejects as "malformed base64".
    # --limit already bounds how many items a single request returns.
    page = client.beta.agents.sessions.items.list(
        session_id, limit=args.limit, order=args.order
    )
    items = page.data
    if page.has_more:
        print(
            f"Note: more items exist beyond this page of {len(items)}. "
            "Increase --limit (max 100) to see more.",
            file=sys.stderr,
        )

    if args.json:
        # model_dump(mode="json") avoids noisy pydantic serializer warnings
        # about this preview API's union-typed fields.
        print(json.dumps([i.model_dump(mode="json") for i in items], indent=2))
        return 0

    if not items:
        print("No items found.", file=sys.stderr)
        return 0

    def type_label(item) -> str:
        # message:user / message:assistant are clearer than bare "message".
        role = getattr(item, "role", None)
        return f"{item.type}:{role}" if role else item.type

    id_w = max(len("ITEM_ID"), *(len(i.id) for i in items))
    type_w = max(len("TYPE"), *(len(type_label(i)) for i in items))
    status_w = max(len("STATUS"), *(len(getattr(i, "status", "") or "") for i in items))

    header = f"{'ITEM_ID':<{id_w}}  {'TYPE':<{type_w}}  {'STATUS':<{status_w}}  PREVIEW"
    print(header)
    print("-" * len(header))
    for item in items:
        status = getattr(item, "status", "") or ""
        print(
            f"{item.id:<{id_w}}  {type_label(item):<{type_w}}  {status:<{status_w}}  "
            f"{_preview(item)}"
        )

    print(f"\n{len(items)} item(s). Use --json for full details.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
