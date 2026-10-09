# Module 1 prerequisites

Before running any lab in this module, work through this page once. It covers
the tooling you need, how to configure AWS credentials, the IAM identities BMA
involves, and two ways to create the session role.

> **Public preview.** BMA (powered by OpenAI) is in preview. Default models,
> Region availability, and the exact IAM actions can change. Treat the policies
> here as a least-privilege **starting point** and confirm the current
> requirements in the official docs:
>
> - [Prerequisites](https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-managed-agents-openai-prerequisites.html)
> - [Security](https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-managed-agents-openai-security.html)

## 1. Install the tools

- **Python 3.12 or newer** — check with `python3 --version`.
- **AWS CLI v2** — check with `aws --version`. Used to configure credentials and
  (optionally) to create the session role.

Then build the module virtual environment and install dependencies
(`openai[bedrock]` and `boto3`):

```bash
cd modules/01-bma-environment-none
./setup.sh
```

Re-run `./setup.sh` whenever `requirements.txt` changes, or run
`FORCE=1 ./setup.sh` to rebuild the venv from scratch.

## 2. Configure AWS credentials and a Region

BMA calls are SigV4-signed with your AWS credentials — there is no OpenAI API
key. Pick a profile name once and reuse it for the rest of this page:

```bash
# Set this once per terminal to whatever you want your BMA profile called.
export BMA_PROFILE=<your-aws-profile>
```

Configure that profile and confirm it resolves:

```bash
aws configure --profile "$BMA_PROFILE"
aws sts get-caller-identity --profile "$BMA_PROFILE"
```

AWS credentials are **per terminal**. In each new shell, point the labs at your
profile with either:

```bash
export AWS_PROFILE="$BMA_PROFILE"
```

or by passing `--aws-profile "$BMA_PROFILE"` to each lab script. A stale or
wrong profile shows up as a `401 AuthenticationError` when you run a lab.

**Region and model.** This module defaults to Region `us-east-1` (choices:
`us-east-1`, `us-west-2`, `us-east-2`) and model `openai.gpt-5.6-luna`. Model and
Region availability are account-dependent. Use `--region` / `--model` to match
what your account exposes.

## 3. The three IAM identities

BMA involves up to three distinct identities. Keeping them separate is what the
IAM setup below is about:

1. **Caller / BMA-client identity** — the user or role *you* authenticate as to
   invoke the BMA session APIs (create/get/list/delete sessions, submit events,
   list items). It needs the BMA-client actions **and** permission to
   `iam:PassRole` the session role to BMA.
2. **Session role** — the role BMA *assumes* (via `bedrock-mantle.amazonaws.com`)
   to do customer-authorized work, chiefly model inference. Default name:
   `BedrockManagedAgentsPreviewInferenceServiceRole`.
3. **Execution-environment identity** — the identity under which an execution
   environment runs tools/code. **Not applicable for `environment=none`**, which
   is this entire module. It becomes relevant only for the self-hosted and
   AgentCore Runtime environments covered in later modules.

## 4. Create the session role

You can create the session role with the provided script, or by hand. Either
way, review the policies against least privilege before using them beyond a
sandbox.

The role name is **not** a hard requirement — BMA identifies the session role by
the ARN you pass in `role_arn` when creating a session, not by its name. Any
name works, in any role your account allows. Pick one once and reuse it below:

```bash
# Any name you like; this is just the example's default.
export BMA_ROLE_NAME=BedrockManagedAgentsPreviewInferenceServiceRole
```

Point the lab scripts at your role with `--role-arn` or
`export BMA_INFERENCE_ROLE_ARN=arn:aws:iam::<account-id>:role/$BMA_ROLE_NAME`.
If you skip both, the labs fall back to the default name above in your own
account.

### Option A — use the script

Preview the exact policies without touching AWS (no credentials needed):

```bash
cd modules/01-bma-environment-none
./scripts/create_session_role.sh --dry-run
```

Then create it for real (prompts for confirmation; pass `--yes` to skip, and
`--model` to override the model). Pass `--role-name` to control the name:

```bash
./scripts/create_session_role.sh --role-name "$BMA_ROLE_NAME"
```

The script creates the role plus its inline inference policy, and **prints** —
without creating — the two policies you must attach to your own calling identity
(the `iam:PassRole` policy and the BMA-client policy). Attach those yourself
after reviewing them.

### Option B — create it by hand (least privilege)

Replace `123456789012` with your own account id, `BMA_ROLE_NAME` with the role
name you chose above, and adjust the model as needed. The trust and inference
policies do not reference the role name; only the `iam:PassRole` resource ARN
below does, so keep that in sync with the name you actually create.

**Trust policy** on the session role (lets BMA assume it, scoped to your
account):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "bedrock-mantle.amazonaws.com" },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": { "aws:SourceAccount": "123456789012" },
        "ArnLike": { "aws:SourceArn": "arn:aws:bedrock-mantle:*:123456789012:*" }
      }
    }
  ]
}
```

**Inline inference policy** on the session role (allows inference for one
model):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "bedrock-mantle:CreateInference",
      "Resource": "*",
      "Condition": {
        "StringEquals": { "bedrock-mantle:Model": "openai.gpt-5.6-luna" }
      }
    }
  ]
}
```

**On your own calling identity**, attach an `iam:PassRole` policy so you may pass
the role to BMA:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::123456789012:role/BMA_ROLE_NAME",
      "Condition": {
        "StringEquals": { "iam:PassedToService": "bedrock-mantle.amazonaws.com" }
      }
    }
  ]
}
```

…and a BMA-client policy granting the session actions:

```json
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
```

## 5. Least privilege — review before deploying

These policies are a **starting point** for a learning sandbox, not a finished
production configuration. Before using them beyond a sandbox:

- Scope the inference policy's `Resource "*"` to specific inference
  resources/ARNs once you know what your account exposes.
- Confirm the `bedrock-mantle:Model` condition pins exactly the model(s) you
  intend to allow.
- Narrow the BMA-client policy's `Resource "*"` where your account supports
  resource-level scoping.
- Keep the trust policy scoped to your account (`aws:SourceAccount` /
  `aws:SourceArn`); do not broaden the principal.
- **Verify** the effective permissions (for example with the IAM policy
  simulator) before deploying.

Full guidance is in the official
[prerequisites](https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-managed-agents-openai-prerequisites.html)
and
[security](https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-managed-agents-openai-security.html)
docs.

---

Once your credentials and session role are in place, start with the
[module overview and lab index](README.md).
