# Lab 01 — Create a session

**What you learn:** how to create a BMA session with no execution
environment, submit the first prompt, and stream the agent's reply.

## Concept

A **session** is the durable, server-side container for one conversation
with an agent. You create it once, then submit **turns** (one user prompt +
the agent's response) against it. BMA keeps the full history on the server,
so later turns — even from a different terminal — see everything that came
before.

This lab uses `environment={"type": "none"}`: no sandbox is provisioned, so
the agent reasons and produces text output but cannot run code or local
tools. That is the simplest setup and the right place to start.

Three things are required to create a session:

- **`agent`** — the `model` to run and the `instructions` that shape its
  behavior.
- **`environment`** — `{"type": "none"}` for this module.
- **`role_arn`** — the IAM role BMA assumes to run inference. The typed SDK
  does not expose this field yet, so it is passed through `extra_body`.

The first prompt goes in `input` as a list of messages, each with
`content` parts of type `input_text`.

## What you'll run

`create_session.py` builds the client, resolves the role ARN, calls
`sessions.create(...)`, and then **drains the turn** — opens the event
stream and reads lifecycle events until the turn completes:

- prints the final text on `agent.session.turn.output_text.done`,
- stops on `agent.session.turn.completed` / `agent.session.completed`,
- raises on any failure event (`turn.failed`, `turn.cancelled`,
  `session.failed`, `environment.failed`, `error`).

## The command

Before your first run, complete the one-time
[prerequisites](../../00-prerequisites.md) (create the venv and configure your
AWS profile). As the recommended first check, run the read-only preflight from
the module root to confirm your Python/SDK, AWS identity, Region, session role,
and IAM config are in place:

```bash
python preflight.py
```

It reports each check as CONFIRMED / UNVERIFIED / FAILED; fix anything FAILED
(using the printed next action) before running the lab. See
[Verify you're ready](../../00-prerequisites.md#6-verify-youre-ready) for
details.

Then, in each new terminal, from the module root
(`modules/01-bma-environment-none`), activate the venv and make sure your AWS
profile is set (`export AWS_PROFILE=<your-aws-profile>` or pass `--aws-profile`):

```bash
python labs/lab-01-create-session/create_session.py "What is the capital of France?"
```

Override the model, Region, instructions, profile, or role as needed:

```bash
python labs/lab-01-create-session/create_session.py \
    --model openai.gpt-5.6-luna \
    --region us-west-2 \
    --instructions "You are a terse assistant." \
    --aws-profile <your-aws-profile> \
    "Explain SigV4 in one sentence."
```

Pass `--help` for the full flag list.

> **Note:** a non-default `--model` only works if the session role's inference
> policy allows that model (see
> [prerequisites](../../00-prerequisites.md#2-configure-aws-credentials-and-a-region));
> otherwise inference is denied.

## Expected output

The new session id prints to stdout; progress and the final turn event
print to stderr. You will see something like:

```text
Agent config: {
  "model": "openai.gpt-5.6-luna",
  "instructions": "You are a concise assistant. Answer the user's questions directly and accurately."
}
Created session: sess_abc123
--- prompt: 'What is the capital of France?'
{
  "type": "agent.session.turn.output_text.done",
  "text": "The capital of France is Paris."
}

Session kept open: sess_abc123
  * inspect its items:  python labs/lab-02-interpret-results/interpret_results.py --session-id sess_abc123
  * delete it when done: python labs/lab-05-delete-session/delete_session.py sess_abc123
```

Copy the `sess_...` id — the next labs reuse it.

## What to notice

- **`stream=False` on `create()`** returns the session object immediately;
  the turn's events are streamed separately with `events.stream()`. The
  create call still *starts* the first turn — that is why there is a turn
  to drain.
- **`role_arn` rides in `extra_body`**, not as a typed parameter — the BMA
  preview API requires it even though the SDK types do not list it.
- **The session is not deleted.** It stays open so you can keep working with
  it. Clean it up in [Lab 05](../lab-05-delete-session/README.md).

## Cleanup

When you are done, delete the session with
[Lab 05](../lab-05-delete-session/README.md):

```bash
python labs/lab-05-delete-session/delete_session.py sess_abc123
```

## Next

Continue to [Lab 02 — Interpret results](../lab-02-interpret-results/README.md)
to read what the agent actually produced.
