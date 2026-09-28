---
name: email-quote
description: |
  Use when the user asks to work the mailbox as a quotation desk — list
  inbound RFQ emails on the node, re-run the deterministic pipeline on a
  chosen mail, and inspect the resulting quote draft, DFM verdict and reply
  draft. This skill is a thin bridge: it forwards to the local union-export
  livekernel mailbox pipeline, which classifies, extracts, prices via the
  deterministic Timo engine and drafts the reply. Iron-rule-1 / 铁律①: SMTP is
  OFF by default — replies are always draft_only and require human approval;
  nothing is ever auto-sent. Replaces the retired CodeBuddy email-quote
  worker (which auto-scanned QQ mail and auto-replied — no HITL, no price
  lock, no audit chain).
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
    - mailbox
    - rfq
    - draft-only
    - hitl
    - bridge
---

# email-quote

Thin bridge from OpenClaw to the local **union-export livekernel** (v7.1.0)
mailbox pipeline. The livekernel owns the whole chain: IMAP pull (already
running on the node), RFQ classification, deterministic Timo pricing,
conflict checking, sha256 price lock, and draft-only reply generation. This
skill does NOT read mail itself and never sends anything — it lists what the
livekernel has pulled and drives the pipeline on demand.

## When to use

- The user asks to process customer inquiry emails / draft quotation replies.
- The user asks "what RFQ mails are pending" or "quote this mail".
- The user asks to re-run a mail that was skipped, failed, or is gray-zone.

Do NOT use this skill to connect to IMAP/SMTP directly. The livekernel puller
owns mailbox credentials and the ledger; egress is draft_only. Never send a
reply yourself — SMTP is disabled by default (铁律①) and every reply needs
human approval in the workbench.

## Prerequisites

- livekernel reachable at `${UEA_LIVEKERNEL_URL:-http://127.0.0.1:8888}`.
- `curl` available.

## Instructions

Set the base URL once:

    BASE="${UEA_LIVEKERNEL_URL:-http://127.0.0.1:8888}"

1. List inbound mail the livekernel has already pulled:

       curl -s "$BASE/v1/mail/inbox?limit=20"

   Each item carries `mail_id`, `subject`, `from`, `filter` (`rfq` / `gray` /
   `skip`), `status`, `pending` (ledger state: DONE / HITL / FAILED /
   SKIPPED) and `badges` (for example `NON_RFQ`, `GRAY_REVIEW`). Only mails
   with `filter: "rfq"` (or a gray-zone mail the user explicitly re-checks)
   are quotation candidates.

2. Drive the deterministic pipeline on one mail (manual reprocess — it
   bypasses classification/dedup and is audit-logged as
   `mail_force_reprocess`):

       curl -s -X POST "$BASE/v1/mail/{mail_id}/reprocess"

   The livekernel then runs classify → extract → DFM → deterministic quote →
   verify gate → reply draft. Use the `mail_id` from step 1 verbatim.

3. Inspect the verified result:

   - `GET /v1/mail/{mail_id}/context/hitl` — the HITL panel: `draft` (the
     reply draft; `draft.mode` is `draft_only` and `draft.auto_send` is
     `false` — the reply is a draft, nothing is auto-sent), `quote` (with
     `_source`), `quote_sha16` / `quote_sha16_locked`, `locked` (the
     iron-rule-1 price fingerprint), `can_approve`, `verification_status`.
   - `GET /v1/mail/{mail_id}/context/verification` — `status`
     (PASS / HITL / CLARIFY / BLOCKED), `reasons`, `conflicts`,
     `risk_score`, `gate_history`.
   - `GET /v1/mail/{mail_id}` — the parsed mail itself (`subject`, `from`,
     `body`, `attachments_detail`); processing state is NOT here, use the
     inbox item's `status` / `pending` (ledger state: DONE / HITL / FAILED /
     SKIPPED).
   - `hitl_required` / HITL badge — a human must approve in the workbench
     before any egress.
   - Attachment evidence endpoints when the mail has attachments:
     `GET /v1/mail/{mail_id}/context/geometry` (STEP facts),
     `/context/image` (drawing perception), `/context/rag` (knowledge hits),
     `/context/trace` (deterministic chain).

   If a mail shows `filter: "skip"` (non-RFQ) it is not a quotation
   candidate — say so instead of forcing a quote. If `state` is `FAILED`,
   report the engine error verbatim; never invent a price.

## Output format

Report a short summary per mail: subject, verdict (draft ready / HITL pending
/ blocked / non-RFQ), the deterministic price with its `_source` provenance,
and whether the reply is waiting for human approval. Always attribute the
price to the deterministic engine, never present it as your own computation.

## Iron-rule-1 guarantees (do not violate)

- SMTP / IMAP egress is OFF by default (铁律①): replies are `draft_only`
  with `auto_send:false`. Human approval in the workbench is the only path
  to sending, and this skill never performs egress itself.
- The price is ALWAYS computed by the deterministic Timo kernel and locked by
  sha256; the LLM only routes and drafts text.
- Mailbox credentials live only inside the livekernel (loopback); this skill
  never reads, prints, or transmits them.
- If the engine reports `mock:` or the pipeline FAILED, surface that
  honestly; do not fabricate a quote or a reply.
