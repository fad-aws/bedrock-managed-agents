"""Lab 06 — Gate the shared to-do list with an AgentCore Gateway tool (stretch).

This is the advanced lab, and it builds directly on Lab 03's shared to-do
list. The twist: before the agent adds an item, it must ask an **AgentCore
Gateway** tool for permission. The tool, ``GetRandomBool``, returns ``true``
or ``false`` at random; the agent adds the item only when the tool returns
``true``, and refuses (leaving the list unchanged) when it returns
``false``. That gives the remote tool call a real job in the workflow —
it decides whether the turn mutates the shared, server-side list.

Everything from Lab 03 still holds: the list lives in the session's
server-side history, and anyone holding the session id can add to it from
their own terminal. The only new thing is the Gateway tool and the gate.

The Gateway tool is wired in through the agent's ``tools`` list::

    agent["tools"] = [
        {
            "type": "mcp",
            "server_label": "gateway_tools",
            "connector_id": args.gateway_arn,   # the Gateway's ARN
        }
    ]

The Gateway is referenced by its ARN via ``connector_id`` — NOT by a URL
with a ``transport`` block (that http-transport shape fails BMA's schema
validation with a generic oneOf error). BMA resolves the connector and
calls the Gateway with IAM from the service side using the session's
``role_arn``, so no URL, bearer token, or vault credential is needed — the
session role just needs ``bedrock-agentcore:InvokeGateway`` on the Gateway.

The Gateway itself is NOT created here. You must already have one that
exposes a ``GetRandomBool`` MCP tool (returns a random boolean). See the
lab README for a copy-paste Lambda + Gateway setup.

Tools are fixed at session creation, so the Gateway can only be attached
when the shared list is first created (no --session-id). Teammates who join
with --session-id inherit the same tool automatically.

Run it (from the module root, with the venv active):

    # person A — create the gated shared list (prints the id)
    python labs/lab-06-agentcore-gateway/gateway_session.py \\
        --gateway-arn arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/my-gateway-id \\
        --user Alice "buy milk"

    # person B — join the SAME list from another terminal (no --gateway-arn)
    python labs/lab-06-agentcore-gateway/gateway_session.py \\
        --session-id sess_abc123 --user Bob "book flights"

Docs:
  https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-managed-agents-openai.html
  https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-managed-agents-openai-sessions.html
"""

import argparse
import json
import os
import sys

# --- Import the shared module helpers ------------------------------------
# Each lab lives two directories below the module root:
#   modules/01-bma-environment-none/labs/lab-06-agentcore-gateway/gateway_session.py
#   module root ----------------------^
# bma_common.py sits at that module root. Insert it on sys.path so
# `import bma_common` works no matter which directory you run the script
# from. os.path.dirname three times walks up from this file to the module
# root.
MODULE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, MODULE_ROOT)

import bma_common  # noqa: E402 — must come after the sys.path shim above
# The default model, failure-event set, and the turn-draining loop
# (bma_common.drain_turn) are shared across the Module 1 labs; see
# bma_common.py. What is unique to THIS lab is the Gateway tool wiring in
# main() and the gate-aware instructions below.
#
# A note on Gateway failures and draining: a tool call that fails at the
# Gateway does NOT necessarily fail the turn — the agent may still answer
# (often by saying the tool failed), so drain_turn completes normally. The
# real error lives on the ``mcp_call`` item, which you read with Lab 02's
# ``interpret_results.py --json`` (look at ``server_label``, ``name``, and
# ``error``). See the lab README.

# Instructions: Lab 03's shared-to-do-list behavior, PLUS a gate. Before
# adding any item the agent must call the Gateway's GetRandomBool tool and
# only add the item if the tool returns true; on false it declines and
# leaves the list unchanged. This makes the remote tool call decide whether
# the turn mutates the shared, server-side list.
TODO_GATE_INSTRUCTIONS = (
    "You maintain a single shared to-do list for this session. The items may "
    "come from different people; a message prefixed with a name like "
    "'Alice:' means Alice is adding that item. "
    "IMPORTANT: before adding ANY item, you MUST call the 'GetRandomBool' "
    "tool exactly once for that item. It takes no arguments and returns a "
    "boolean 'result'. If result is true, add the item. If result is false, "
    "do NOT add the item — say it was rejected by the gate this time and "
    "leave the list unchanged. Never add an item without calling the tool "
    "first, and never guess the tool's answer. "
    "On every reply, state the tool's result for this item (added or "
    "rejected), then output the ENTIRE current list, numbered, one item per "
    "line, in the order items were added, each line showing the item text "
    "and who added it (if known). Rebuild the full list from the whole "
    "conversation history, never dropping or reordering earlier items. Keep "
    "any preamble to one short sentence."
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

    Same convention as Lab 03: 'Alice' + 'buy milk' -> 'Alice: buy milk'.
    """
    return f"{user}: {item}" if user else item


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Add an item to a shared BMA to-do list, but gate each add on an "
            "AgentCore Gateway tool (GetRandomBool). Creates a new gated list "
            "unless --session-id is given, in which case it joins that list."
        )
    )
    parser.add_argument(
        "item",
        metavar="ITEM",
        help="The to-do item to try to add this turn (e.g. \"buy milk\").",
    )
    parser.add_argument(
        "--gateway-arn",
        default=None,
        help=(
            "ARN of an already-provisioned AgentCore Gateway that exposes a "
            "'GetRandomBool' MCP tool, e.g. "
            "'arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/"
            "my-gateway-id'. Passed as the tool's connector_id. REQUIRED when "
            "creating a new list (no --session-id); ignored when joining an "
            "existing one, since tools are fixed at session creation."
        ),
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help=(
            "Existing gated list to join (e.g. sess_abc123). Share this id "
            "with teammates. If omitted, a new gated list is created and "
            "--gateway-arn is required."
        ),
    )
    parser.add_argument(
        "--user",
        default=None,
        help=(
            "Optional name to attribute this item to (e.g. --user Alice), "
            "sent as an 'Alice: <item>' prefix. There is no real per-user "
            "identity — a session is shared by whoever has its id."
        ),
    )
    parser.add_argument(
        "--model",
        default=bma_common.DEFAULT_MODEL,
        help=f"Model id, used only when creating a new session (default: {bma_common.DEFAULT_MODEL}).",
    )
    bma_common.add_connection_args(parser)
    bma_common.add_role_arn_arg(parser)
    args = parser.parse_args(argv)
    # A new list needs the Gateway (the tool is fixed at creation). Joining an
    # existing list reuses whatever tool it was created with, so the ARN is
    # neither needed nor usable there.
    if not args.session_id and not args.gateway_arn:
        parser.error("--gateway-arn is required when creating a new list (no --session-id).")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)

    # make_client wires the OpenAI SDK to the regional bedrock-mantle
    # endpoint and signs with your AWS credentials — no OpenAI API key.
    client = bma_common.make_client(args.region, args.aws_profile)

    message = _compose_item(args.user, args.item)

    if args.session_id:
        # Join an existing gated list. The Gateway tool was fixed when the
        # list was created, so this process inherits it automatically — it
        # only submits the new item via the events endpoint and drains.
        session_id = args.session_id
        print(f"Joining shared list: {session_id}", file=sys.stderr)
        print(f"--- trying to add: {message!r}", file=sys.stderr)
        client.beta.agents.sessions.events.create(
            session_id, events=[_message_event(message)]
        )
        bma_common.drain_turn(client, session_id)
    else:
        # Create a new gated shared list. The IAM role BMA assumes runs
        # inference AND calls the Gateway, so for this lab it additionally
        # needs bedrock-agentcore:InvokeGateway on the Gateway ARN (see the
        # lab README's requirements).
        role_arn = bma_common.resolve_role_arn(args.role_arn, args.aws_profile)

        # The agent config: model, the gate-aware to-do instructions, and —
        # the point of this lab — the Gateway tool. The Gateway is referenced
        # by its ARN as the tool's `connector_id`, NOT by a URL with a
        # `transport` block (that shape fails BMA's schema validation). BMA
        # resolves the connector and calls the Gateway from the service side
        # via role_arn, so no URL, token, or vault credential is passed here.
        #
        # Note: the installed openai SDK types `connector_id` as a closed
        # enum of OpenAI's own named connectors, which does not include a
        # Gateway ARN — but `tools` here is a plain dict the SDK forwards
        # without enforcing that enum, and BMA accepts the ARN.
        agent: dict = {
            "model": args.model,
            "instructions": TODO_GATE_INSTRUCTIONS,
            "tools": [
                {
                    "type": "mcp",
                    "server_label": "gateway_tools",
                    "connector_id": args.gateway_arn,
                }
            ],
        }
        print(f"Agent config: {json.dumps(agent, indent=2)}", file=sys.stderr)
        sess = client.beta.agents.sessions.create(
            agent=agent,
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
        print(f"Created gated shared list: {session_id}", file=sys.stderr)
        print(f"--- trying to add: {message!r}", file=sys.stderr)
        bma_common.drain_turn(client, session_id)
        print(
            "\nShare this session id so others can add to the SAME gated list "
            "from their own terminal (no --gateway-arn needed — the tool is "
            "already attached):\n"
            "  python labs/lab-06-agentcore-gateway/gateway_session.py "
            f"--session-id {session_id} --user Bob \"book flights\"",
            file=sys.stderr,
        )

    print(
        f"\nSession kept open: {session_id}\n"
        "  * inspect its items (and the GetRandomBool mcp_call result/errors): "
        "python labs/lab-02-interpret-results/interpret_results.py --json "
        f"--session-id {session_id}\n"
        "  * delete it when done: python labs/lab-05-delete-session/"
        f"delete_session.py {session_id}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
