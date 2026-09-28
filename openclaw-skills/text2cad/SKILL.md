---
name: text2cad
description: |
  Use when the user asks to draw / generate / model a part from text or
  parameters ("draw me a flange 60mm outer dia, 10mm thick, 4 bolt holes",
  "生成一个 L 支架 STEP", "画个轴套"). This skill is a thin bridge: it forwards
  the shape + parameters to the local union-export livekernel, whose
  deterministic cadquery kernel builds the geometry and returns STEP/STL files
  with a real sha256_16 file fingerprint. Iron-rule: the LLM never invents
  coordinates — geometry is produced only by the deterministic kernel. Pricing
  is out of scope here: a quote is ALWAYS computed by the deterministic Timo
  engine (use the cnc-quote bridge), never by this skill and never by the LLM.
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
    - cad
    - step
    - deterministic
    - bridge
---

# text2cad

Thin bridge from OpenClaw to the local **union-export livekernel** (v7.1.0)
for text/parameter → CAD generation (nl2cad-class capability). The livekernel
owns the deterministic geometry kernel (cadquery, 5 shape families:
flange / l_bracket / bushing / plate / pipe). This skill does NOT build
geometry — it forwards the request and relays the verified result.

## When to use

- The user wants a drawing / model / STEP / STL file from a text description.
- The user gives dimensions (outer diameter, thickness, hole count, wall, …)
  and asks for a part file.
- The user asks to regenerate a part with changed dimensions.

Do NOT use this skill to write coordinates, mesh data, or STEP text yourself —
iron-rule: geometry is produced only by the deterministic kernel. Do NOT use
this skill to price a part — quoting belongs to the Timo engine (cnc-quote
bridge); this skill never emits a price.

## Prerequisites

- livekernel reachable at `${UEA_LIVEKERNEL_URL:-http://127.0.0.1:8888}`.
- `curl` available.

## Instructions

Set the base URL once:

    BASE="${UEA_LIVEKERNEL_URL:-http://127.0.0.1:8888}"

1. List the available shape families and their parameters:

       curl -s "$BASE/v1/cad/shapes"

   The response contains `shapes` (flange / l_bracket / bushing / plate /
   pipe, each with its parameter spec: name, type, min/max, required) and
   `formats` (step, stl). Pick the family that matches the request and map the
   user's dimensions onto its parameters (units: mm).

2. Forward the drawing request:

       curl -s -X POST "$BASE/v1/cad/text2step" \
         -H "Content-Type: application/json" \
         -d '{"shape":"flange",
              "params":{"outer_dia":60,"thickness":10,"bore_dia":20,
                        "bolt_circle_dia":44,"hole_count":4,"hole_dia":6},
              "formats":["step","stl"],"name":"flange-d60"}'

   `name` is optional (default: parameter-hash stem); it must match
   `[A-Za-z0-9_-]+` — an unsafe name returns `invalid-name`.

3. Relay the result:

   - `ok:true` → `files.step` / `files.stl` (paths on the node, under
     `data/cad`), `geometry.bbox_mm` / `volume_mm3` / `volume_cm3` (the
     deterministic facts), `params` (the normalized parameters),
     `sha256_16` (the real file-byte hash of the STEP — never restate it from
     memory), `iron_rule` (expect `deterministic`), `_source` (expect
     `services.text2cad`; on a dev machine without cadquery expect the honest
     `MOCK:cadquery-unavailable`).
   - `ok:false` with `error:"missing-params"` → read the `missing` list and ask
     the user for those dimensions. The kernel never guesses defaults — a
     drawing made from invented sizes is worse than no drawing.
   - `ok:false` with `error:"invalid-params"` → the `invalid` map says which
     parameter is non-numeric or out of range; report it verbatim and ask.
   - `ok:false` with `error:"unknown-shape"` → use the `available` list.
   - `ok:false` with `error:"geometry-failed"` → the geometry is illegal
     (e.g. pipe wall thicker than half the outer diameter); report the
     `detail` verbatim.
   - `ok:false` with `error:"cadquery-unavailable"` → the kernel is down on
     this machine; tell the user drawing is unavailable, never fabricate a
     file or a geometry.

## Iron-rule guarantees (do not violate)

- Geometry is ALWAYS produced by the deterministic cadquery kernel and locked
  by the real file hash `sha256_16`. The LLM never invents coordinates.
- Missing required parameters never get silent defaults — they surface as
  `missing-params` for human slot-filling.
- When cadquery is unavailable the bridge degrades honestly
  (`cadquery-unavailable`, zero files written); no fabricated STEP.
- This skill draws only; pricing stays with the deterministic Timo engine.
  Outbound email is never sent from this skill.
