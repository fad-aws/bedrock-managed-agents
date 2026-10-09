"""Lab 04 — List the sessions in an account/Region.

Sessions you create stay around until you delete them (Lab 05), so you need
a way to see what exists. This lab lists BMA sessions and shows their id,
status, model, and last-active time — enough to find the one you want to
continue or clean up.

Run it (from the module root, with the venv active):

    python labs/lab-04-list-sessions/list_sessions.py
    python labs/lab-04-list-sessions/list_sessions.py --limit 50 --order asc
    python labs/lab-04-list-sessions/list_sessions.py --json

Docs:
  https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-managed-agents-openai-api-reference.html
"""

import argparse
import json
import os
import sys

MODULE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, MODULE_ROOT)

import bma_common  # noqa: E402
def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List BMA sessions in the account/Region.")
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max sessions to list, 1-100 (default: 20).",
    )
    parser.add_argument(
        "--order",
        choices=("asc", "desc"),
        default="desc",
        help="Sort order by creation time (default: desc, newest first).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON instead of a formatted table.",
    )
    bma_common.add_connection_args(parser)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    client = bma_common.make_client(args.region, args.aws_profile)

    page = client.beta.agents.sessions.list(limit=args.limit, order=args.order)
    # Read page.data (just the requested page) rather than iterating the
    # pager. The SDK's auto-pager builds its own `after` cursor from the last
    # item's id, and against this preview endpoint that self-built cursor
    # comes back as "malformed base64" — the API's `after` cursor is an
    # opaque value, not safe to reconstruct. --limit (max 100) already bounds
    # a single request, which is all this lab needs; it does not auto-page.
    sessions = page.data
    if page.has_more:
        print(
            f"Note: more sessions exist beyond this page of {len(sessions)}. "
            "Increase --limit (max 100) to see more.",
            file=sys.stderr,
        )

    if args.json:
        # model_dump(mode="json") avoids noisy pydantic serializer warnings
        # about this preview API's union-typed fields (e.g. environment,
        # which varies by environment type).
        print(json.dumps([s.model_dump(mode="json") for s in sessions], indent=2))
        return 0

    if not sessions:
        print("No sessions found.", file=sys.stderr)
        return 0

    id_w = max(len("SESSION_ID"), *(len(s.id) for s in sessions))
    model_w = max(
        len("MODEL"),
        *(len(getattr(s.agent, "model", "") or "") for s in sessions),
    )
    status_w = max(len("STATUS"), *(len(s.status or "") for s in sessions))

    header = f"{'SESSION_ID':<{id_w}}  {'STATUS':<{status_w}}  {'MODEL':<{model_w}}  LAST_ACTIVE_AT"
    print(header)
    print("-" * len(header))
    for s in sessions:
        model = getattr(s.agent, "model", "") or ""
        print(
            f"{s.id:<{id_w}}  {s.status or '':<{status_w}}  {model:<{model_w}}  "
            f"{s.last_active_at}"
        )

    print(f"\n{len(sessions)} session(s). Use --json for full details.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
