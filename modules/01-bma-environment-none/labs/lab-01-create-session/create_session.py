"""Lab 01 — Create a BMA session and stream the agent's first reply.

This is the "hello world" of Bedrock Managed Agents (BMA, powered by
OpenAI). It does the smallest useful thing end to end:

  1. build the client (SigV4-signed, no OpenAI API key),
  2. create a session with NO execution environment
     (``environment={"type": "none"}``),
  3. submit the first prompt as that session's first turn, and
  4. stream the lifecycle events until the turn finishes, printing the
     agent's text output.

It never deletes the session — it prints the new session id so later labs
(interpret results, continue the session, list, delete) can reuse it.

Run it (from the module root, with the venv active):

    python labs/lab-01-create-session/create_session.py "What is the capital of France?"

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
#   modules/01-bma-environment-none/labs/lab-01-create-session/create_session.py
#   module root ----------------------^
# bma_common.py sits at that module root. Insert it on sys.path so
# `import bma_common` works no matter which directory you run the script
# from. os.path.dirname twice walks up from this file to the module root.
MODULE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, MODULE_ROOT)

import bma_common  # noqa: E402 — must come after the sys.path shim above
# The model, system instructions, failure-event set, and the event-draining
# loop are shared across the Module 1 labs and live in bma_common.py:
#   bma_common.DEFAULT_MODEL         — default inference model
#   bma_common.DEFAULT_INSTRUCTIONS  — the "concise assistant" instructions
#   bma_common.drain_turn(client, session_id)  — stream a turn to completion
# This lab just uses them so the create-session flow below stays the focus.


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a BMA session (environment=none) and stream its first reply."
    )
    parser.add_argument(
        "prompt",
        metavar="PROMPT",
        help="The first user prompt, submitted as the session's first turn.",
    )
    parser.add_argument(
        "--model",
        default=bma_common.DEFAULT_MODEL,
        help=f"Model id for the new session (default: {bma_common.DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--instructions",
        default=bma_common.DEFAULT_INSTRUCTIONS,
        help="System instructions for the new session.",
    )
    bma_common.add_connection_args(parser)
    bma_common.add_role_arn_arg(parser)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    # make_client wires the OpenAI SDK to the regional bedrock-mantle
    # endpoint and signs with your AWS credentials — no OpenAI API key.
    client = bma_common.make_client(args.region, args.aws_profile)

    # The IAM role BMA assumes to run inference. resolve_role_arn uses
    # --role-arn / $BMA_INFERENCE_ROLE_ARN if set, else builds the default
    # role name in your own account id (via STS get-caller-identity).
    role_arn = bma_common.resolve_role_arn(args.role_arn, args.aws_profile)

    # The agent config: which model to use and how it should behave.
    agent = {
        "model": args.model,
        "instructions": args.instructions,
    }
    print(f"Agent config: {json.dumps(agent, indent=2)}", file=sys.stderr)

    # Create the session AND start its first turn in one call.
    #   environment {"type": "none"}  -> no sandbox; the agent reasons and
    #                                    produces text but runs no code/tools.
    #   extra_body {"role_arn": ...}   -> the typed SDK does not expose
    #                                    role_arn yet, but the BMA preview API
    #                                    requires it as a top-level body field;
    #                                    extra_body merges it into the request.
    #   input [...]                    -> the first user message, as content
    #                                    parts of type "input_text".
    #   stream=False                   -> create() returns the session object;
    #                                    we stream the turn's events separately
    #                                    below via events.stream().
    sess = client.beta.agents.sessions.create(
        agent=agent,
        environment={"type": "none"},
        extra_body={"role_arn": role_arn},
        input=[
            {
                "role": "user",
                "content": [{"type": "input_text", "text": args.prompt}],
            }
        ],
        stream=False,
    )
    session_id = sess.id

    # The session id is the handle for everything else: continue it, list its
    # items, or delete it. Print it to stdout so it is easy to capture.
    print(f"Created session: {session_id}")
    print(f"--- prompt: {args.prompt!r}", file=sys.stderr)

    # Drain the first turn that create() already started.
    bma_common.drain_turn(client, session_id)

    print(
        f"\nSession kept open: {session_id}\n"
        "  * inspect its items:  python labs/lab-02-interpret-results/"
        f"interpret_results.py --session-id {session_id}\n"
        "  * delete it when done: python labs/lab-05-delete-session/"
        f"delete_session.py {session_id}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
