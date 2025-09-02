# Chevrolet Silverado 1500 Semantic Scraper & Q&A Agent

## Quickstart (End-to-End)

1) Configure OpenAI and basics

- Run `python setup.py` and follow prompts for `OPENAI_API_KEY` and optional `OPENAI_PROJECT`.
- Or create `.env` from `.env.example` and set:
  - `OPENAI_API_KEY=...`
  - `OPENAI_PROJECT=...` (recommended when using admin/org keys)
  - `EMBED_MODEL=text-embedding-3-small`
  - `CHAT_MODEL=gpt-4o-mini`
  - `GRAPH_PATH=output_embedding/embedding.json`

2) Scrape a website → semantic JSON

- DEV (uses local HTML fixture):
  - `python scrap.py --dev --log-level INFO`
  - Produces `output_DEV.json`.
- PROD (fetches live site, enables Playwright):
  - `python scrap.py --prod --log-level INFO`
  - Produces `output_PROD.json`.
- Optional multi-page crawl:
  - Discover vehicle URLs: `python scrap.py --prod --discover-vehicles --category trucks`
  - Or pass a file: `python scrap.py --prod --urls-file path/to/urls.json`

3) Build embedding artifacts

- Option A: JSONL + graph
  - `python -m embedding.chevy_embed --input output_DEV.json --output embeddings/chevy_embeddings.jsonl --normalized-json output_embedding/embedding.json`
  - Artifacts:
    - `embeddings/chevy_embeddings.jsonl` (id, text, metadata, embedding=None)
    - `output_embedding/embedding.json` (normalized graph of models/prices/sections/assets/disclosures/awards)
- Option B: Graph only (skip JSONL)
  - `python -m embedding.chevy_embed --input output_DEV.json --skip-jsonl --normalized-json output_embedding/embedding.json`
  - Artifact:
    - `output_embedding/embedding.json`

4) Run the Q&A agent

- `python agent.py`
- The agent indexes `GRAPH_PATH`. If unset, it prefers `output_embedding/embedding.json`, falling back to `embedding.json`.

Notes

- Install dependencies: `pip install -r requirements.txt` (and `pip install openai python-dotenv rich` if needed).
- For PROD scraping with Playwright: `pip install scrapy-playwright` then `python -m playwright install chromium`.

A Scrapy-based spider that converts selected parts of chevrolet.ca's Silverado 1500 page into a compact, semantically meaningful JSON structure. It supports two modes: DEV (offline, deterministic, fixture-based) and PROD (live site, optionally browser-rendered). It also injects official disclosure content when present on the page.

The project also includes a Q&A Agent that uses OpenAI embeddings and chat models to answer questions about the Chevrolet Silverado based on the scraped data.

This README covers how to run the project, the high-level architecture, and the key design choices.

## Quick Start

- Create a virtualenv and install dependencies:
  - `python -m venv .venv && source .venv/bin/activate`
  - `pip install -r requirements.txt`
- Install Playwright browsers for PROD rendering (chromium):
  - `python -m playwright install chromium`
- Ensure DEV fixtures exist:
  - `samples/silverado1500.html`
  - `samples/disclosurespurejson.json`
- Run in DEV (offline):
  - `python main.py --dev --log-level INFO`
- Run in PROD (live):
  - `DEV=false python main.py --prod --log-level INFO --save-html True`

Notes:

- Output is written to `output_DEV.json` or `output_PROD.json` (root) via Scrapy FEEDS.
- `--save-html` only applies in PROD and saves a timestamped HTML to `samples/`.

## Setup

- Python: 3.10+ recommended
- Dependencies: see `requirements.txt` (Scrapy, Playwright, scrapy-playwright, Click, python-dotenv, rich)
- Playwright browsers: `python -m playwright install chromium`
- Env var for mode: `.env` can set `DEV=TRUE` or `DEV=False`
- Make targets: `make run` (defaults to DEV), `make rund` (DEV with INFO logs)

## Project Layout

- `main.py` — CLI entrypoint; configures logging, sets DEV/PROD, loads disclosures, runs the spider
- `scrapper/scrapper.py` — Base `Scrapper` class (mode-aware settings, optional Playwright, FEEDS setup, HTML saver, metadata extraction)
- `scrapper/chevy_scrapper.py` — `ChevyScapper` spider (DOM selection + semantic JSON transformation)
- `scrapper/disclosure.py` — `DisclosureScrapper` and `load_disclosures` utility (fetch/parse disclosures; optional CLI to refresh `samples`)
- `samples/` — DEV fixtures: `silverado1500.html`, `disclosurespurejson.json` (+ optional split sections)
- `utils/logger.py` — Minimal, configurable logger
- `embedding/embedding.py` — Embedding orchestrator (`BaseEmbedder`, `EmbeddingConfig`, `Record`)
- `embedding/gm_base.py` — Shared GM embedder logic (prices/sections/assets/links/related models/awards)
- `embedding/chevy_embed.py` — Chevy-specific embedder subclass (trims, CLI)

## Running

DEV (offline, deterministic)

- Ensures no network usage; reads `samples/silverado1500.html` and `samples/disclosurespurejson.json`.
- Command: `python main.py --dev --log-level INFO`

PROD (live site)

- Fetches the live page `https://www.chevrolet.ca/en/trucks/silverado-1500` and live disclosures endpoint.
- Requires Playwright browsers installed. Optionally saves raw HTML for later DEV use.
- Command: `DEV=false python main.py --prod --log-level INFO --save-html True`

CLI options (from `main.py`)

- `--dev/--prod` (default `--dev`): Select mode
- `--log-level, -l`: `DEBUG` | `INFO` | `WARNING` | `ERROR` | `CRITICAL` (default `CRITICAL`)
- `--save-html, -s`: `True|False` (effective in PROD only)

Logging

- The CLI `--log-level` sets both the project logger (`utils/logger.py`) and Scrapy's `LOG_LEVEL` so all log output uses a consistent level.

Where output goes

- `scrapper/scrapper.py` sets FEEDS to write JSON to `output_DEV.json` or `output_PROD.json` in the project root.

Embedding output

- Run: `python -m embedding.chevy_embed --input output_DEV.json --output embeddings/chevy_embeddings.jsonl`
- Also writes `embedding.json` (normalized graph: models/prices/disclosures/assets/sections/awards)

Mode selection caveat

- The base `Scrapper` reads `DEV` from the environment at import-time to configure FEEDS and Playwright.
- To force PROD end-to-end, set the env var when launching: `DEV=false python main.py --prod ...` (or set `DEV=False` in `.env`).
- The CLI flag controls runtime behavior and disclosure loading; the env var ensures Playwright and FEEDS are configured consistently.

## Architecture

- Orchestrator (CLI): `main.py`
  - Configures logs (via `utils/logger.py`)
  - Decides mode (DEV/PROD) and sets `os.environ["DEV"]`
  - Loads disclosures via `load_disclosures(dev_mode=...)`
  - Runs Scrapy `CrawlerProcess` with `ChevyScapper(disclosures=..., save_html=...)`

- Base Spider: `scrapper/scrapper.py` (`Scrapper`)
  - Mode-aware Scrapy `custom_settings` (FEEDS, robots, UA, Playwright handler in PROD)
  - `start_urls` set by mode (local fixture vs live URL)
  - `save_response_html(...)` to persist raw HTML (PROD only)
  - `extract_metadata(...)` collects title/description/canonical/OG/Twitter/meta

- Domain Spider: `scrapper/chevy_scrapper.py` (`ChevyScapper`)
  - Selects three major regions via XPath: navbar, main body, footer
  - DFS over the DOM builds a semantic JSON tree
  - Specialized serializers for common and GM-specific elements (links, buttons, images, lists, tables, `gb-*` components, SVG paths)
  - Disclosure integration: `<gb-disclosure data-disclosure-id>` resolved via the loaded mapping

- Disclosures: `scrapper/disclosure.py`
  - `load_disclosures(...)` loads from `samples` in DEV or remote endpoint in PROD, cleaning JSON and stripping basic tags (`<p>`, `'<sup>'`) from content
  - Optional CLI to refresh and persist the latest disclosures payload to `samples/`

Data flow

- DEV: `samples/*.html` + local disclosures → spider → semantic JSON → `output_DEV.json`
- PROD: live page + remote disclosures → spider → semantic JSON → `output_PROD.json` (+ optional raw HTML saved under `samples/`)

## Disclosures Integration

- On-page markers: `<gb-disclosure data-disclosure-id="...">`
- At parse time: lookup the ID in the disclosures mapping
  - Found: replace with the full content (cleaned)
  - Missing: emit a fallback with `text` and `disclosure_id` for later reconciliation

Refresh DEV disclosures

- `python scrapper/disclosure.py --save-json --file-name disclosurespurejson.json`
- Use `--out <path>` to save to a custom file

## What Gets Serialized (High-Level)

- Noise reduction: EXCLUDE flattens structural/noisy tags (script/style/template/noscript/div/nav/section/article, grid wrappers, etc.)
- Wrapper flattening: WRAPPERS collapses trivial containers (header/main/footer/picture/aside/gb-dynamic-text/adv-grid) unless specialized
- Rich serializers: links, button-like elements, images and srcsets, headings, lists, paragraphs with inline content, tables (row arrays), SVG and paths, GM components (`gb-dynamic-text`, `gb-region-selector`, `gb-myaccount-flyout`, `gb-disclosure`)
- Utilities: URL normalization, internal/external classification, robust JSON attribute parsing, NBSP handling, metadata extraction

## Design Choices & Rationale

- Scrapy over ad-hoc scripts: Crawl lifecycle, retries, FEEDS, throttling, and observability out of the box; easy to layer Playwright for dynamic content
- DEV vs PROD split: Speed and determinism for iteration; live validation for production reality
- Semantic transform: Purposefully reduce layout noise while preserving meaningful content; serializers capture intent (links/buttons/images/lists/tables) and GM-specific components
- Disclosure enrichment: Decouple content from page markers; support offline iteration with a local disclosures snapshot
- Output stability: One item per page with consistent shape (`url`, `metadata`, `navbar`, `main_body_content`, `footer`)

## Why Scrapy over BeautifulSoup

- Purpose and scope
  - BeautifulSoup is a great HTML/XML parser, but it is not a crawler. You must glue together HTTP clients, concurrency, retries, scheduling, politeness, storage, and logging yourself.
  - Scrapy is a full crawling framework: downloader, scheduler, item pipeline, middleware, feed exports, throttling, and robust logging/stats/signals out of the box.
- Robust networking and crawling primitives
  - Built-in retry/backoff, request fingerprinting/deduplication, cookies, headers, caching, robots.txt obedience, and AutoThrottle.
  - With BeautifulSoup alone, you would need to implement these around a separate HTTP client (e.g., requests/async clients).
- Concurrency and performance
  - Scrapy’s async engine (Twisted) efficiently handles high concurrency with backpressure control.
  - Rolling your own asyncio/threading around BeautifulSoup is feasible but error-prone and harder to tune.
- Extensibility and maintainability
  - Spiders, middlewares, and pipelines create a clean separation of concerns and make it easy to add features (e.g., disclosure enrichment, custom exporters).
  - BeautifulSoup scripts tend to become monolithic as responsibilities grow beyond parsing.
- Dynamic content readiness
  - Scrapy integrates with browser automation via custom download handlers (e.g., scrapy-playwright) when needed for JS-rendered pages.
  - BeautifulSoup cannot execute JavaScript; you’d need to bring your own browser automation layer and integrate it manually.
- Observability and resilience
  - Rich logging, stats, and signal hooks in Scrapy make production monitoring and debugging straightforward.
  - With BeautifulSoup-based scripts, you must build this scaffolding yourself.
- Why this design choice for this project
  - The target page (chevrolet.ca) is dynamic and changes over time; we need reliability, concurrency controls, and a path to browser rendering when needed.
  - We transform multiple DOM regions into a structured JSON schema and enrich content with remote disclosures—best done with a framework that manages the crawl lifecycle and item flow.
  - Scrapy lets us keep DEV mode fast and deterministic (fixtures) while keeping PROD mode robust for live runs.

## Troubleshooting

- No output file: verify FEEDS in `Scrapper.custom_settings` or override with `CrawlerProcess(settings=...)`
- Disclosures missing: ensure the ID exists in `samples/disclosurespurejson.json` (DEV) or that the remote endpoint is reachable (PROD)
- HTML not saved: `--save-html` works only in PROD; files are timestamped under `samples/`
- Mode mismatch: set env var on launch to align Playwright/FEEDS with CLI flags, e.g., `DEV=false python main.py --prod ...`
- Q&A Agent embedding error: verify you have the correct embedding model specified in `.env` (default is `text-embedding-3-small`)
- Q&A Agent API key error: make sure you have a valid OpenAI API key in your `.env` file

## Why DEV and PROD Modes

- DEV: fast, deterministic, and safe for frequent runs
- PROD: validates against the live site with dynamic rendering and current disclosures

This separation keeps iteration fast while ensuring the extractor stays faithful to production reality.

## Q&A Agent

The project includes an interactive Q&A Agent that can answer questions about the Chevrolet Silverado 1500 based on the extracted data.

### Setup for Q&A Agent

1. Create a `.env` file in the project root with your OpenAI API key (you can copy from `.env.example`):

   ```
   OPENAI_API_KEY=your_openai_api_key_here
   # If using a new admin/org key, set the project to route requests:
   # OPENAI_API_KEY_ADMIN=your_admin_api_key_here
   # OPENAI_PROJECT=your_project_id_or_slug
   EMBED_MODEL=text-embedding-3-small
   CHAT_MODEL=gpt-4o-mini
   GRAPH_PATH=output_embedding/embedding.json
   ```

2. Generate the embedding graph from your scraped data:

   - JSONL + graph:

     ```
     python -m embedding.chevy_embed --input output_DEV.json --output embeddings/chevy_embeddings.jsonl --normalized-json output_embedding/embedding.json
     ```

   - Graph only (no JSONL):

     ```
     python -m embedding.chevy_embed --input output_DEV.json --skip-jsonl --normalized-json output_embedding/embedding.json
     ```

   The agent will automatically pick up `output_embedding/embedding.json` when `GRAPH_PATH` is not set.

3. Run the Q&A Agent:

   ```
   python agent.py
   ```

### Using the Q&A Agent

- The agent will load and index the data from `embedding.json` using the OpenAI embedding model.
- Once loaded, you can ask questions about the Chevrolet Silverado 1500.
- The agent will search for relevant context in the indexed data and use OpenAI's chat model to generate answers.
- Type 'exit' or press Ctrl+C to quit the agent.

### Customizing the Agent

- Change the embedding model: Set `EMBED_MODEL` in `.env` or modify the default in `agent.py`
- Change the chat model: Set `CHAT_MODEL` in `.env` or modify the default in `agent.py`
- Adjust the number of context documents: Modify the `k` parameter in the `retrieve` function call in `agent.py`
