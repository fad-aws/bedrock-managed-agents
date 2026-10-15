# BMA API cheatsheet (environment=none)

Exact call shapes for Amazon Bedrock Managed Agents (BMA, powered by OpenAI),
preview, via the OpenAI Python SDK's `bedrock` provider. Use these only when
the Module 1 lab scripts don't cover the task; otherwise run the scripts.
Reuse `modules/01-bma-environment-none/bma_common.py` for the client and role
resolution rather than re-deriving them.

Public preview: APIs, request/response shapes, and default models can change.
Docs: https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-managed-agents-openai.html

## Install / client

```
pip install "openai[bedrock]" boto3
```

```python
from openai import OpenAI
from openai.providers import bedrock

# SigV4-signed to the regional bedrock-mantle endpoint; no OpenAI API key.
client = OpenAI(provider=bedrock(region="us-east-1", endpoint="mantle", profile="my-aws-profile"))
```

- Supported regions: `us-east-1` (default), `us-west-2`, `us-east-2`.
- Signing service `bedrock-mantle`; endpoint host
  `https://bedrock-mantle.<region>.api.aws`.
- `profile` pins which `~/.aws` profile signs requests.

## Session role

BMA assumes an IAM role (`role_arn`) for inference. Resolve it like
`bma_common.resolve_role_arn`: prefer an explicit arn / `BMA_INFERENCE_ROLE_ARN`,
else build `arn:aws:iam::<account>:role/BedrockManagedAgentsPreviewInferenceServiceRole`
using the caller's account id from STS `get_caller_identity`.

## Create a session (and start its first turn)

```python
sess = client.beta.agents.sessions.create(
    agent={"model": "openai.gpt-5.6-luna", "instructions": "You are a concise assistant."},
    environment={"type": "none"},            # no execution environment
    extra_body={"role_arn": role_arn},        # SDK doesn't type role_arn yet; preview API requires it
    input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
    stream=False,                             # returns the session; stream the turn separately
)
session_id = sess.id                          # e.g. "sess_abc123"
```

Attach an AgentCore Gateway MCP tool (fixed at creation) by adding to `agent`:

```python
agent["tools"] = [
    {"type": "mcp", "server_label": "gateway_tools", "connector_id": "<gateway-arn>"}
]
```

The Gateway is referenced by ARN via `connector_id` — NOT a URL + `transport`
block (that fails schema validation). The session role needs
`bedrock-agentcore:InvokeGateway` on the Gateway, and the Gateway's MCP
`supportedVersions` must include `2025-03-26`.

## Submit a follow-up turn on an existing session

```python
client.beta.agents.sessions.events.create(
    session_id,
    events=[{
        "type": "agent.session.input.message",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": text}]}],
    }],
)
```

## Drain a turn's event stream

```python
FAILURE_EVENTS = {
    "agent.session.turn.failed", "agent.session.turn.cancelled",
    "agent.session.failed", "agent.session.environment.failed", "error",
}
with client.beta.agents.sessions.events.stream(session_id) as events:
    for event in events:
        if event.type in FAILURE_EVENTS:
            raise RuntimeError(f"Agent lifecycle failure: {event.type}")
        if event.type == "agent.session.turn.output_text.done":
            print(event.to_json())            # the final assistant text for the turn
        if event.type in {"agent.session.turn.completed", "agent.session.completed"}:
            break
```

## List sessions

```python
page = client.beta.agents.sessions.list(limit=20, order="desc")
sessions = page.data                          # read page.data only — do NOT iterate the pager
# page.has_more -> more exist; raise limit (max 100). The preview endpoint's
# auto-built `after` cursor returns "malformed base64", so single-page only.
```

## List a session's items (interpret results)

```python
page = client.beta.agents.sessions.items.list(session_id, limit=20, order="asc")
items = page.data                             # same single-page caveat as above
# items are a tagged union by .type:
#   message            -> .role, .content[] (parts with .text / .type)
#   reasoning          -> model reasoning summary
#   mcp_call           -> .server_label, .name, .arguments, .error (null on success)
#   command_execution  -> .command, .output (only with an execution environment)
# For JSON, use i.model_dump(mode="json") to avoid pydantic union warnings.
```

## Delete a session

```python
client.beta.agents.sessions.delete(session_id)   # never auto-deleted; clean up explicitly
```

## IAM quick reference

- Caller needs: `bedrock-mantle:CreateAgentSession`, `GetAgentSession`,
  `ListAgentSessions`, `CreateAgentSessionEvent`, `ListAgentSessionEvents`,
  `ListAgentSessionItems`, `DeleteAgentSession`, plus `iam:PassRole` on the
  session role (condition `iam:PassedToService = bedrock-mantle.amazonaws.com`).
- Session role trust: principal `bedrock-mantle.amazonaws.com`, scoped by
  `aws:SourceAccount` / `aws:SourceArn`. Inference permission:
  `bedrock-mantle:CreateInference` (Resource `*`, narrowed by a
  `bedrock-mantle:Model` condition). For Gateway labs, also
  `bedrock-agentcore:InvokeGateway` on the Gateway ARN.
