# Skill Catalog (P0 inventory)

Generated: 2026-09-21T10:58:47

## Counts

| Status | N |
|--------|---|
| catalog_only | 961 |
| core | 2 |
| pack_candidate | 256 |
| quarantined | 65 |
| total | 1284 |

## Policy

- `core`: livekernel iron-rule skills (dispatcher default)
- `pack_enabled`: only if listed in `config/skill_registry.yaml`
- `catalog_only`: knowledge index, never in TOOL_ALLOWLIST
- `quarantined`: never load

## core (2)

- `orchestrator` — livekernel core skill id
- `orchestrator` — livekernel core skill id

## pack_candidate (256)

- `3dprint-material-price` — capability keywords: quote-pack,knowledge-router
- `agent-fleet-coordinator` — capability keywords: decision-pack
- `agricultural-machinery-quote` — capability keywords: quote-pack
- `aluminum-6061-quote` — capability keywords: quote-pack
- `atx-board-quote` — capability keywords: quote-pack
- `automotive-semi-axle-quote` — capability keywords: quote-pack
- `battery-housing-quote` — capability keywords: quote-pack
- `bom-material-explosion-workflow` — capability keywords: knowledge-router
- `box-200x100x50-quote` — capability keywords: quote-pack
- `cad-agent-qa` — capability keywords: cad-pack
- `cad-drawing-analyzer` — capability keywords: cad-pack
- `cad-parser-batch` — capability keywords: cad-pack
- `cad-parser-dwg` — capability keywords: cad-pack
- `cad-parser-step` — capability keywords: cad-pack
- `cad-parser-stl` — capability keywords: cad-pack
- `cad-perf-agent` — capability keywords: cad-pack
- `cad-ptuning` — capability keywords: cad-pack
- `cad-quote` — capability keywords: quote-pack,cad-pack
- `cad-rag-batch` — capability keywords: cad-pack
- `cad-rag-fix` — capability keywords: cad-pack
- `cad-rag-verify` — capability keywords: cad-pack
- `cad-reverse` — capability keywords: cad-pack
- `cad-step-rag` — capability keywords: cad-pack
- `casting-quote-expert` — capability keywords: quote-pack
- `ceo-decision-cb` — skills_extracted curated
- `cnc-quote-engine-skill` — capability keywords: quote-pack
- `cnc-quote-engineer` — capability keywords: quote-pack
- `cnc-quote-skill` — capability keywords: quote-pack
- `cnc-quote-sync` — capability keywords: quote-pack
- `cnc-quote-system` — capability keywords: quote-pack
- `cnc-quote-workflow` — capability keywords: quote-pack
- `composite-material-quote` — capability keywords: quote-pack,knowledge-router
- `coolant-cost-calculation` — capability keywords: quote-pack
- `cost-batch-economy` — capability keywords: quote-pack
- `cost-breakdown` — capability keywords: quote-pack
- `cost-machining-time` — capability keywords: quote-pack
- `cost-material-selection` — capability keywords: quote-pack,knowledge-router
- `cost-overhead-analysis` — capability keywords: quote-pack
- `cost-risk-premium` — capability keywords: quote-pack
- `cost-scrap-analysis` — capability keywords: quote-pack
- `cost-supplier-quote-analysis` — capability keywords: quote-pack
- `cost-surface-treatment-cost` — capability keywords: quote-pack
- `cover-plate-quote` — capability keywords: quote-pack
- `dc-bus-insulation-quote` — capability keywords: quote-pack
- `dfm-analysis` — capability keywords: knowledge-router
- `dfm-manufacturing` — capability keywords: knowledge-router
- `drone-frame-quote` — capability keywords: quote-pack
- `dxf-engineer-draw` — skills_extracted curated
- `edm-wire-cut-quote` — capability keywords: quote-pack
- `electronic-enclosure-quote` — capability keywords: quote-pack
- `electroplating-quote` — capability keywords: quote-pack
- `email-quote` — capability keywords: quote-pack
- `encoder-mount-quote` — capability keywords: quote-pack
- `ev-charging-gun-quote` — capability keywords: quote-pack
- `factory-equipment-inventory` — capability keywords: cad-pack
- `factory-safety-detection-skill` — capability keywords: cad-pack
- `fitness-equipment-quote` — capability keywords: quote-pack
- `fixture-design-quote` — capability keywords: quote-pack
- `flange-100x50-quote` — capability keywords: quote-pack
- `forging-quote-expert` — capability keywords: quote-pack
- `gb-t-12600-quote` — capability keywords: quote-pack
- `gb-t-3087-quote` — capability keywords: quote-pack
- `gb-t-3854-quote` — capability keywords: quote-pack
- `grinding-quote-expert` — capability keywords: quote-pack
- `handle-grip-quote` — capability keywords: quote-pack
- `hard-anodizing-quote` — capability keywords: quote-pack
- `heat-treatment-quote` — capability keywords: quote-pack
- `hexagram-orchestrator` — capability keywords: decision-pack
- `hydropower-equipment-quote` — capability keywords: quote-pack
- `injection-molding-quote` — capability keywords: quote-pack
- `inner-cavity-quote` — capability keywords: quote-pack
- `knowledge-querier` — skills_extracted curated
- `laser-cutting-quote` — capability keywords: quote-pack
- `limit-sleeve-quote` — capability keywords: quote-pack
- `lite-orchestrator` — capability keywords: decision-pack
- `logistics-handcart-quote` — capability keywords: quote-pack
- `manufacturing-cost-breakdown-workflow` — capability keywords: quote-pack
- `material-(021)-56085857` — capability keywords: knowledge-router
- `material-+61-(40)-8131-927,-+61-(48)-82` — capability keywords: knowledge-router
- `material---E0-进HBM，20normal` — capability keywords: knowledge-router
- … +176 more (see skill_catalog/index.json)

## catalog_only (961)

- `1688-operations` — default catalog (not hot-dispatched)
- `304-stainless-deep-knowledge` — knowledge/dataset slice
- `3d-printing-prototype` — default catalog (not hot-dispatched)
- `3dprint-new-material` — default catalog (not hot-dispatched)
- `3dprint-quality-management` — default catalog (not hot-dispatched)
- `3dprint-sales-tech` — default catalog (not hot-dispatched)
- `6061-aluminum-deep-knowledge` — knowledge/dataset slice
- `acrylic-plexiglas-knowledge` — knowledge/dataset slice
- `aero-part-knowledge` — knowledge/dataset slice
- `aerospace-part` — default catalog (not hot-dispatched)
- `aerospace-part-manufacturing` — knowledge/dataset slice
- `agent-generator` — default catalog (not hot-dispatched)
- `agent-management` — default catalog (not hot-dispatched)
- `agent-platform-v3` — default catalog (not hot-dispatched)
- `agent-platform-v3-robust` — default catalog (not hot-dispatched)
- `agent-self-review` — default catalog (not hot-dispatched)
- `agent-workflow` — default catalog (not hot-dispatched)
- `agentcraft` — default catalog (not hot-dispatched)
- `agricultural-machinery-knowledge` — knowledge/dataset slice
- `agricultural-part-knowledge` — knowledge/dataset slice
- `ahuang-truth-skill` — default catalog (not hot-dispatched)
- `ai-business-case` — default catalog (not hot-dispatched)
- `ai-framework-knowledge` — knowledge/dataset slice
- `ai-job-hunting-agent-skill` — default catalog (not hot-dispatched)
- `ai-knowledge-base-generator-skill` — knowledge/dataset slice
- `ai-model-subscription-analyzer-skill` — default catalog (not hot-dispatched)
- `ai-procurement-supplychain` — default catalog (not hot-dispatched)
- `ai4s-presentation-generator-skill` — default catalog (not hot-dispatched)
- `aipc-setup` — default catalog (not hot-dispatched)
- `alloy-steel-material-knowledge` — knowledge/dataset slice
- `alloy-steel-part-quote` — knowledge/dataset slice
- `aluminum-6061-t6-knowledge` — knowledge/dataset slice
- `aluminum-7075-knowledge` — knowledge/dataset slice
- `aluminum-7075-t6-knowledge` — knowledge/dataset slice
- `aluminum-alloy-material-knowledge` — knowledge/dataset slice
- `amd-adaptive-model` — default catalog (not hot-dispatched)
- `anodized-part` — default catalog (not hot-dispatched)
- `anodizing-knowledge` — knowledge/dataset slice
- `anodizing-surface-finish-knowledge` — knowledge/dataset slice
- `anodizing-training-expert` — default catalog (not hot-dispatched)
- `anomaly-detector` — default catalog (not hot-dispatched)
- `aoran-ppt-skill` — default catalog (not hot-dispatched)
- `ascend-dev-helper-skill` — default catalog (not hot-dispatched)
- `auto-reverse-draw` — default catalog (not hot-dispatched)
- `automation-robot-knowledge` — knowledge/dataset slice
- `automation-robot-part` — default catalog (not hot-dispatched)
- `automotive-part` — default catalog (not hot-dispatched)
- `automotive-part-knowledge` — knowledge/dataset slice
- `automotive-part-manufacturing` — knowledge/dataset slice
- `autonomous-ai-agents` — default catalog (not hot-dispatched)
- `base-part` — default catalog (not hot-dispatched)
- `base-pedestal-knowledge` — knowledge/dataset slice
- `base-plate-structure-knowledge` — knowledge/dataset slice
- `batch-processing-1` — default catalog (not hot-dispatched)
- `batch-processing-2` — default catalog (not hot-dispatched)
- `batch-processing-3` — default catalog (not hot-dispatched)
- `batch-processing-4` — default catalog (not hot-dispatched)
- `batch-processing-5` — default catalog (not hot-dispatched)
- `batch-quantity-discount` — default catalog (not hot-dispatched)
- `battery-part` — default catalog (not hot-dispatched)
- `bear-notes` — default catalog (not hot-dispatched)
- `bearing-housing-knowledge` — knowledge/dataset slice
- `bearing-part` — default catalog (not hot-dispatched)
- `beijing-competition` — default catalog (not hot-dispatched)
- `bicycle-part-quote` — knowledge/dataset slice
- `block-part` — default catalog (not hot-dispatched)
- `block-part-knowledge` — knowledge/dataset slice
- `bolt-fastener` — default catalog (not hot-dispatched)
- `bolt-fastener-knowledge` — knowledge/dataset slice
- `bom-extraction` — default catalog (not hot-dispatched)
- `box-housing-knowledge` — knowledge/dataset slice
- `bracket-part` — default catalog (not hot-dispatched)
- `bracket-part-knowledge` — knowledge/dataset slice
- `bushing-part-knowledge` — knowledge/dataset slice
- `bushing-sleeve-knowledge` — knowledge/dataset slice
- `business-contract-process` — default catalog (not hot-dispatched)
- `cad-rag-knowledge` — knowledge/dataset slice
- `cam-mechanism-knowledge` — knowledge/dataset slice
- `camsnap` — default catalog (not hot-dispatched)
- `canvas` — default catalog (not hot-dispatched)
- … +881 more (see skill_catalog/index.json)

## quarantined (65)

- `1password` — noise/irrelevant pattern
- `apple` — noise/irrelevant pattern
- `apple-notes` — noise/irrelevant pattern
- `apple-reminders` — noise/irrelevant pattern
- `blogwatcher` — noise/irrelevant pattern
- `blucli` — noise/irrelevant pattern
- `bluebubbles` — noise/irrelevant pattern
- `discord` — noise/irrelevant pattern
- `gifgrep` — noise/irrelevant pattern
- `github` — noise/irrelevant pattern
- `gog` — noise/irrelevant pattern
- `goplaces` — noise/irrelevant pattern
- `himalaya` — noise/irrelevant pattern
- `hospital-booking` — noise/irrelevant pattern
- `material-$3432.1997万人民币,-$16373.6697万人民` — noise/irrelevant pattern
- `material-$399.221748万人民币,-$317.5万人民币,-未` — noise/irrelevant pattern
- `material-'Dim1'-和-'Dim2'-分别代表不同的测量维度（宽度` — noise/irrelevant pattern
- `notion` — noise/irrelevant pattern
- `nvidia-skills-repo` — no SKILL.md
- `obsidian` — noise/irrelevant pattern
- `output` — no SKILL.md
- `part-【数量1-TPU-蓝色】头部模型` — noise/irrelevant pattern
- `part-【数量2-TPU-灰色】头部模型` — noise/irrelevant pattern
- `peekaboo` — noise/irrelevant pattern
- `qq-notifier` — noise/irrelevant pattern
- `smart-home` — noise/irrelevant pattern
- `sonoscli` — noise/irrelevant pattern
- `spotify-player` — noise/irrelevant pattern
- `suntime-a-shares-screen` — noise/irrelevant pattern
- `suntime-amplitude-forecast` — noise/irrelevant pattern
- `suntime-catalyst-calendar` — noise/irrelevant pattern
- `suntime-catalyst-research` — noise/irrelevant pattern
- `suntime-competitive-analysis` — noise/irrelevant pattern
- `suntime-copper-price-analysis` — noise/irrelevant pattern
- `suntime-ddm-valuation` — noise/irrelevant pattern
- `suntime-docx` — noise/irrelevant pattern
- `suntime-etf-screen` — noise/irrelevant pattern
- `suntime-go-goal-investment` — noise/irrelevant pattern
- `suntime-gold-price-analysis` — noise/irrelevant pattern
- `suntime-gold-silver-ratio` — noise/irrelevant pattern
- `suntime-idea-generation` — noise/irrelevant pattern
- `suntime-key-variable-analysis` — noise/irrelevant pattern
- `suntime-ma-rumor-research` — noise/irrelevant pattern
- `suntime-management-analysis` — noise/irrelevant pattern
- `suntime-mcp-cli` — noise/irrelevant pattern
- `suntime-pdf` — noise/irrelevant pattern
- `suntime-private-fund-data` — noise/irrelevant pattern
- `suntime-public-fund-data` — noise/irrelevant pattern
- `suntime-stock-performance-appraisal` — noise/irrelevant pattern
- `suntime-stock-technical-analysis` — noise/irrelevant pattern
- `suntime-stock-watchlist-manager` — noise/irrelevant pattern
- `suntime-treasure-strategy` — noise/irrelevant pattern
- `suntime-undervalued-investing` — noise/irrelevant pattern
- `suntime-valuation-band-chart` — noise/irrelevant pattern
- `suntime-valuation-comparison` — noise/irrelevant pattern
- `suntime-xlsx` — noise/irrelevant pattern
- `tcm-prescriber` — noise/irrelevant pattern
- `things-mac` — noise/irrelevant pattern
- `tmux` — noise/irrelevant pattern
- `travel-planner` — noise/irrelevant pattern
- `travel-planner-v2` — noise/irrelevant pattern
- `travel-pro-v3` — noise/irrelevant pattern
- `nl2cad` — no SKILL.md
- `opc-dcs-monitor` — no SKILL.md
- `unified-quote` — no SKILL.md
