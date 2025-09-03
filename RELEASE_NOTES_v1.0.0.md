# v1.0.0 — Publish‑ready release

Tag: v1.0.0
Date: 2025‑09‑02

Highlights

- Dynamic DEV/PROD spider configuration at runtime
  - `scrap.py` passes mode into the spider; per‑mode Scrapy settings are applied dynamically.
  - DEV parses local fixtures in `samples/` (no browser). PROD uses Playwright for live pages.
- Embedding output simplified to a single normalized JSON graph
  - Output: `output_embedding/embedding.json` (agent’s default input).
  - JSONL output removed to reduce complexity and repo noise.
- Page metadata preserved in embeddings
  - Each document’s `metadata.page_metadata` includes title, description, canonical, language, OpenGraph, and Twitter metadata for traceability.
- Make target for embeddings from latest crawl
  - `make embed-latest` builds `output_embedding/embedding.json` from the newest `output_*.json`.
- CLI ergonomics and docs
  - `--save-html/--no-save-html` boolean flag in `scrap.py`.
  - README updated with DEV vs PROD guide, output format, and commands.
- Repo hygiene
  - Removed tracked build artifacts, caches, and notebooks.
  - Preserved `samples/` and example outputs in `output_embedding/`.

Breaking changes

- JSONL output removed from embedding step
  - Flags `--keep-jsonl` / `--skip-jsonL` removed.
  - The file `embeddings/chevy_embeddings.jsonl` is no longer produced.
- Removed JSONL record schema file
  - `docs/embedding_record.schema.json` deleted.
- Makefile commands standardized to `python3`.

Getting started

- DEV crawl: `python3 scrap.py --dev --log-level INFO`
- PROD crawl (single page): `python3 scrap.py --prod --url <vehicle-url> --log-level INFO`
- Build graph from latest crawl: `make embed-latest`
- Run agent: `python3 agent.py`

