#!/usr/bin/env python3
"""create_session_role.py — create the IAM session role that BMA (Bedrock
Managed Agents, powered by OpenAI) assumes to perform model inference.

BMA assumes this role (its trust policy trusts bedrock-mantle.amazonaws.com)
to call inference on your behalf. The role carries an inline policy allowing
bedrock-mantle:CreateInference for a specific model. This script creates that
role and its inline inference policy.

It also PRINTS (but does NOT create or attach) two policies you need on your
own calling identity — the identity that invokes the BMA session APIs:
  * an iam:PassRole policy so you may pass this role to BMA, and
  * a BMA-client policy granting the session actions.
Review those and attach them to your user/role yourself.

This replaces the old Bash role-creation helper and runs natively on macOS,
Linux and Windows. It uses boto3 instead of the AWS CLI, so run it with the module
venv active (i.e. after `python setup.py`); it does NOT require the aws CLI.

============================================================================
LEAST PRIVILEGE — READ THIS
----------------------------------------------------------------------------
The policies below are a STARTING POINT scoped for a learning sandbox, not a
finished production configuration. Before using this beyond a sandbox you
MUST review and narrow them, in particular:
  * the inference policy KEEPS Resource "*" on purpose — do NOT try to scope
    it to a model-specific ARN. bedrock-mantle:CreateInference does not take a
    model-specific resource ARN; the bedrock-mantle:Model condition below is
    what restricts which model may be invoked, so narrow the model THERE, not
    via Resource;
  * the model condition (bedrock-mantle:Model) pins ONE model — confirm it is
    the model you intend to allow, and add others deliberately;
  * the trust policy is scoped to your account via aws:SourceAccount and
    aws:SourceArn — keep it scoped; do not broaden the principal.
Always VERIFY the effective permissions (e.g. with the IAM policy simulator)
before deploying. See the security and prerequisites docs:
  https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-managed-agents-openai-prerequisites.html
  https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-managed-agents-openai-security.html
============================================================================

Usage:
  python create_session_role.py                 # create (prompts for confirmation)
  python create_session_role.py --yes           # create without prompting
  python create_session_role.py --dry-run       # print the policy JSON and exit; no AWS calls
  python create_session_role.py --role-name NAME --model MODEL

Options / environment overrides:
  --role-name NAME   role to create (default: $ROLE_NAME or
                     BedrockManagedAgentsPreviewInferenceServiceRole)
  --model MODEL      model allowed by the inference policy (default: $MODEL or
                     openai.gpt-5.6-luna)
  --aws-profile P    AWS profile used for AWS calls (default: $AWS_PROFILE)
  --yes              skip the confirmation prompt
  --dry-run          print both policy JSONs and exit 0 without any AWS calls
"""

import argparse
import json
import os
import sys

import boto3

# Default name of the role we create. Overridable via --role-name or ROLE_NAME.
DEFAULT_ROLE_NAME = "BedrockManagedAgentsPreviewInferenceServiceRole"
# Default model the inference policy allows. Overridable via --model or MODEL.
DEFAULT_MODEL = "openai.gpt-5.6-luna"
# Placeholder account id used only for --dry-run output (no AWS call made).
PLACEHOLDER_ACCOUNT = "123456789012"


# ---- policy document builders ----------------------------------------------
# Each returns a Python dict so the same object can be json.dumps'd for display
# (dry-run) or serialized and handed to boto3 for a real create/put. All take
# the account id as an argument so the same code path is used for the real
# account id and the dry-run placeholder.

def trust_policy(account: str) -> dict:
    """Trust policy attached to the session role.

    Lets bedrock-mantle.amazonaws.com assume the role, scoped to THIS account
    via aws:SourceAccount and aws:SourceArn so no other account can trigger it.
    """
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-mantle.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": account},
                    "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock-mantle:*:{account}:*"},
                },
            }
        ],
    }


def inference_policy(model: str) -> dict:
    """Inline inference policy attached to the session role.

    Keeps Resource "*" on purpose: bedrock-mantle:CreateInference takes no
    model-specific ARN. The bedrock-mantle:Model condition is what pins the
    model, so narrow the model there — not via Resource.
    """
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "bedrock-mantle:CreateInference",
                "Resource": "*",
                "Condition": {"StringEquals": {"bedrock-mantle:Model": model}},
            }
        ],
    }


def passrole_policy(account: str, role_name: str) -> dict:
    """iam:PassRole policy for your OWN identity (printed, not attached).

    Lets your calling identity pass this specific session role to BMA, scoped
    via iam:PassedToService so it can only be passed to bedrock-mantle.
    """
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "iam:PassRole",
                "Resource": f"arn:aws:iam::{account}:role/{role_name}",
                "Condition": {
                    "StringEquals": {"iam:PassedToService": "bedrock-mantle.amazonaws.com"}
                },
            }
        ],
    }


def bma_client_policy() -> dict:
    """BMA-client policy for your OWN identity (printed, not attached).

    Grants the session actions your identity needs to drive BMA sessions.
    """
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "bedrock-mantle:CreateAgentSession",
                    "bedrock-mantle:GetAgentSession",
                    "bedrock-mantle:ListAgentSessions",
                    "bedrock-mantle:CreateAgentSessionEvent",
                    "bedrock-mantle:ListAgentSessionEvents",
                    "bedrock-mantle:ListAgentSessionItems",
                    "bedrock-mantle:DeleteAgentSession",
                ],
                "Resource": "*",
            }
        ],
    }


def _dumps(doc: dict) -> str:
    """JSON-serialize a policy document for human display."""
    return json.dumps(doc, indent=2)


# Print the two policies the CALLER must attach to its own identity. Printed in
# both dry-run and real runs because this script never creates them for you.
# Everything here goes to STDERR: stdout is reserved for the final role ARN.
def print_caller_policies(account: str, role_name: str) -> None:
    print(
        "\n"
        "----------------------------------------------------------------------------\n"
        "ATTACH THESE TO YOUR OWN CALLING IDENTITY (user/role that invokes BMA).\n"
        "This script does NOT create or attach them — review and attach manually.\n"
        "\n"
        "1) iam:PassRole — lets you pass the session role to BMA:",
        file=sys.stderr,
    )
    print(_dumps(passrole_policy(account, role_name)), file=sys.stderr)
    print(
        "\n"
        "2) BMA-client policy — the session actions your identity needs:",
        file=sys.stderr,
    )
    print(_dumps(bma_client_policy()), file=sys.stderr)
    print(
        "\n"
        'Reminder: these are a least-privilege STARTING POINT. Review, narrow (the\n'
        'BMA-client Resource "*" in particular), and VERIFY before production.\n'
        "----------------------------------------------------------------------------",
        file=sys.stderr,
    )


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create the IAM session role BMA assumes for inference, plus its "
            "inline inference policy. Also PRINTS (not attaches) the two "
            "caller-side policies you must add to your own identity."
        )
    )
    parser.add_argument(
        "--role-name",
        default=os.environ.get("ROLE_NAME", DEFAULT_ROLE_NAME),
        help=(
            "role to create (default: $ROLE_NAME or "
            "BedrockManagedAgentsPreviewInferenceServiceRole)."
        ),
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("MODEL", DEFAULT_MODEL),
        help="model allowed by the inference policy (default: $MODEL or openai.gpt-5.6-luna).",
    )
    parser.add_argument(
        "--aws-profile",
        default=os.environ.get("AWS_PROFILE"),
        help="AWS profile used for AWS calls (default: $AWS_PROFILE).",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="skip the confirmation prompt.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print both policy JSONs and exit 0 without any AWS calls.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    role_name = args.role_name
    model = args.model

    # Name of the inline inference policy, derived from the role name so it
    # tracks whatever --role-name you chose (e.g. MyBmaRole -> MyBmaRolePolicy)
    # instead of a fixed, unrelated string.
    inference_policy_name = f"{role_name}Policy"

    # ---- dry-run: print everything, make no AWS calls, exit 0 --------------
    # Checked BEFORE any boto3 Session/client is built, so no credentials are
    # read and zero network calls happen in this branch.
    if args.dry_run:
        print("DRY RUN — no AWS calls will be made and nothing will be created.", file=sys.stderr)
        print(f"Using placeholder account id {PLACEHOLDER_ACCOUNT} for display only.", file=sys.stderr)
        print(f"Role name: {role_name}", file=sys.stderr)
        print(f"Model:     {model}", file=sys.stderr)

        print("", file=sys.stderr)
        print("Trust policy (attached to the session role):", file=sys.stderr)
        print(_dumps(trust_policy(PLACEHOLDER_ACCOUNT)), file=sys.stderr)

        print("", file=sys.stderr)
        print(
            f"Inline inference policy {inference_policy_name} (attached to the session role):",
            file=sys.stderr,
        )
        print(_dumps(inference_policy(model)), file=sys.stderr)

        print_caller_policies(PLACEHOLDER_ACCOUNT, role_name)

        print("", file=sys.stderr)
        print("Dry run complete. Re-run without --dry-run to create the role.", file=sys.stderr)
        return 0

    # ---- real run: needs credentials ---------------------------------------
    # Build the session (optionally pinned to a profile) and resolve the real
    # account id via STS. boto3 replaces the aws CLI here, so no CLI is needed.
    session = boto3.Session(profile_name=args.aws_profile)
    print("Looking up your AWS account id via sts get-caller-identity...", file=sys.stderr)
    try:
        account_id = session.client("sts").get_caller_identity()["Account"]
    except Exception as exc:  # noqa: BLE001 — creds may be absent/expired; report clearly
        print(
            f"Could not resolve your AWS account id ({exc}). "
            "Check your credentials/profile, or use --dry-run.",
            file=sys.stderr,
        )
        return 1
    if not account_id or account_id == "None":
        print(
            "Could not resolve your AWS account id. Check your credentials/profile.",
            file=sys.stderr,
        )
        return 1
    print(f"Account id: {account_id}", file=sys.stderr)

    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"

    # Show exactly what will be created before doing it.
    print(
        "\n".join(
            [
                "",
                "About to create (if it does not already exist):",
                f"  Role name : {role_name}",
                f"  Role ARN  : {role_arn}",
                f"  Model     : {model}",
                "",
                "Trust policy:",
            ]
        ),
        file=sys.stderr,
    )
    print(_dumps(trust_policy(account_id)), file=sys.stderr)
    print("", file=sys.stderr)
    print(f"Inline inference policy ({inference_policy_name}):", file=sys.stderr)
    print(_dumps(inference_policy(model)), file=sys.stderr)

    # Confirm unless --yes.
    if not args.yes:
        print("", file=sys.stderr)
        reply = input("Proceed with creating/updating this role? [y/N] ")
        if reply not in ("y", "Y", "yes", "YES"):
            print("Aborted. Nothing was created.", file=sys.stderr)
            return 0

    iam = session.client("iam")

    # Detect an existing role and inform rather than hard-erroring.
    try:
        iam.get_role(RoleName=role_name)
    except iam.exceptions.NoSuchEntityException:
        print(f"Creating role {role_name}...", file=sys.stderr)
        iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy(account_id)),
            Description="Session role assumed by Bedrock Managed Agents (preview) for inference.",
        )
        print("Role created.", file=sys.stderr)
    else:
        print(f"Role {role_name} already exists; leaving its trust policy as-is.", file=sys.stderr)
        print(f"Updating/ensuring the inline inference policy {inference_policy_name}.", file=sys.stderr)

    print(f"Putting inline inference policy {inference_policy_name} on {role_name}...", file=sys.stderr)
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName=inference_policy_name,
        PolicyDocument=json.dumps(inference_policy(model)),
    )
    print("Inline inference policy applied.", file=sys.stderr)

    # Print the caller-side policies for manual attach.
    print_caller_policies(account_id, role_name)

    print("", file=sys.stderr)
    print("Done. Session role ARN:", file=sys.stderr)
    # stdout gets ONLY the bare ARN, so it can be captured in a pipeline.
    print(role_arn)

    # Tell the user how the labs/preflight will find this role. If this is the
    # default role name, the labs resolve it automatically from the caller's
    # account id — no action needed. If it is a CUSTOM name, the labs would
    # otherwise build the DEFAULT-named ARN, so print a ready-to-paste export
    # of BMA_INFERENCE_ROLE_ARN (the env var resolve_role_arn checks first) so
    # every lab and the preflight target this exact role.
    if role_name == DEFAULT_ROLE_NAME:
        print(
            "\n"
            "This is the default role name, so the labs and preflight resolve it\n"
            "automatically from your account id — no --role-arn needed.",
            file=sys.stderr,
        )
    else:
        print(
            "\n"
            "You used a custom role name, so point the labs and preflight at it by\n"
            "exporting this in each terminal (or pass --role-arn <arn> per command):\n"
            "\n"
            f"  export BMA_INFERENCE_ROLE_ARN={role_arn}            # macOS / Linux\n"
            f'  $env:BMA_INFERENCE_ROLE_ARN="{role_arn}"            # Windows (PowerShell)',
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
