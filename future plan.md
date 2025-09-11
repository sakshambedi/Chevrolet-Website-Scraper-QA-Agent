# Embedding & Personalization Platform – Future Plan Roadmap

## 1. Executive Summary

You have a rich, hierarchical dataset (models → trims → prices → sections → disclosures → assets) but it is not yet operationalized for high‑quality semantic retrieval or outbound personalization. Core gaps: duplication, missing specs, weak disclosure linkage, lack of tags/persona metadata, absence of embeddings, and no evaluation harness. This roadmap establishes a phased plan to evolve into a robust Retrieval Augmented Personalization (RAP) system powering email / SMS / phone outreach with dynamic pricing, media, and intent alignment.

## 2. Current State (Issue Inventory)

1. Not an embedding file (no vectors).
2. Duplicate sentences / repeated bodies (e.g. towing paragraph).
3. Truncated / malformed marketing phrases (“Class- Duramax … Exclusive \*”).
4. Asterisk markers not contextually resolved to disclosure text.
5. Prices are strings with commas (non‑numeric for filtering / analytics).
6. Media alt text inconsistent; some low semantic value (“w”, filenames).
7. Missing high-value numeric specs (towing, payload, hp, torque, bed length, drivetrain matrix, fuel economy).
8. Single locale (en-CA) — no fr-CA or localization strategy.
9. No taxonomy for buyer personas, use cases, or feature domains.
10. Disclosures not normalized per in-text reference (compliance risk).
11. No chunking strategy; content granularity suboptimal for embeddings.
12. No evaluation framework (queries, judgments, metrics).
13. No retrieval scoring or reranking layer.
14. No interaction telemetry loop (clicks, opens, conversions → embedding refinement).
15. No governance around updates / last_updated versioning.
16. No risk mitigation for hallucination or outdated price quoting.
17. Pricing lacks effective date, MSRP vs “as_shown” breakdown, no historical diff.
18. No standardized outbound template variable schema.

## 3. Future State Vision (12–18 Weeks)

A production-grade RAP stack where:

- Clean, deduplicated, semantically tagged chunks are stored in a vector DB with hybrid (semantic + metadata) search.
- Persona- & intent-driven retrieval personalizes outbound messages (email/SMS) with localized, spec-complete, disclosure-compliant content.
- Automated enrichment (spec ingestion + vision captioning) feeds continuous improvements.
- Measurable relevance (nDCG, MRR), personalization lift (CTR, reply rate), and conversion metrics (test drive bookings, inquiries).
- Governance: versioned content, disclosure binding, price effective dates, and locale coverage.

## 4. Guiding Principles

- Compliance First (disclosures always traceable).
- Deterministic Fallbacks (missing region → default).
- Observability & Metrics Early (don’t wait for “perfect” content).
- Progressive Enrichment (ship cleaned core before deep spec expansion).
- Reusability (shared chunk schema across outbound channels).
- Measured Model Upgrades (justify moving to larger embedding model with metric deltas).

## 5. Phased Roadmap

### Phase 0 (Week 0–1): Stabilization & Data Hygiene

Goals: Clean text, normalize prices, remove duplication.
Key Tasks:

- Script to parse and normalize price strings → integer fields + `price_display`.
- Sentence-level hash dedupe for sections/features.
- Identify truncated phrases; build a manual correction map.
- Add `last_updated` timestamps; unify ISO date format.
  Deliverables:
- `clean_dataset.json`
- Dedup report (before/after counts).
  Success Metric:
- Duplicate sentence ratio < 1%.
  Dependencies: None.

### Phase 1 (Week 1–3): Schema & Chunking Foundation

Goals: Define chunk schema + tag framework.
Key Tasks:

- Implement chunk generator (model summary, per trim, per section, per disclosure, media groups).
- Add metadata: object_type, locale, model_id, trim_id, tags[], disclosure_refs[], price_summary{}.
- Introduce derived fields (price_range_per_trim, delta_vs_base).
- Manual first-pass tag assignment (persona, use_case, powertrain, capability).
  Deliverables:
- `chunks_v1.jsonl`
- Tag taxonomy doc.
  Success Metrics:
- 100% of trims & sections represented in chunk set.
- Avg chunk token length within 300–800 target.

### Phase 2 (Week 3–5): Embedding & Retrieval MVP

Goals: Standing vector store with hybrid querying.
Key Tasks:

- Choose vector DB (pgvector for simplicity or Pinecone for scale).
- Generate embeddings with `text-embedding-3-small`.
- Implement hybrid search (ANN + metadata filters).
- Build query API (search endpoint with filters).
- Seed test queries + manual relevance judgments.
  Deliverables:
- Embedding pipeline script.
- Retrieval service (REST or internal module).
- Evaluation harness (queries.json, judgments.csv).
  Success Metrics:
- MRR ≥ 0.7 on seed set.
- Median query latency < 300 ms (excluding network).

### Phase 3 (Week 5–7): Enrichment & Compliance

Goals: Add disclosure resolution, media curation, improved alt.
Key Tasks:

- Inline disclosure bracket references or append structured block.
- Group assets into semantic media clusters (e.g., off-road, interior tech).
- Automated alt regeneration (vision caption model) for weak entries.
- Add initial spec enrichment placeholders (null-safe fields).
  Deliverables:
- `chunks_v2.jsonl` with enriched media & disclosures.
- Disclosure resolution map.
  Success Metrics:
- 0 unresolved `*` markers.
- 90%+ media entries have descriptive alt ≥ 5 meaningful tokens.

### Phase 4 (Week 7–10): Personalization Layer

Goals: Dynamic outbound content assembly.
Key Tasks:

- Templating engine (email, SMS, phone-call briefing).
- Persona resolution logic (from CRM signals: budget band, use_case, region).
- Ranking pipeline incorporating persona weight + embedding score + price fit.
- A/B test harness for subject lines.
  Deliverables:
- Personalization microservice.
- Template variable contract (JSON schema).
  Success Metrics:
- Lift in click/reply rate vs control (≥ +10%).
- Correct region price usage > 99%.

### Phase 5 (Week 10–13): Spec & Localization Expansion

Goals: Add real specs + fr-CA locale.
Key Tasks:

- Ingest structured spec feeds (towing payload tables).
- Generate bilingual content (MT + human QA pipeline).
- Add locale negotiation in retrieval.
  Deliverables:
- `specs_enriched.json`.
- `chunks_v3_fr-CA.jsonl`.
  Success Metrics:
- Coverage of core specs for ≥ 90% trims.
- nDCG drop across locales < 3%.

### Phase 6 (Week 13–16): Intelligence & Optimization

Goals: Close feedback loop.
Key Tasks:

- Log retrieval context IDs into outbound messages.
- Capture downstream interactions (open, click, reply, booked).
- Train lightweight re-ranker (cross-encoder) if uplift justifies cost.
  Deliverables:
- Interaction telemetry store.
- Re-ranker performance report.
  Success Metrics:
- Re-ranker improves MRR ≥ +5% vs baseline.
- Automated stale-content alerts (if last_updated > threshold).

### Phase 7 (Week 16–18+): Scale & Model Evaluation

Goals: Evaluate move to `text-embedding-3-large`.
Key Tasks:

- Sample 50–100 complex queries (nuanced multi-feature intent).
- Compare nDCG@5 and cost-per-1k chunks.
- Decision doc on model upgrade.
  Success Metrics:
- Only upgrade if quality gain ≥ 5–7% with acceptable ROI.

## 6. Backlog (Condensed Task Table)

- P0: Price normalizer, duplicate remover, truncated phrase validator.
- P1: Chunk schema, tag dictionary, derived price diffs.
- P2: Embedding generation, vector index, evaluation harness.
- P3: Disclosure linker, media alt enhancer, spec placeholder fields.
- P4: Persona inference rules, template API, hybrid ranking.
- P5: Spec ingestion ETL, locale expansion, bilingual QA.
- P6: Telemetry loop, re-ranker candidate, auto refresh pipeline.
- P7: Embedding model A/B and cost-benefit analysis.

## 7. Data Model Evolution (Additions Over Time)

Phase 1: base fields + tags + price_summary
Phase 3: disclosure_inlined_text, media_group tags
Phase 5: specs (towing_capacity_max_kg, payload_max_kg, engine_options[], drivetrain_options[], bed_length_options, warranty_summary)
Phase 6: interaction_stats (views, clicks, conversions), persona_weights
Phase 7: embedding_model_version, evaluation_metrics snapshot

## 8. Technical Architecture (High Level)

Components:

- Ingestion & Cleaning Worker
- Chunk Builder & Tagger
- Embedding Pipeline
- Vector Store (pgvector or Pinecone) + Postgres metadata
- Retrieval API (semantic + metadata filters + optional rerank)
- Personalization Service (template engine + content selection)
- Telemetry Collector (Kafka or lightweight queue)
- Analytics & Evaluation Dashboard
  Security/Compliance:
- Versioned content records
- Disclosure integrity check on publish
- Locale + region gating for price correctness

## 9. Embedding Strategy

- Default: `text-embedding-3-small`
- Retry queue (backoff) for transient failures
- Batch size tuning for throughput
- Vector dimension housekeeping & index vacuum schedule
- Upgrade evaluation script for `3-large` (Phase 7)

## 10. Evaluation & Metrics

Retrieval Quality:

- MRR, nDCG@5, hit@3
  Outbound Performance:
- Open Rate, CTR, Reply Rate, Test Drive Conversion
  Data Hygiene:
- Duplicate sentence ratio
- Stale content ratio (content > N days old without refresh)
  Model Drift:
- Relevance decay vs baseline judgments

## 11. Risks & Mitigations

| Risk                                          | Impact                | Mitigation                                |
| --------------------------------------------- | --------------------- | ----------------------------------------- |
| Duplicate residuals reduce embedding clarity  | Lower relevance       | Hash-based dedupe + QA sample             |
| Missing specs cause weak personalization      | Lower conversion      | Progressive spec ingestion + placeholders |
| Disclosure mismatch                           | Compliance exposure   | Pre-publish validator; test suite         |
| Regional price misuse                         | Customer distrust     | Region fallback logic + unit tests        |
| Overly long chunks degrade semantic precision | Missed matches        | Length guard + token analyzer             |
| Model upgrade cost overrun                    | Budget blowout        | A/B with strict ROI threshold             |
| Alt text poor for accessibility & search      | Lower semantic recall | Vision caption batch improvement          |

## 12. Operational Playbooks

- Content Refresh Cycle: weekly diff scan → regenerate embeddings only for changed chunks (checksum compare).
- Incident Response: if disclosure mismatch found → disable affected chunks via metadata flag.
- Locale Rollout: fr-CA behind feature flag; measure parity metrics.

## 13. Tooling & Automation

Scripts to build:

- `normalize_prices.py`
- `dedupe_sentences.py`
- `build_chunks.py`
- `generate_embeddings.py`
- `evaluate_retrieval.py`
- `enrich_media_alt.py`
- `ingest_specs.py`
- `rerank_eval.py`

## 14. Timeline (Indicative)

- Week 1: Phase 0 complete
- Week 3: Phase 1 & 50% Phase 2
- Week 5: Retrieval MVP live
- Week 7: Enrichment & compliance stable
- Week 10: Personalization live A/B
- Week 13: Specs + fr-CA
- Week 16: Telemetry + optimization
- Week 18: Embedding model evaluation decision

## 15. Success Criteria (Exit Conditions)

- Retrieval MRR ≥ 0.8
- Persona-targeted emails show ≥10% CTR lift vs generic
- 0 unresolved disclosure markers
- 95%+ outbound messages show correct regional pricing
- <5% chunks flagged as stale (beyond SLA)

## 16. Immediate Next 7-Day Sprint Plan

Stories:

1. Build price normalizer (includes numeric + display fields).
2. Implement sentence deduper (report + baseline metrics).
3. Draft chunk schema & produce first 50 sample chunks.
4. Manual tag taxonomy v0 (at least 30 tags across personas, capabilities, segments).
5. Set up pgvector extension & metadata tables.
   Definition of Done:

- Sample query against first chunk set returns sensible results.
- Dedupe reduces raw section token count by ≥15%.

## 17. Decision Log (to Maintain Going Forward)

- Chosen vector DB & rationale
- Embedding model version & evaluation date
- Tag taxonomy major revisions
- Disclosure handling policy changes
- Locale enablement dates

## 18. Open Questions

- Source for authoritative spec ingestion (OEM API? Scrape? Manual feed?)
- Frequency of price updates & effective date retention
- CRM integration points for persona inference
- Governance for bilingual copy QA (human vs automated thresholds)

## 19. Appendices

A. Original Gap Summary (preserved for traceability)
B. Example Queries & Expected Chunk Targets
C. Sample Template Variable Schema (future)
