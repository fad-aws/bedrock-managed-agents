"""Preflight — a read-only "verify you're ready" check before Lab 01.

The goal of this script is to let a learner go from a fresh checkout to their
first successful BMA session without guessing. It inspects, and only inspects,
the pieces the labs depend on and reports each one as:

  * CONFIRMED  — this specific thing was verified just now.
  * UNVERIFIED — we could NOT check it (e.g. you lack IAM read permission).
                 This is NOT the same as "broken"; it means "unknown".
  * FAILED     — this is actively wrong and will stop the labs.


It is strictly READ-ONLY: it may call STS get-caller-identity and best-effort
IAM reads (get-role / get-role-policy / list-role-policies). It never creates a
session, never writes, and never mutates IAM. It also never prints credentials,
secret keys, or session tokens.

Run it from the module root with the venv active:

    python preflight.py
    python preflight.py --aws-profile my-profile --region us-east-1

Exit code: 0 when nothing is FAILED (UNVERIFIED is fine); non-zero if any
check FAILED.
"""

import argparse
import json
import os
import sys
import urllib.parse

# --- Import the shared module helpers ------------------------------------
# preflight.py lives at the module root, right next to bma_common.py, so the
# module root is simply this file's own directory. Insert it on sys.path so
# `import bma_common` works no matter which directory you run the script from.
MODULE_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, MODULE_ROOT)

import bma_common  # noqa: E402 — must come after the sys.path shim above

# Status constants. Keeping them as named values avoids typos and lets the
# summary logic below reason about them without magic strings scattered around.
CONFIRMED = "CONFIRMED"
UNVERIFIED = "UNVERIFIED"
FAILED = "FAILED"

# A short glyph per status so the output scans quickly in a terminal.
_GLYPH = {CONFIRMED: "[OK ]", UNVERIFIED: "[ ? ]", FAILED: "[FAIL]"}


def _policy_statements(doc):
    """Return a policy document's Statement entries as a list, or None.

    Normalizes the shapes an IAM policy document can take so the trust/
    inference checks don't have to:

      * boto3 returns IAM policy documents already parsed as a ``dict`` (it
        URL-decodes and JSON-parses the API's string form for us), which is
        the normal case here;
      * we still defensively accept a ``str`` (URL-encoded and/or raw JSON, as
        the underlying REST/CLI API returns) and parse it, so an unexpected
        shape degrades gracefully instead of raising;
      * ``Statement`` may be a single object rather than a list (the IAM
        policy grammar allows both) — we always return a list.

    Returns ``None`` when the document cannot be understood, so the caller can
    report UNVERIFIED rather than crash or over-claim.
    """
    if isinstance(doc, str):
        # Underlying IAM REST/CLI returns URL-encoded JSON; boto3 normally
        # decodes it, but handle the string form defensively anyway.
        try:
            doc = json.loads(urllib.parse.unquote(doc))
        except (ValueError, TypeError):
            return None
    if not isinstance(doc, dict):
        return None
    stmts = doc.get("Statement", [])
    if isinstance(stmts, dict):  # singleton statement -> list
        stmts = [stmts]
    if not isinstance(stmts, list):
        return None
    return [s for s in stmts if isinstance(s, dict)]


def _as_list(value):
    """Return a scalar-or-list IAM field as a list (``[]`` for None)."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


class Check:
    """One preflight result: a named check with a status and guidance.

    * name        — short label (e.g. "AWS identity").
    * status      — one of CONFIRMED / UNVERIFIED / FAILED.
    * detail      — one line of what we found (never secrets).
    * next_action — what to do about it; required for FAILED/UNVERIFIED so the
                    learner always has a concrete next step.
    """

    def __init__(self, name, status, detail, next_action=None):
        self.name = name
        self.status = status
        self.detail = detail
        self.next_action = next_action

    def render(self):
        """Return the printable block for this check (status line + detail)."""
        lines = [f"{_GLYPH[self.status]} {self.name}: {self.status}"]
        if self.detail:
            lines.append(f"       {self.detail}")
        # Only CONFIRMED checks have nothing more to do; the others always
        # carry a next action so the learner is never left guessing.
        if self.next_action:
            lines.append(f"       NEXT ACTION: {self.next_action}")
        return "\n".join(lines)


def check_python_and_sdk():
    """Confirm Python 3.12+ and that both SDKs import; show versions.

    FAILED if Python is too old or a required import is missing — in either
    case the labs cannot run and setup.py needs to be (re-)run.
    """
    py = "%d.%d.%d" % sys.version_info[:3]
    if sys.version_info[:2] < (3, 12):
        return Check(
            "Python & SDK",
            FAILED,
            f"Python {py} is too old; the labs need 3.12+.",
            "Install Python 3.12+ and re-run `python setup.py` (or `python3.12 setup.py`).",
        )
    try:
        import boto3  # noqa: E402 — imported lazily so a missing dep is a clean FAIL
        import openai  # noqa: E402
    except Exception as exc:  # noqa: BLE001 — any import failure is a setup problem
        return Check(
            "Python & SDK",
            FAILED,
            f"Python {py} OK, but importing the SDKs failed: {exc}",
            "Re-run `python setup.py` to (re)install openai[bedrock] and boto3 into the venv.",
        )
    openai_ver = getattr(openai, "__version__", "unknown")
    boto3_ver = getattr(boto3, "__version__", "unknown")
    return Check(
        "Python & SDK",
        CONFIRMED,
        f"Python {py}, openai {openai_ver}, boto3 {boto3_ver}.",
    )


def check_region(region):
    """Confirm the selected Region is one the labs support."""
    if region in bma_common.SUPPORTED_REGIONS:
        return Check("Region", CONFIRMED, f"Using supported Region {region}.")
    supported = ", ".join(bma_common.SUPPORTED_REGIONS)
    return Check(
        "Region",
        FAILED,
        f"Region {region!r} is not a supported labs Region.",
        f"Select a supported Region with --region (one of: {supported}).",
    )


def check_identity(profile):
    """Resolve the caller identity via STS get-caller-identity (read-only).

    Returns (Check, account_id). account_id is None when identity could not be
    resolved, so later checks can report UNVERIFIED instead of guessing.
    Never prints access keys or session tokens — only the account id and the
    caller ARN, which are safe to display.
    """
    try:
        import boto3  # noqa: E402

        session = boto3.Session(profile_name=profile)
        ident = session.client("sts").get_caller_identity()
    except Exception as exc:  # noqa: BLE001 — creds may be absent/expired; treat as FAIL
        who = f"profile {profile!r}" if profile else "the default credential chain"
        return (
            Check(
                "AWS identity",
                FAILED,
                f"Could not resolve credentials for {who}: {exc}",
                "Refresh your SSO session or AWS credentials (e.g. `aws sso login "
                "--profile <p>`), or pass --aws-profile with valid credentials.",
            ),
            None,
        )
    account = ident.get("Account")
    arn = ident.get("Arn")
    return (
        Check(
            "AWS identity",
            CONFIRMED,
            f"Account {account}, caller {arn}.",
        ),
        account,
    )


def _account_from_arn(role_arn):
    """Best-effort extract the account id from an IAM role ARN.

    ARN shape: arn:aws:iam::<account-id>:role/<name>. Returns None if the ARN
    does not have an account id in the expected position.
    """
    parts = role_arn.split(":")
    if len(parts) >= 5 and parts[4]:
        return parts[4]
    return None


def check_session_role(explicit_role_arn, profile, caller_account):
    """Resolve the exact session-role ARN the labs will use and show it.

    Returns (Check, role_arn). resolve_role_arn may itself need STS when no
    explicit ARN is given; if that fails we report UNVERIFIED (we could not
    determine the ARN) rather than FAILED (we have no evidence it is wrong).
    """
    try:
        role_arn = bma_common.resolve_role_arn(explicit_role_arn, profile)
    except Exception as exc:  # noqa: BLE001 — STS lookup for the default ARN can fail
        return (
            Check(
                "Session role",
                UNVERIFIED,
                f"Could not determine the role ARN: {exc}",
                "Pass --role-arn explicitly, or fix credentials so the default "
                "ARN can be built from your account id.",
            ),
            None,
        )

    role_account = _account_from_arn(role_arn)
    if caller_account and role_account:
        if role_account == caller_account:
            detail = f"{role_arn} (in your own account {caller_account})."
        else:
            detail = (
                f"{role_arn} (account {role_account}, which is NOT your caller "
                f"account {caller_account})."
            )
        return (Check("Session role", CONFIRMED, detail), role_arn)

    # We have the ARN but could not compare accounts (identity unknown).
    return (
        Check(
            "Session role",
            UNVERIFIED,
            f"{role_arn} (could not compare against your account — identity "
            "unresolved).",
            "Resolve the AWS identity check above to confirm the role is in "
            "your account.",
        ),
        role_arn,
    )


def check_iam_config(role_arn, profile):
    """Best-effort, read-only inspection of the session role's IAM config.

    Reads and INSPECTS the policy documents, not just their existence:
      * iam:GetRole -> the trust policy must allow
        bedrock-mantle.amazonaws.com to assume the role;
      * iam:ListRolePolicies + iam:GetRolePolicy -> at least one inline policy
        must Allow bedrock-mantle:CreateInference.
    This is a presence check over INLINE policies, not full IAM evaluation
    (no condition semantics, NotAction, permission boundaries, attached managed
    policies, or SCPs). It therefore reports:
      * FAILED only when the result is certain from what we can see — the role
        does not exist, the trust policy does not allow BMA to assume it, or an
        UNCONDITIONAL inline Deny blocks CreateInference;
      * CONFIRMED only when an inline Allow is present with no overriding Deny
        and no unevaluated condition;
      * UNVERIFIED whenever the effective result depends on something we did
        not evaluate — a conditional Allow or Deny, a document we cannot read
        (AccessDenied), an unparseable document, or no inline Allow (the
        permission may live in an attached managed policy we do not inspect).

    CONFIRMED means the trust and inference permission were actually seen; it
    still does not prove every session operation is authorized — only a real
    session call does.
    """
    if not role_arn:
        return Check(
            "IAM configuration",
            UNVERIFIED,
            "No role ARN was resolved, so nothing could be inspected.",
            "Resolve the Session role check above first.",
        )

    role_name = role_arn.split("/")[-1]
    try:
        import boto3  # noqa: E402
        from botocore.exceptions import ClientError  # noqa: E402

        iam = boto3.Session(profile_name=profile).client("iam")
    except Exception as exc:  # noqa: BLE001 — no creds/client means we cannot check
        return Check(
            "IAM configuration",
            UNVERIFIED,
            f"Could not build an IAM client to inspect the role: {exc}",
            "Fix the AWS identity check above, then re-run.",
        )

    try:
        role = iam.get_role(RoleName=role_name)["Role"]
    except ClientError as exc:  # noqa: BLE001 — distinguish NoSuchEntity vs AccessDenied
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("NoSuchEntity", "NoSuchEntityException"):
            return Check(
                "IAM configuration",
                FAILED,
                f"Role {role_name!r} does not exist in this account.",
                "Create it with `python scripts/create_session_role.py` (or ask an admin), "
                "or pass --role-arn for the role you actually use.",
            )
        if code in ("AccessDenied", "AccessDeniedException"):
            return Check(
                "IAM configuration",
                UNVERIFIED,
                f"Not allowed to read role {role_name!r} (iam:GetRole denied).",
                "This usually just means you lack IAM read permission; it does NOT "
                "mean setup is broken. Ask an admin to confirm the role if unsure.",
            )
        return Check(
            "IAM configuration",
            UNVERIFIED,
            f"Could not inspect role {role_name!r}: {exc}",
            "Re-run with valid credentials, or confirm the role with an admin.",
        )
    except Exception as exc:  # noqa: BLE001 — any other error is "unknown", not "broken"
        return Check(
            "IAM configuration",
            UNVERIFIED,
            f"Could not inspect role {role_name!r}: {exc}",
            "Re-run with valid credentials, or confirm the role with an admin.",
        )

    # The role exists and we can read it. Actually INSPECT the policy
    # documents — not just confirm existence — so a CONFIRMED here means we
    # verified the two things the labs depend on:
    #   1. the trust policy lets bedrock-mantle.amazonaws.com assume the role,
    #   2. an inline policy allows bedrock-mantle:CreateInference.
    # If a document is missing or wrong, that is a real FAILED. If we cannot
    # READ the documents (AccessDenied) we report UNVERIFIED, never CONFIRMED,
    # so a confirmed result reflects an actual check rather than mere
    # existence.

    # 1. Trust policy — from the get_role response we captured above. Normalize
    # the document shape; if we cannot parse it, say UNVERIFIED rather than
    # crash or guess.
    BMA_PRINCIPAL = "bedrock-mantle.amazonaws.com"
    trust_stmts = _policy_statements(role.get("AssumeRolePolicyDocument"))
    if trust_stmts is None:
        return Check(
            "IAM configuration",
            UNVERIFIED,
            f"Role {role_name!r} exists, but its trust policy document could "
            "not be parsed into a form we recognize.",
            "Inspect the trust policy manually (see 00-prerequisites.md); this "
            "is an unexpected document shape, not necessarily a misconfiguration.",
        )

    def _assume_matches(stmt):
        # Does this statement concern bedrock-mantle assuming the role via
        # sts:AssumeRole? (Used for both the Allow we need and a Deny we honor.)
        principal = stmt.get("Principal", {})
        services = _as_list(principal.get("Service")) if isinstance(principal, dict) else []
        actions = _as_list(stmt.get("Action"))
        assumes = any(a in ("sts:AssumeRole", "sts:*", "*") for a in actions)
        return BMA_PRINCIPAL in services and assumes

    # An explicit Deny that matches wins over any Allow, so check it first.
    denied = any(s.get("Effect") == "Deny" and _assume_matches(s) for s in trust_stmts)
    trust_ok = (not denied) and any(
        s.get("Effect") == "Allow" and _assume_matches(s) for s in trust_stmts
    )
    if not trust_ok:
        reason = (
            "an explicit Deny blocks bedrock-mantle from assuming it"
            if denied
            else "it does not Allow bedrock-mantle.amazonaws.com to call "
            "sts:AssumeRole"
        )
        return Check(
            "IAM configuration",
            FAILED,
            f"Role {role_name!r} exists, but its trust policy will not let BMA "
            f"assume it — {reason}.",
            "Fix the trust policy (see 00-prerequisites.md), or re-create the "
            "role with `python scripts/create_session_role.py`.",
        )

    # 2. Inline inference permission — read each inline policy document and
    # look for an Allow of bedrock-mantle:CreateInference.
    try:
        names = iam.list_role_policies(RoleName=role_name).get("PolicyNames", [])
    except Exception as exc:  # noqa: BLE001 — listing may be denied separately
        return Check(
            "IAM configuration",
            UNVERIFIED,
            f"Role {role_name!r} exists and trusts BMA, but its inline policies "
            f"could not be listed ({exc}).",
            "You can read the role but not its policies; this is a permission "
            "gap (iam:ListRolePolicies), not necessarily a misconfiguration.",
        )

    # Scan all INLINE policies for statements that touch CreateInference. We do
    # NOT do full IAM policy evaluation (condition semantics, NotAction,
    # permission boundaries, attached/managed policies, SCPs) — out of scope for
    # a readiness check. We only claim what we can actually see, and downgrade
    # to UNVERIFIED (never a false CONFIRMED or a false FAILED) whenever the
    # effective result depends on something we did not evaluate:
    #   * an UNCONDITIONAL matching Deny -> FAILED (it always denies);
    #   * a CONDITIONAL matching Deny -> UNVERIFIED (may not apply to the call);
    #   * a matching Allow with a Condition we don't evaluate -> UNVERIFIED;
    #   * a plain matching Allow with no overriding Deny -> CONFIRMED (presence);
    #   * NO inline Allow found -> UNVERIFIED, because the permission could come
    #     from an attached managed policy we did not inspect (absence of an
    #     inline Allow is not proof inference is denied).
    def _matches_inference(stmt):
        actions = _as_list(stmt.get("Action"))
        return any(
            a in ("bedrock-mantle:CreateInference", "bedrock-mantle:*", "*")
            for a in actions
        )

    allow_found = False
    allow_conditional = False
    deny_unconditional = False
    deny_conditional = False
    unreadable = []
    for name in names:
        try:
            raw = iam.get_role_policy(RoleName=role_name, PolicyName=name).get(
                "PolicyDocument", {}
            )
        except Exception:  # noqa: BLE001 — a single policy may be unreadable
            unreadable.append(name)
            continue
        stmts = _policy_statements(raw)
        if stmts is None:  # present but unparseable -> treat as unverifiable
            unreadable.append(name)
            continue
        for stmt in stmts:
            if not _matches_inference(stmt):
                continue
            effect = stmt.get("Effect")
            conditional = bool(stmt.get("Condition"))
            if effect == "Deny":
                if conditional:
                    deny_conditional = True
                else:
                    deny_unconditional = True
            elif effect == "Allow":
                allow_found = True
                if conditional:
                    allow_conditional = True

    # An UNCONDITIONAL matching Deny always wins -> inference denied.
    if deny_unconditional:
        return Check(
            "IAM configuration",
            FAILED,
            f"Role {role_name!r} trusts BMA, but an inline policy "
            "unconditionally Denies bedrock-mantle:CreateInference — inference "
            "will be denied regardless of any Allow.",
            "Remove or narrow the Deny (see 00-prerequisites.md), or use a role "
            "without it.",
        )

    # A CONDITIONAL matching Deny may or may not apply to the learner's call;
    # we don't evaluate conditions, so we cannot assert denial.
    if deny_conditional:
        return Check(
            "IAM configuration",
            UNVERIFIED,
            f"Role {role_name!r} has a Deny on bedrock-mantle:CreateInference "
            "that is gated by a Condition this check does not evaluate — "
            "whether inference is denied depends on that condition.",
            "Inspect the Deny's condition, or test with an actual session.",
        )

    # A conditional Allow may or may not apply at call time; we don't evaluate
    # conditions, so we cannot claim effective permission.
    if allow_found and allow_conditional:
        return Check(
            "IAM configuration",
            UNVERIFIED,
            f"Role {role_name!r} trusts BMA and has an Allow for "
            "bedrock-mantle:CreateInference, but it is gated by a Condition "
            "this check does not evaluate — effective permission is unknown.",
            "Confirm the condition (e.g. bedrock-mantle:Model) matches the "
            "model you will use, or test with an actual session.",
        )

    if allow_found:
        return Check(
            "IAM configuration",
            CONFIRMED,
            f"Role {role_name!r} trusts bedrock-mantle and allows "
            "bedrock-mantle:CreateInference (no overriding Deny; no "
            "unevaluated condition on the Allow). This is a presence check, "
            "not full IAM evaluation — only an actual session call proves every "
            "operation is authorized.",
        )

    if unreadable:
        return Check(
            "IAM configuration",
            UNVERIFIED,
            f"Role {role_name!r} trusts BMA, but inference permission could not "
            f"be confirmed: policies {', '.join(unreadable)} were not readable.",
            "You lack iam:GetRolePolicy on some policies; this is a permission "
            "gap, not necessarily a misconfiguration.",
        )

    # No INLINE Allow found. The permission may still come from an attached
    # managed policy, which this check does not inspect — so report UNVERIFIED
    # rather than claim inference is denied.
    return Check(
        "IAM configuration",
        UNVERIFIED,
        f"Role {role_name!r} exists and trusts BMA, but none of its INLINE "
        "policies allow bedrock-mantle:CreateInference. Attached (managed) "
        "policies were not inspected, so inference permission is unconfirmed — "
        "not necessarily denied.",
        "If you rely on a managed policy, verify it allows "
        "bedrock-mantle:CreateInference; otherwise add the inline inference "
        "policy with `python scripts/create_session_role.py --model <id>`.",
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Read-only preflight: verify Python/SDK, AWS identity, Region, "
            "session role, and IAM config before Lab 01. Makes no sessions and "
            "mutates nothing."
        )
    )
    # Reuse the same connection/role flags the labs use so --region /
    # --aws-profile / --role-arn behave identically here.
    bma_common.add_connection_args(parser)
    bma_common.add_role_arn_arg(parser)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    checks = []

    # 1. Python & SDK — purely local; no AWS involved.
    checks.append(check_python_and_sdk())

    # 2. Region — purely local membership check.
    checks.append(check_region(args.region))

    # 3. AWS identity — the first thing that touches AWS (read-only STS).
    identity_check, caller_account = check_identity(args.aws_profile)
    checks.append(identity_check)

    # 4. Session role — the exact ARN the labs will pass to BMA.
    role_check, role_arn = check_session_role(
        args.role_arn, args.aws_profile, caller_account
    )
    checks.append(role_check)

    # 5. IAM configuration — best-effort, read-only inspection of that role.
    checks.append(check_iam_config(role_arn, args.aws_profile))

    # Print each check as its own block.
    print("BMA Module 1 preflight — read-only readiness check\n")
    for check in checks:
        print(check.render())
        print()

    # Summarize. We deliberately do NOT say "all set": we report the tally and
    # whether anything is blocking.
    confirmed = sum(1 for c in checks if c.status == CONFIRMED)
    unverified = sum(1 for c in checks if c.status == UNVERIFIED)
    failed = sum(1 for c in checks if c.status == FAILED)

    summary = (
        f"Summary: {confirmed} confirmed, {unverified} unverified, "
        f"{failed} failed."
    )
    if failed:
        summary += (
            " Fix the FAILED checks above (see each NEXT ACTION) before Lab 01."
        )
    elif unverified:
        summary += (
            " Nothing is actively broken, but some checks could not be verified "
            "(see UNVERIFIED above). A clean run does not guarantee every "
            "session operation is authorized."
        )
    else:
        summary += (
            " No blockers found. Note: this does not guarantee every session "
            "operation is authorized — only what is listed above was checked."
        )
    print(summary)

    # Exit non-zero only when something is actively wrong (FAILED). UNVERIFIED
    # is informational, not blocking.
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
