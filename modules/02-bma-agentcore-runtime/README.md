# Module 2 — BMA with AgentCore Runtime

This module teaches the BMA (Bedrock Managed Agents, powered by OpenAI) session
workflow with an **AgentCore Runtime** as the execution environment
(`environment: {"type": "aws_bedrock_agentcore", ...}`). Where Module 1 used
`environment={"type": "none"}` — the agent reasoned and produced text but ran
nothing — here the agent runs in a **managed microVM** and can actually EXECUTE
commands against a workspace. That is the payoff: the agent does real work, and
you can read back exactly what it ran as `command_execution` items.

Two other things change from Module 1, both handled for you by
`bma_common.py`:

- **Auth is a bearer token.** Requests carry a short-lived token minted by
  `aws-bedrock-token-generator` (from your AWS credential chain) instead of
  SigV4-signing each call. There is still no OpenAI API key.
- **The session role is `BmaSessionRole-<region>`.** Its inline `BmaSession`
  policy allows model inference AND the Runtime invoke actions
  (`bedrock-agentcore:InvokeAgentRuntime` / `StopRuntimeSession`).

> **Public preview.** APIs, default models, and Region availability can change.
> See the
> [AgentCore Runtime get-started (BMA)](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-bma.html)
> tutorial and the
> [BMA prerequisites doc](https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-managed-agents-openai-prerequisites.html).

## Prerequisites

Do the one-time setup in [00-prerequisites.md](00-prerequisites.md) — it has
the full detail (the Runtime provisioning steps, the bearer-token vs SigV4
difference, the four IAM identities, and least-privilege guidance). In short,
from `modules/02-bma-agentcore-runtime`:

```bash
# 1. Provision the Runtime via the AgentCore CLI tutorial (AWS owns this),
#    then export its ARN (the labs read it, and derive the Region from it):
export BMA_RUNTIME_ARN=arn:aws:bedrock-agentcore:<region>:<account-id>:runtime/<runtime-id>

# 2. Build the venv (macOS/Linux; on Windows use `python setup.py`) and activate it:
python3 setup.py
source .venv/bin/activate

# 3. Create the session role and set your AWS profile:
python scripts/create_session_role.py        # reads $BMA_RUNTIME_ARN
export AWS_PROFILE=<your-aws-profile>

# 4. Verify you're ready (read-only; reports CONFIRMED / UNVERIFIED / FAILED):
python preflight.py
```

## Run convention

All labs use the same convention: with the venv **active** (set up once in the
[prerequisites](00-prerequisites.md#3-our-setup-venv--session-role); re-activate
in each new terminal with `source .venv/bin/activate`, or
`.\.venv\Scripts\Activate.ps1` on Windows), run the lab script directly. There
are no per-lab wrapper scripts.

```bash
python labs/lab-01-run-on-runtime/run_on_runtime.py
```

Each lab script imports the shared `bma_common.py` from the module root
automatically, so you can run it from any working directory. Every lab reads
the Runtime from `$BMA_RUNTIME_ARN` (or takes `--runtime <arn>`), and derives
the Region from it. Pass `--help` to any lab
script for its full flag list.

## Lab index

Work through the labs in order; each one builds on the ideas before it.

| # | Lab | What you learn |
|---|---|---|
| 01 | [lab-01-run-on-runtime](labs/lab-01-run-on-runtime/README.md) — `run_on_runtime.py` | Create a session on an AgentCore Runtime and watch the agent execute commands in a microVM. |
| 02 | [lab-02-interpret-results](labs/lab-02-interpret-results/README.md) — `interpret_results.py` | List a session's items and read the `command_execution` items (command + output) a Runtime produces. |
| 03 | [lab-03-continue-session](labs/lab-03-continue-session/README.md) — `continue_session.py` | Submit a follow-up turn and see the microVM workspace persist within the session. |
| 04 | [lab-04-delete-session](labs/lab-04-delete-session/README.md) — `delete_session.py` | Delete sessions and understand what cleanup does (and does not) remove. |
