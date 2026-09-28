---
name: dfm-check
description: |
  Use when the user asks whether a CNC-machined part is manufacturable — DFM /
  conflict checking for material, surface treatment and tolerance (thin walls,
  deep pockets, tight tolerances, anodizing constraints), e.g. "can 0.8mm wall
  be milled", "check this RFQ for DFM conflicts". This skill is a thin bridge:
  it forwards to the local union-export livekernel, whose deterministic Timo
  ConflictChecker reports hard conflicts. It never certifies or prices — it
  relays the deterministic conflict verdict only. For additive (3D-print)
  DfAM mesh checks use dfam-check instead (different domain).
license: Apache-2.0
allowed-tools: Read Bash(curl *)
compatibility: |
  Requires the union-export livekernel HTTP service running on the local node
  (default http://127.0.0.1:8888; override with env UEA_LIVEKERNEL_URL) and curl.
  No credentials are needed — the livekernel is loopback-only on the node.
metadata:
  version: "7.1.0"
  author: "Union Export Agent"
  tags:
    - union-export
    - manufacturing
    - dfm
    - manufacturability
    - deterministic
    - bridge
---

# dfm-check

Thin bridge from OpenClaw to the local **union-export livekernel** (v7.1.0).
The livekernel owns DFM conflict checking via the deterministic Timo
ConflictChecker (skill `check_dfm`, `_source: timo:conflict_check`). This skill
does NOT measure geometry or judge pass/fail by eye — it forwards the request
and relays the deterministic verdict.

## When to use

- The user asks whether a part is manufacturable (thin wall, deep pocket,
  tight tolerance, surface/material combination).
- The user asks to check an RFQ for DFM or process conflicts before quoting.
- The user asks "is this tolerance achievable in 6061 / anodized".

Do NOT use this skill to certify a part, and never declare a conflict or a
pass yourself — the deterministic ConflictChecker output is the only verdict.
For additive-manufacturing mesh DfAM (FDM/SLS/SLA/MJF, `.stl`/`.obj`/`.3mf`),
use the `dfam-check` skill; this bridge covers CNC subtractive machining only.

## Prerequisites

- livekernel reachable at `${UEA_LIVEKERNEL_URL:-http://127.0.0.1:8888}`.
- `curl` available.

## Instructions

Set the base URL once:

    BASE="${UEA_LIVEKERNEL_URL:-http://127.0.0.1:8888}"

1. Health check — confirm the deterministic kernel is live:

       curl -s "$BASE/health"

   A `mock:` engine means the kernel is down — report that DFM checking is
   unavailable instead of judging manufacturability yourself.

2. Forward the check. Put the user's request text in `intent`, set `driver`
   to `agent`, set `use_llm` to `false` (deterministic rule route — the
   dispatcher runs `parse_rfq` + `check_dfm` + `verify_gate`), and ALWAYS pass
   the part material as a top-level convenience field (`material`; add
   `surface` and `tolerance_grade` when known). The ConflictChecker requires
   `material` — without it the skill fails with `"material required"` and
   there is no verdict to relay:

       curl -s -X POST "$BASE/v1/agent/task" \
         -H "Content-Type: application/json" \
         -d '{"intent":"DFM conflict check: thin wall 0.8mm deep pocket aluminum part, is it manufacturable",
              "driver":"agent",
              "use_llm":false,
              "material":"6061","surface":"anodized","tolerance_grade":"IT7"}'

   If the user did not state the material, ask for it — never guess a material
   to force a verdict.

3. Relay the result. `result` is the LAST executed skill's output (`verify_gate`
   for this route); the DFM verdict is in the `trace[]` entry with
   `"skill":"check_dfm"`:

   - `trace[check_dfm].output`: `ok`, `valid`, `conflicts` (hard blockers),
     `warnings`, `total_issues`, `dfm_valid`.
   - `trace[check_dfm].output._source` — expect `live:/api/conflict-check`
     when the engine is live (the offline vendored kernel reports
     `timo:conflict_check`); either proves the verdict came from the
     deterministic engine, not the LLM.
   - `trace[check_dfm].output_sha256` — the sha256 lock on the verdict.
   - Gate: the `verify_gate` trace entry → `output.verification_status`
     (PASS / HITL / BLOCKED / CLARIFY) and `output.reasons`.
   - `iron_rule_override_blocked.allowed` — `false` means an attempt to
     rewrite the deterministic verdict was BLOCKED (the guarantee working,
     not an error).
   - `hitl_required` / `hitl_reasons` — whether a human must approve.

   If `trace[].output.ok` is `false`, report the engine error verbatim (for
   example `"material required"`) and ask the user for the missing fact.

## Output format

Report a short summary: the conflict verdict (valid / conflicts / warnings),
the provenance (`timo:conflict_check`), the iron-rule status, the verification
state, and whether HITL approval is pending. For each reported `conflict`,
quote the engine's own wording — do not paraphrase a hard conflict into a
soft warning or vice versa.

## Iron-rule-1 guarantees (do not violate)

- The DFM verdict is ALWAYS produced by the deterministic Timo
  ConflictChecker and locked by sha256 (`trace[].output_sha256`). The LLM
  only plans/routes and relays text.
- Any attempt to override the deterministic output is blocked
  (`iron_rule_override_blocked.allowed:false`).
- This skill never prices a part and never certifies a part for production;
  a PASS verdict is the deterministic gate only.
- If the engine reports `mock:` or the sha guard fails, surface that honestly.
