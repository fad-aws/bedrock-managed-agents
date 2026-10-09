#!/usr/bin/env bash
#
# create_session_role.sh — create the IAM session role that BMA (Bedrock
# Managed Agents, powered by OpenAI) assumes to perform model inference.
#
# BMA assumes this role (its trust policy trusts bedrock-mantle.amazonaws.com)
# to call inference on your behalf. The role carries an inline policy allowing
# bedrock-mantle:CreateInference for a specific model. This script creates that
# role and its inline inference policy.
#
# It also PRINTS (but does NOT create or attach) two policies you need on your
# own calling identity — the identity that invokes the BMA session APIs:
#   * an iam:PassRole policy so you may pass this role to BMA, and
#   * a BMA-client policy granting the session actions.
# Review those and attach them to your user/role yourself.
#
# ============================================================================
# LEAST PRIVILEGE — READ THIS
# ----------------------------------------------------------------------------
# The policies below are a STARTING POINT scoped for a learning sandbox, not a
# finished production configuration. Before using this beyond a sandbox you
# MUST review and narrow them, in particular:
#   * the inference policy uses Resource "*" — scope it to specific inference
#     resources/ARNs once you know what your account exposes;
#   * the model condition (bedrock-mantle:Model) pins ONE model — confirm it is
#     the model you intend to allow, and add others deliberately;
#   * the trust policy is scoped to your account via aws:SourceAccount and
#     aws:SourceArn — keep it scoped; do not broaden the principal.
# Always VERIFY the effective permissions (e.g. with the IAM policy simulator)
# before deploying. See the security and prerequisites docs:
#   https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-managed-agents-openai-prerequisites.html
#   https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-managed-agents-openai-security.html
# ============================================================================
#
# Usage:
#   ./create_session_role.sh                 # create (prompts for confirmation)
#   ./create_session_role.sh --yes           # create without prompting
#   ./create_session_role.sh --dry-run       # print the policy JSON and exit; no AWS calls
#   ./create_session_role.sh --role-name NAME --model MODEL
#
# Options / environment overrides:
#   --role-name NAME   role to create (default: $ROLE_NAME or
#                      BedrockManagedAgentsPreviewInferenceServiceRole)
#   --model MODEL      model allowed by the inference policy (default: $MODEL or
#                      openai.gpt-5.6-luna)
#   --aws-profile P    AWS profile used for AWS calls (default: $AWS_PROFILE)
#   --yes              skip the confirmation prompt
#   --dry-run          print both policy JSONs and exit 0 without any AWS calls

set -euo pipefail

# Resolve the directory this script lives in, so it works from any cwd.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

ROLE_NAME="${ROLE_NAME:-BedrockManagedAgentsPreviewInferenceServiceRole}"
MODEL="${MODEL:-openai.gpt-5.6-luna}"
AWS_PROFILE_ARG="${AWS_PROFILE:-}"
ASSUME_YES=0
DRY_RUN=0

# Placeholder account id used only for --dry-run output (no AWS call made).
PLACEHOLDER_ACCOUNT="123456789012"

usage() {
  sed -n '2,45p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# ---- parse args ------------------------------------------------------------
while [ $# -gt 0 ]; do
  case "$1" in
    --role-name)
      ROLE_NAME="${2:?--role-name requires a value}"; shift 2 ;;
    --model)
      MODEL="${2:?--model requires a value}"; shift 2 ;;
    --aws-profile)
      AWS_PROFILE_ARG="${2:?--aws-profile requires a value}"; shift 2 ;;
    --yes|-y)
      ASSUME_YES=1; shift ;;
    --dry-run)
      DRY_RUN=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Run with --help for usage." >&2
      exit 2 ;;
  esac
done

# Name of the inline inference policy, derived from the role name so it tracks
# whatever --role-name you chose (e.g. MyBmaRole -> MyBmaRolePolicy) instead of
# a fixed, unrelated string.
INFERENCE_POLICY_NAME="${ROLE_NAME}Policy"

# Build the array of AWS CLI auth args (only used when not in --dry-run).
AWS_ARGS=()
if [ -n "$AWS_PROFILE_ARG" ]; then
  AWS_ARGS+=(--profile "$AWS_PROFILE_ARG")
fi

# ---- policy document builders ----------------------------------------------
# All take the account id as $1 so the same code path is used for the real
# account id and the dry-run placeholder.

trust_policy_json() {
  local account="$1"
  cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "bedrock-mantle.amazonaws.com" },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": { "aws:SourceAccount": "${account}" },
        "ArnLike": { "aws:SourceArn": "arn:aws:bedrock-mantle:*:${account}:*" }
      }
    }
  ]
}
EOF
}

inference_policy_json() {
  cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "bedrock-mantle:CreateInference",
      "Resource": "*",
      "Condition": {
        "StringEquals": { "bedrock-mantle:Model": "${MODEL}" }
      }
    }
  ]
}
EOF
}

passrole_policy_json() {
  local account="$1"
  cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::${account}:role/${ROLE_NAME}",
      "Condition": {
        "StringEquals": { "iam:PassedToService": "bedrock-mantle.amazonaws.com" }
      }
    }
  ]
}
EOF
}

bma_client_policy_json() {
  cat <<EOF
{
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
        "bedrock-mantle:DeleteAgentSession"
      ],
      "Resource": "*"
    }
  ]
}
EOF
}

# Print the two policies the CALLER must attach to its own identity. Printed in
# both dry-run and real runs because this script never creates them for you.
print_caller_policies() {
  local account="$1"
  cat >&2 <<EOF

----------------------------------------------------------------------------
ATTACH THESE TO YOUR OWN CALLING IDENTITY (user/role that invokes BMA).
This script does NOT create or attach them — review and attach manually.

1) iam:PassRole — lets you pass the session role to BMA:
EOF
  passrole_policy_json "$account" >&2
  cat >&2 <<EOF

2) BMA-client policy — the session actions your identity needs:
EOF
  bma_client_policy_json >&2
  cat >&2 <<EOF

Reminder: these are a least-privilege STARTING POINT. Review, narrow (the
BMA-client Resource "*" in particular), and VERIFY before production.
----------------------------------------------------------------------------
EOF
}

# ---- dry-run: print everything, make no AWS calls, exit 0 ------------------
if [ "$DRY_RUN" = "1" ]; then
  echo "DRY RUN — no AWS calls will be made and nothing will be created." >&2
  echo "Using placeholder account id ${PLACEHOLDER_ACCOUNT} for display only." >&2
  echo "Role name: ${ROLE_NAME}" >&2
  echo "Model:     ${MODEL}" >&2

  echo >&2
  echo "Trust policy (attached to the session role):" >&2
  trust_policy_json "$PLACEHOLDER_ACCOUNT"

  echo >&2
  echo "Inline inference policy ${INFERENCE_POLICY_NAME} (attached to the session role):" >&2
  inference_policy_json

  print_caller_policies "$PLACEHOLDER_ACCOUNT"

  echo >&2
  echo "Dry run complete. Re-run without --dry-run to create the role." >&2
  exit 0
fi

# ---- real run: needs credentials -------------------------------------------
if ! command -v aws >/dev/null 2>&1; then
  echo "The AWS CLI (v2) is required for a real run. Install it, or use --dry-run." >&2
  exit 1
fi

echo "Looking up your AWS account id via sts get-caller-identity..." >&2
ACCOUNT_ID="$(aws "${AWS_ARGS[@]}" sts get-caller-identity --query Account --output text)"
if [ -z "$ACCOUNT_ID" ] || [ "$ACCOUNT_ID" = "None" ]; then
  echo "Could not resolve your AWS account id. Check your credentials/profile." >&2
  exit 1
fi
echo "Account id: ${ACCOUNT_ID}" >&2

ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

# Show exactly what will be created before doing it.
cat >&2 <<EOF

About to create (if it does not already exist):
  Role name : ${ROLE_NAME}
  Role ARN  : ${ROLE_ARN}
  Model     : ${MODEL}

Trust policy:
EOF
trust_policy_json "$ACCOUNT_ID" >&2
echo >&2
echo "Inline inference policy (${INFERENCE_POLICY_NAME}):" >&2
inference_policy_json >&2

# Confirm unless --yes.
if [ "$ASSUME_YES" != "1" ]; then
  echo >&2
  printf 'Proceed with creating/updating this role? [y/N] ' >&2
  read -r reply
  case "$reply" in
    y|Y|yes|YES) ;;
    *) echo "Aborted. Nothing was created." >&2; exit 0 ;;
  esac
fi

# Detect an existing role and inform rather than hard-erroring.
if aws "${AWS_ARGS[@]}" iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  echo "Role ${ROLE_NAME} already exists; leaving its trust policy as-is." >&2
  echo "Updating/ensuring the inline inference policy ${INFERENCE_POLICY_NAME}." >&2
else
  echo "Creating role ${ROLE_NAME}..." >&2
  aws "${AWS_ARGS[@]}" iam create-role \
    --role-name "$ROLE_NAME" \
    --assume-role-policy-document "$(trust_policy_json "$ACCOUNT_ID")" \
    --description "Session role assumed by Bedrock Managed Agents (preview) for inference." \
    >/dev/null
  echo "Role created." >&2
fi

echo "Putting inline inference policy ${INFERENCE_POLICY_NAME} on ${ROLE_NAME}..." >&2
aws "${AWS_ARGS[@]}" iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name "$INFERENCE_POLICY_NAME" \
  --policy-document "$(inference_policy_json)" \
  >/dev/null
echo "Inline inference policy applied." >&2

# Print the caller-side policies for manual attach.
print_caller_policies "$ACCOUNT_ID"

echo >&2
echo "Done. Session role ARN:" >&2
echo "$ROLE_ARN"
