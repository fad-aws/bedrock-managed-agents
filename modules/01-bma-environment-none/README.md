# Module 1 — BMA with `environment=none`

This module teaches the core BMA (Bedrock Managed Agents, powered by OpenAI)
session workflow using **no execution environment**
(`environment: {"type": "none"}`). With `none`, the agent reasons and calls
model inference (and, in the stretch lab, remote MCP tools) — there is no
sandbox running code or local tools. That makes it the simplest place to learn
the session APIs, so it is where we start.

> **Public preview.** APIs, default models, and Region availability can change.
> See the [prerequisites doc](https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-managed-agents-openai-prerequisites.html).

## Prerequisites

Do the one-time setup first: install Python 3.12+ and the AWS CLI v2, configure
AWS credentials, and create the session role. The full walkthrough — including
the three IAM identities and least-privilege guidance — is in
[00-prerequisites.md](00-prerequisites.md).

### 1. Build the virtual environment

Everything in this module runs inside a per-module Python virtualenv. Create it
once:

```bash
cd modules/01-bma-environment-none
./setup.sh
```

### 2. Set your AWS profile in every terminal

AWS credentials are **per terminal**. In each new shell, either export the
profile or pass it per command:

```bash
export AWS_PROFILE=<your-aws-profile>
# ...or add --aws-profile <your-aws-profile> to each lab command
```

A stale or wrong profile shows up as a `401 AuthenticationError`. Fix it by
exporting the correct `AWS_PROFILE` (or passing `--aws-profile`) for that
terminal.

## Run convention

All labs use the same convention: **activate the venv, then run the lab script
directly.** There are no per-lab wrapper scripts.

```bash
source .venv/bin/activate
python labs/lab-01-create-session/create_session.py "Hello, BMA!"
```

Each lab script imports the shared `bma_common.py` from the module root
automatically, so you can run it from any working directory. Pass `--help` to
any lab script for its full flag list (region, model, instructions, role ARN,
and so on).

## Lab index

Work through the labs in order; each one builds on the ideas before it.

| # | Lab | What you learn |
|---|---|---|
| 01 | [lab-01-create-session](labs/lab-01-create-session/README.md) — `create_session.py` | Create a session, submit the first prompt, and stream the agent's output. |
| 02 | [lab-02-interpret-results](labs/lab-02-interpret-results/README.md) — `interpret_results.py` | List a session's items and read the tagged-union result shape (messages, reasoning, tool calls). |
| 03 | [lab-03-session-state](labs/lab-03-session-state/README.md) — `session_state.py` | Build a shared to-do list where several terminals add to the same session, showing durable, server-side state shared across users. |
| 04 | [lab-04-list-sessions](labs/lab-04-list-sessions/README.md) — `list_sessions.py` | List sessions in the account/Region and read their status and metadata. |
| 05 | [lab-05-delete-session](labs/lab-05-delete-session/README.md) — `delete_session.py` | Delete sessions and understand cleanup (sessions are never auto-deleted). |
| 06 | [lab-06-agentcore-gateway](labs/lab-06-agentcore-gateway/README.md) — `gateway_session.py` | **Stretch/advanced:** attach an AgentCore Gateway MCP tool and gate each add to the Lab 03 to-do list on the tool's result. |

> The lab files are added in the labs' own commits; the directory and script
> names above are the stable paths every lab uses.
