# `bma-sessions` — Codex skill

A [Codex](https://developers.openai.com/codex/) skill that lets you work with
Amazon Bedrock Managed Agents (BMA, powered by OpenAI) sessions conversationally
— create, continue, inspect, list, and delete sessions, and attach an AgentCore
Gateway tool — by driving the Module 1 lab scripts in this repo. It targets the
`environment=none` mode.

> This README is for humans. Codex itself reads `SKILL.md` (the instructions +
> metadata it loads when the skill triggers); editing this README does not
> change skill behavior.

## What's in here

| File | Purpose |
|---|---|
| `SKILL.md` | The skill: `name` + `description` metadata and the instructions Codex follows. |
| `references/api-cheatsheet.md` | Exact BMA API call shapes, for tasks the lab scripts don't cover. |
| `README.md` | This file. |

## Prerequisites

The skill runs the Module 1 lab scripts, so the module must be set up first
(see [`modules/01-bma-environment-none/00-prerequisites.md`](../../../modules/01-bma-environment-none/00-prerequisites.md)):

- The Python virtualenv exists: `cd modules/01-bma-environment-none && python3 setup.py` (use `python` on Windows).
- Your AWS credentials/profile are valid (BMA is SigV4-signed; no OpenAI API key).
- A BMA session role exists (default `BedrockManagedAgentsPreviewInferenceServiceRole`).

## How to use it

1. **Launch Codex from the repo root** so the skill is discovered
   (Codex scans `.agents/skills/` from your current directory up to the repo
   root):

   ```bash
   cd /path/to/bedrock-managed-agents   # the repo root
   codex
   ```

2. **Confirm Codex sees it** — in the Codex session:

   ```
   /skills
   ```

   You should see `bma-sessions` listed.

3. **Invoke it**, either way:
   - **Explicitly** — type `$` and mention it, e.g. `$bma-sessions list my sessions`.
   - **Implicitly** — just describe the task; Codex matches the skill from your
     wording (e.g. "create a BMA session and ask it the capital of France").

Codex automatically detects skill changes. If an edit doesn't show up, restart
Codex.

## If it fails with an auth / expired-token error

BMA calls are signed with your AWS credentials, and credentials are **per
shell**. The most common failure is a stale or wrong profile, which shows up as
a `401 AuthenticationError` or an "invalid/expired security token" message. The
skill reports this as an authentication issue (not a network issue).

Fix it by pointing at a valid profile:

```bash
# If it's an AWS SSO profile, refresh the login:
aws sso login --profile <your-profile>

# Confirm the profile resolves to the expected account:
aws sts get-caller-identity --profile <your-profile>
```

Then tell Codex which profile to use, for example:

```
list my BMA sessions using AWS profile <your-profile>
```

…or set it for the whole session before launching Codex:

```bash
export AWS_PROFILE=<your-profile>
codex
```

(Every new terminal needs the profile set again unless you add the `export` to
your shell startup file.)

## Example prompts you can ask

Session basics:

- "Create a BMA session and ask it the capital of France."
- "Start a new BMA agent with terse instructions and ask it to explain SigV4."
- "Continue session `sess_abc123` and ask a follow-up: what's its population?"

Inspecting results:

- "Show me the items in session `sess_abc123`."
- "Dump session `sess_abc123` as JSON so I can see the tool calls."
- "What reasoning and tool-call items are in my last session?"

Listing and cleanup:

- "List my BMA sessions."
- "List the 50 most recent sessions, oldest first, as JSON."
- "Delete session `sess_abc123`."
- "List my sessions and delete the idle ones." (It will confirm before deleting.)

Shared to-do list (session state demo):

- "Start a shared BMA to-do list and add 'buy milk' as Alice."
- "Add 'book flights' as Bob to session `sess_abc123`."

AgentCore Gateway (advanced):

- "Create a gated to-do list session using Gateway ARN `arn:aws:bedrock-agentcore:...` and add 'buy milk' as Alice."
- "Join session `sess_abc123` and try to add 'water the plants' as Bob."

Specifying options in natural language works too:

- "…using AWS profile `bma-test`."
- "…in region us-west-2."
- "…with model `openai.gpt-5.6-luna`."

## Notes

- The skill makes **real AWS calls** that can incur charges (model inference).
- **Sessions are never auto-deleted.** The skill surfaces session ids and
  offers cleanup; delete sessions you no longer need.
- BMA is in **public preview** — APIs and default models can change.
