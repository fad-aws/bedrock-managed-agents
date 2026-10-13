---
name: bma-sessions
description: >-
  Work with Amazon Bedrock Managed Agents (BMA, powered by OpenAI) sessions
  in this repo: create a session, submit prompts/turns, interpret a session's
  items/results, list sessions, delete sessions, and attach an AgentCore
  Gateway MCP tool — all for the environment=none mode. Trigger when the user
  mentions BMA, Bedrock Managed Agents, bedrock-mantle, a BMA session
  (sess_...), or asks to run/continue/inspect/clean up an OpenAI-on-Bedrock
  agent session. Not for self-hosted or AgentCore Runtime execution
  environments.
---

# BMA sessions (environment=none)

This skill drives the Module 1 lab scripts in this repository to work with
Amazon Bedrock Managed Agents (BMA, powered by OpenAI) sessions. BMA is a
public preview; APIs and default models can change.

**Do not reimplement the BMA API.** Prefer running the existing, verified lab
scripts under `modules/01-bma-environment-none/labs/`. Only write ad-hoc API
calls if the user asks for something the scripts do not cover — in that case
read `references/api-cheatsheet.md` (next to this file) for the exact call
shapes, and reuse `modules/01-bma-environment-none/bma_common.py`.

## Safety and cost (read first)

- These scripts make **real AWS calls** signed with the user's credentials and
  can **incur charges** (model inference). Treat creating sessions and
  submitting turns as side-effecting actions.
- **Sessions are never auto-deleted.** Whenever you create sessions during a
  task, tell the user the session id(s) and offer to delete them with Lab 05
  when done. Do not leave orphaned sessions silently.
- Never print or paste the user's AWS credentials, tokens, or full role ARNs
  with account ids into chat beyond what a command strictly needs.
- Deleting a BMA session removes its server-side history but does NOT delete
  customer-owned resources (e.g. an AgentCore Gateway or its Lambda).

## Prerequisites (verify before running anything)

1. **Working directory & venv.** Run scripts from the module root
   `modules/01-bma-environment-none`. The Python venv must exist and be
   active. If it does not exist, create it:
   `cd modules/01-bma-environment-none && python3 setup.py` (use `python` on
   Windows), then `source .venv/bin/activate`.
2. **AWS profile.** BMA calls are SigV4-signed with AWS credentials (no OpenAI
   API key). Credentials are per-shell. If the user hits a
   `401 AuthenticationError` or an expired/invalid token, the profile is
   wrong or stale — have them set `export AWS_PROFILE=<their-profile>` (or pass
   `--aws-profile <profile>` to each script) and confirm with
   `aws sts get-caller-identity --profile <profile>`.
3. **Session role.** BMA assumes an IAM session role for inference, resolved
   via `--role-arn` / `$BMA_INFERENCE_ROLE_ARN`, else the default
   `BedrockManagedAgentsPreviewInferenceServiceRole` in the caller's account.
   If the role is missing, point the user at
   `modules/01-bma-environment-none/00-prerequisites.md` and
   `scripts/create_session_role.py`.
4. **Region & model.** Supported regions: us-east-1 (default), us-west-2,
   us-east-2. Default model `openai.gpt-5.6-luna`; availability is
   region/account dependent. Pass `--region` / `--model` to override.

Always invoke scripts with the venv's Python, e.g.
`python labs/lab-01-create-session/create_session.py ...` after activating the
venv (or `.venv/bin/python labs/...` without activating).

## Operations (map the user's intent to a lab script)

All paths are relative to `modules/01-bma-environment-none`.

### Create a session and submit the first prompt
Use `labs/lab-01-create-session/create_session.py`.
```
python labs/lab-01-create-session/create_session.py "What is the capital of France?"
```
Optional: `--model`, `--region`, `--instructions`, `--aws-profile`,
`--role-arn`. It prints `Created session: sess_...` to stdout — capture that
id and report it to the user; later operations reuse it.

### Interpret a session's results (list its items)
Use `labs/lab-02-interpret-results/interpret_results.py`.
```
python labs/lab-02-interpret-results/interpret_results.py --session-id sess_abc123
python labs/lab-02-interpret-results/interpret_results.py --session-id sess_abc123 --json
```
Items are a tagged union (`message` with role, `reasoning`, `mcp_call`,
`command_execution`). Use `--json` to inspect tool-call detail, especially an
`mcp_call` item's `server_label`, `name`, and `error`. With no `--session-id`
it creates a throwaway session, asks one prompt, then lists.

### Demonstrate durable/shared session state (to-do list)
Use `labs/lab-03-session-state/session_state.py`. First run (no
`--session-id`) creates a shared list and prints the id; later runs join it.
```
python labs/lab-03-session-state/session_state.py --user Alice "buy milk"
python labs/lab-03-session-state/session_state.py --session-id sess_abc123 --user Bob "book flights"
```

### List sessions
Use `labs/lab-04-list-sessions/list_sessions.py`.
```
python labs/lab-04-list-sessions/list_sessions.py
python labs/lab-04-list-sessions/list_sessions.py --limit 50 --order asc --json
```
This endpoint does not auto-paginate; raise `--limit` (max 100) if more exist.

### Delete session(s) — cleanup
Use `labs/lab-05-delete-session/delete_session.py`.
```
python labs/lab-05-delete-session/delete_session.py sess_abc123 sess_def456
```
Offer this whenever sessions created during the task are no longer needed.

### Attach an AgentCore Gateway MCP tool (advanced)
Use `labs/lab-06-agentcore-gateway/gateway_session.py`. Requires a
pre-provisioned Gateway ARN (not created here). The tool is fixed at session
creation, so `--gateway-arn` is required on create and omitted when joining.
```
python labs/lab-06-agentcore-gateway/gateway_session.py \
  --gateway-arn arn:aws:bedrock-agentcore:us-east-1:<acct>:gateway/<id> \
  --user Alice "buy milk"
python labs/lab-06-agentcore-gateway/gateway_session.py --session-id sess_abc123 --user Bob "book flights"
```
Gateway requirements and debugging are documented in that lab's README; if a
tool call fails, inspect the `mcp_call` item via Lab 02 `--json`.

## Workflow guidance

- Pick the single script matching the user's intent; do not chain
  destructive operations without confirming.
- Before create/continue operations, confirm prerequisites (venv + profile).
- After creating any session, surface the `sess_...` id and remind the user it
  persists until deleted.
- When a run errors, read the actual message: `401`/expired token = AWS creds;
  a generic `-32603: tools/list failed at the AgentCore gateway` on an
  `mcp_call` item = Gateway IAM or MCP protocol-version issue (see Lab 06).
- For anything the scripts do not cover, consult `references/api-cheatsheet.md`
  and build on `bma_common.py` rather than hand-rolling client/auth logic.
