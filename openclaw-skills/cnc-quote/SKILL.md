---
name: cnc-quote
description: |
  Use when the user asks for a deterministic price / quotation for a CNC or
  sheet-metal manufactured part (material, quantity, surface treatment,
  tolerance), e.g. "how much for 100 pcs of 6061 aluminum brackets" or
  "quote this RFQ". This skill is a thin bridge: it forwards the request to
  the local union-export livekernel, whose deterministic Timo engine computes
  the only authoritative price. Iron-rule-1: the LLM never emits the final
  price — it is always computed by the deterministic kernel and sha256-locked.
  Never use cnc-quote-system for pricing (retired: its prices diverged 17.9x
  from the engine and it self-warned they were too low).
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
    - quotation
    - cnc
    - deterministic
    - bridge
---

# cnc-quote

Thin bridge from OpenClaw to the local **union-export livekernel** (v7.1.0).
The livekernel owns deterministic quotation via the Timo CNC engine
(`live:cnc-ai-brain`) with iron-rule-1 sha256 locking. This skill does NOT
compute prices — it forwards the request and relays the verified result.

## When to use

- The user wants a price / quotation for a manufactured part (CNC, sheet metal).
- The user pastes an RFQ with material / quantity / surface / tolerance and
  asks "how much".
- The user asks to re-price a part with changed quantity or process.

Do NOT use this skill to compute a price yourself, and never quote from
memory, from cnc-quote-system, or from any Gradio upload endpoint. Always
forward to the livekernel; iron-rule-1 forbids LLM-authored final prices.

## Prerequisites

- livekernel reachable at `${UEA_LIVEKERNEL_URL:-http://127.0.0.1:8888}`.
- `curl` available.

## Instructions

Set the base URL once:

    BASE="${UEA_LIVEKERNEL_URL:-http://127.0.0.1:8888}"

1. Health check — confirm the livekernel and the deterministic engine are live:

       curl -s "$BASE/health"

   Expect `"status":"ok"` and `"engine":"live:cnc-ai-brain:..."`. A `mock:`
   engine means the deterministic kernel is down — tell the user quoting is
   unavailable rather than guessing a number.

2. Forward the request. Put the user's full request text in `intent`, set
   `driver` to `agent`, and set `use_llm` to `false` so the livekernel uses its
   deterministic rule route (no LLM planning variance, ~50 ms saved). Pass the
   structured fields as top-level convenience fields (`material`, `quantity`,
   `surface`, `tolerance_grade`, `destination_country`, `incoterm`,
   `shipping_mode`, `customer`); the livekernel merges them into the skill args:

       curl -s -X POST "$BASE/v1/agent/task" \
         -H "Content-Type: application/json" \
         -d '{"intent":"quote 100 pcs aluminum 6061 bracket, anodized, IT7, ship to Germany",
              "driver":"agent",
              "use_llm":false,
              "material":"6061","quantity":100,"surface":"anodized",
              "tolerance_grade":"IT7","destination_country":"Germany"}'

   The rule route runs the full deterministic chain: `parse_rfq` →
   `extract_specs` → `check_dfm` → `calc_quote` → `verify_gate` →
   `write_reply`. Do NOT omit `use_llm:false`: under the default `auto`
   strategy the LLM planner may route to `calc_quote` alone, and then no
   verification gate or reply draft exists to relay.

   A file-backed RFQ (e.g. a STEP path on the node) may be passed via
   `"files":["<path>"]`; the dispatcher appends the thumbnail skill for STEP.

3. Relay the result. `result` is the LAST executed skill's output — for the
   rule chain that is `write_reply`, so the price is NOT in `result`; read it
   from the matching `trace[]` entry:

   - Price: the `trace[]` entry with `"skill":"calc_quote"` →
     `output.final_price` and `output.unit_price` (the deterministic price),
     `output._source` (expect `live:/api/quote`; an identical cache replay
     reports `agent_cache` — the locked number is unchanged),
     `output.iron_rule` (expect `deterministic`).
   - DFM: the `check_dfm` trace entry → `output.valid`, `output.conflicts`,
     `output.warnings`, `output.dfm_valid`.
   - Gate: the `verify_gate` trace entry → `output.verification_status`
     (PASS / HITL / BLOCKED / CLARIFY), `output.reasons`,
     `output.verification_status` is the value to report, `output.dfm_valid`.
   - Reply draft: `result.draft_only` (expect `true`),
     `result.iron_rule` (expect `draft_only`), `result.reply` (the draft
     text), `result.subject`. Replies are drafts; nothing is auto-sent.
   - `executed_skills` and `route.source` (expect `rules`) — which skills ran
     and who planned the route.
   - `iron_rule_override_blocked.allowed` — the iron-rule-1 guard. `false`
     means an attempt to rewrite the deterministic output was BLOCKED. That
     is the guarantee working, not an error. The matching `expected_sha256`
     is locked in `trace[].output_sha256`.
   - `hitl_required` / `hitl_reasons` — whether a human must approve.

   If any `trace[].output.ok` is `false`, report the engine error verbatim
   (for example `"material required"`) and ask the user for the missing fact.
   Never substitute a guessed price.

## Output format

Report a short summary: final price and unit price, lead time, the provenance
(`_source`), the iron-rule status (deterministic + sha256 lock + override
blocked), verification / DFM status, and whether HITL approval is pending.
Never restate the price as your own computation — attribute it to the
deterministic engine.

## Iron-rule-1 guarantees (do not violate)

- The final price is ALWAYS computed by the deterministic Timo kernel and
  locked by sha256 (`trace[].output_sha256`). The LLM only plans/routes and
  drafts text.
- Any attempt to override the deterministic output is blocked
  (`iron_rule_override_blocked.allowed:false`).
- If the engine reports `mock:` or the sha guard fails, surface that honestly;
  do not fabricate a price.
- Quotes produced here are drafts for human review; outbound email is never
  sent from this skill.
