"""Shared helpers for the Module 1 BMA labs (environment=none).

Every lab script in this module imports this file to build its client and
resolve the IAM session role the same way, so the labs stay small and
consistent. It centralizes:

  * the Regions BMA supports during preview and the defaults we use,
  * the common CLI flags (``--region`` / ``--aws-profile`` / ``--role-arn``),
  * ``make_client`` — construct the OpenAI SDK client wired to BMA, and
  * ``resolve_role_arn`` — figure out which session role ARN to pass to BMA.

BMA (powered by OpenAI) is in **public preview**: APIs, default models, and
Region availability can change. See the docs:

  https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-managed-agents-openai.html
  https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-managed-agents-openai-sessions.html
"""

import argparse
import os
import sys

import boto3
from openai import OpenAI
from openai.providers import bedrock

# Regions where BMA is available during preview. We expose these as the
# allowed choices for --region so a typo fails fast instead of hitting an
# endpoint that does not exist.
SUPPORTED_REGIONS = ("us-east-1", "us-west-2", "us-east-2")

# Region used when --region is not given.
DEFAULT_REGION = "us-east-1"

# Default model BMA uses for inference. BMA is in public preview, so which
# model ids are available depends on your Region and account; override with
# --model if openai.gpt-5.6-luna is not enabled for you. (Model availability
# is region/account dependent — list what your endpoint exposes if unsure.)
DEFAULT_MODEL = "openai.gpt-5.6-luna"

# A simple, general-purpose system instruction used by the labs that just
# need the agent to answer. Labs that demonstrate a specific behavior
# (e.g. the shared to-do list in Lab 03, the Gateway agent in Lab 06) define
# their own instructions locally instead.
DEFAULT_INSTRUCTIONS = (
    "You are a concise assistant. Answer the user's questions directly and "
    "accurately."
)

# Lifecycle events that mean the turn (or whole session) failed. When
# draining a turn we stop and raise on any of these instead of waiting
# forever for a completion that will never come.
FAILURE_EVENTS = {
    "agent.session.turn.failed",
    "agent.session.turn.cancelled",
    "agent.session.failed",
    "agent.session.environment.failed",
    "error",
}

# Default name of the IAM role that BMA assumes to do customer-authorized work
# (chiefly model inference). The calling identity must be allowed to
# iam:PassRole this role to BMA. The scripts/create_session_role.sh helper
# creates a role with this name by default. Override at runtime with
# --role-arn or the BMA_INFERENCE_ROLE_ARN env var if yours differs.
DEFAULT_ROLE_NAME = "BedrockManagedAgentsPreviewInferenceServiceRole"


def add_connection_args(parser: argparse.ArgumentParser) -> None:
    """Add the AWS/BMA connection flags shared by every lab script."""
    parser.add_argument(
        "--region",
        default=DEFAULT_REGION,
        choices=SUPPORTED_REGIONS,
        help=f"AWS Region to call BMA in (default: {DEFAULT_REGION}).",
    )
    parser.add_argument(
        "--aws-profile",
        default=os.environ.get("AWS_PROFILE"),
        help=(
            "Named profile from ~/.aws/config|credentials to sign requests "
            "with (default: $AWS_PROFILE, or the AWS default credential chain "
            "if unset). Use this if your 'default' profile has stale or invalid "
            "credentials (e.g. an expired SSO session or rotated static keys), "
            "which otherwise shows up as a 401 AuthenticationError."
        ),
    )


def add_role_arn_arg(parser: argparse.ArgumentParser) -> None:
    """Add the --role-arn flag (only needed for session-creating calls)."""
    parser.add_argument(
        "--role-arn",
        default=os.environ.get("BMA_INFERENCE_ROLE_ARN"),
        help=(
            "ARN of the IAM session role BMA assumes for inference. Required "
            f"for this preview. Default: ${{BMA_INFERENCE_ROLE_ARN}}, or "
            f"'arn:aws:iam::<account-id>:role/{DEFAULT_ROLE_NAME}' using the "
            "calling identity's account id if neither is set."
        ),
    )


def make_client(region: str, aws_profile: str | None) -> OpenAI:
    """Build an OpenAI client wired to the BMA ``bedrock-mantle`` endpoint.

    The ``bedrock`` provider resolves the regional ``bedrock-mantle`` endpoint
    and SigV4-signs every request with your AWS credentials -- there is no
    OpenAI API key involved. Passing ``profile`` pins which ~/.aws profile
    signs the request instead of relying on whatever the default credential
    chain resolves to (which can silently pick up a stale/expired "default"
    profile).
    """
    return OpenAI(provider=bedrock(region=region, endpoint="mantle", profile=aws_profile))


def resolve_role_arn(explicit_role_arn: str | None, aws_profile: str | None) -> str:
    """Resolve the session role ARN BMA assumes for inference.

    Precedence: an explicit --role-arn / BMA_INFERENCE_ROLE_ARN wins; otherwise
    we build the default role name in the caller's own account id (looked up
    via STS get-caller-identity).
    """
    if explicit_role_arn:
        return explicit_role_arn

    session = boto3.Session(profile_name=aws_profile)
    account_id = session.client("sts").get_caller_identity()["Account"]
    role_arn = f"arn:aws:iam::{account_id}:role/{DEFAULT_ROLE_NAME}"
    print(
        f"No --role-arn given; defaulting to {role_arn} "
        "(override with --role-arn or BMA_INFERENCE_ROLE_ARN if this role "
        "does not exist or isn't the one you want BMA to assume).",
        file=sys.stderr,
    )
    return role_arn


def drain_turn(client: OpenAI, session_id: str, print_output: bool = True) -> None:
    """Stream the in-flight turn's events until it completes.

    A "turn" is one request/response cycle on a session. After a turn starts
    (by creating the session with an initial ``input``, or by submitting a
    message to the events endpoint), the agent emits a stream of events:
    reasoning, output-text deltas, the final output-text, and finally a
    turn-completed event. This opens the event stream and consumes it until
    the turn is done:

      * when ``print_output`` is True, print the final assistant text when we
        see ``...turn.output_text.done`` (its ``to_json()`` shows role,
        content, item id, etc.),
      * stop on ``...turn.completed`` / ``...session.completed``,
      * raise on any ``FAILURE_EVENTS`` so a failed turn is loud, not silent.

    Lab 02 passes ``print_output=False`` because it inspects the session's
    durable items afterward rather than echoing the streamed text.
    """
    with client.beta.agents.sessions.events.stream(session_id) as events:
        for event in events:
            if event.type in FAILURE_EVENTS:
                raise RuntimeError(f"Agent lifecycle failure: {event.type}")
            if print_output and event.type == "agent.session.turn.output_text.done":
                print(event.to_json())
            if event.type in {"agent.session.turn.completed", "agent.session.completed"}:
                break
