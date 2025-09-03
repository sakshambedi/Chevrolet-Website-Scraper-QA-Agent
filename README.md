# 🚗 Chevrolet Website - Scraper + Q&A Agent

Scrape Chevrolet vehicle pages (any model/URL), turn them into clean semantic JSON, build embedding artifacts, and ask questions with a local Q&A agent.

## ✨ What You Get

- 🕷️ Scraper (Scrapy) → `output_DEV.json` / `output_PROD.json`
- 🧱 Normalized graph → `output_embedding/embedding.json` (primary artifact used by the agent)
- 🧠 Embedding output is a single normalized JSON graph (no JSONL).
- 🤖 Q&A Agent (OpenAI) → `agent.py`

## ⚙️ Prerequisites

- Python 3.10+
- Install deps: `pip install -r requirements.txt`
- For PROD scraping: `python -m playwright install chromium`

## 🚀 Quickstart

1. Configure OpenAI

- Run `python setup.py` and paste your `OPENAI_API_KEY` and `OPENAI_PROJECT`.
- Or copy `.env.example` → `.env` and set:
  - `OPENAI_API_KEY=...`
  - `OPENAI_PROJECT=...`
  - `GRAPH_PATH=output_embedding/embedding.json`

2. Scrape → semantic JSON

- DEV (fixture):

```bash
python scrap.py --dev --log-level INFO # returns output_DEV.json
```

- PROD (live):

```bash
# Single page (recommended)
python scrap.py --prod --url https://www.chevrolet.ca/en/suvs/previous-year-equinox --log-level INFO

# Discover vehicles by category
python scrap.py --prod --discover-vehicles --category crossovers-suvs --log-level INFO
```

Dynamic URL behavior:

- Use `--url` for a single Chevrolet vehicle page (no hardcoded Silverado default).
- Discovery mode crawls simplified nav and filters by category.

3. Build embedding artifacts (graph)

- Make target from latest crawl:

```bash
make embed-latest  # picks newest output_*.json and writes output_embedding/embedding.json
```

- Manual graph build:

```bash
python -m embedding.chevy_embed \
  --input output_PROD.json \
  --normalized-json output_embedding/embedding.json
```

 

4. Ask questions

- `python agent.py`
- The agent uses `GRAPH_PATH` if set; otherwise it looks for `output_embedding/embedding.json`.

## 🧭 DEV vs PROD

- DEV mode:
  - Parses local HTML fixture(s) from `samples/` via `file://`.
  - No browser automation; fast and offline.
  - Output file: `output_DEV.json`.
  - Run: `python scrap.py --dev --log-level INFO`.
- PROD mode:
  - Fetches live Chevrolet pages; uses Playwright for JS-rendered content.
  - Supports `--url` for a single page or `--discover-vehicles` to crawl by category.
  - Output file: `output_PROD.json`.
  - Run: `python scrap.py --prod --log-level INFO`.
- After either mode:
  - `make embed-latest` selects the newest `output_*.json` and writes `output_embedding/embedding.json` (the agent’s default). Override with `GRAPH_PATH` in `.env`.

### Notes

- Each document in the normalized graph includes `metadata.page_metadata` (the page’s `<head>` metadata: title, description, canonical, language, OpenGraph, Twitter) nested to avoid clobbering computed fields like `model_id`, `section_title`, and `region`.
- You can set `CHEVY_START_URL` to override the default PROD start page when not passing `--url`.
- Crawl outputs land in the repo root as `output_DEV.json` or `output_PROD.json` (depending on mode). The `make embed-latest` target automatically picks the most recent `output_*.json` and writes the normalized graph to `output_embedding/embedding.json` (the default path the agent uses). You can override with `GRAPH_PATH` in your `.env`.

### Output format

- The embedding step produces a single normalized graph at `output_embedding/embedding.json` used by the agent.

### Example Usage

Below are examples of using the agent.py interactive console:

1. When you run the agent, it will build an index from your embedding file:
   ![Agent Initialization](./imgs/Screenshot%202025-09-01%20at%2010.23.52 PM.jpg)

2. The agent provides answers based on the retrieved information:
   ![Agent Answer](/imgs/Screenshot%202025-09-01%20at%2010.52.04 PM.jpg)

The agent follows these steps for each question:

1. Retrieves the most relevant documents from the index based on semantic similarity
2. Displays a table of the top matches with similarity scores
3. Constructs a context from these documents
4. Generates an answer using the provided context

## 📂 Project At A Glance

- `scrap.py`: CLI to run the Chevy spider (DEV/PROD, discover URLs, etc.)
- `scrapper/`: spider + helpers (disclosures, serializers, logging)
- `embedding/`: embedding table builder (Chevy-specific + GM base)
- `agent.py`: simple retrieval + OpenAI chat interface

## 🧠 Why Scrapy over BeautifulSoup

- Purpose and scope
  - BeautifulSoup is a great HTML/XML parser, but not a crawler. You’d bolt on HTTP, retries, concurrency, scheduling, storage, and logging yourself.
  - Scrapy is a full crawling framework: downloader, scheduler, pipelines, middlewares, FEEDS, throttling, and rich logging/stats/signals.
- Robust networking and crawling primitives
  - Built-in retry/backoff, deduplication, cookies/headers, caching, robots.txt obedience, AutoThrottle.
  - With BeautifulSoup alone, you’d assemble and maintain these around a separate HTTP client.
- Concurrency and performance
  - Scrapy’s async engine (Twisted) handles high concurrency with backpressure.
  - Rolling your own asyncio/threading around BeautifulSoup is feasible but brittle.
- Extensibility and maintainability
  - Spiders/middlewares/pipelines separate concerns; easy to add features (e.g., disclosure enrichment, custom exporters).
  - BeautifulSoup scripts tend to become monolithic as scope expands.
- Dynamic content readiness
  - Scrapy integrates with browser automation (scrapy-playwright) for JS-rendered pages.
  - BeautifulSoup can’t execute JavaScript without an added browser layer.
- Observability and resilience
  - Scrapy offers rich logs, stats, and signals for production monitoring.
- Why for this project
  - The site is dynamic and changes; we need reliability, an optional browser, and a clean crawl lifecycle.
  - We transform multiple DOM regions into a structured JSON schema with disclosures—well-suited to Scrapy’s pipelines.

## 🧩 Tips

- Use `--dev` for fast, offline iterations; PROD uses Playwright and the live site.
- If Playwright is missing: `python -m playwright install chromium`.
- To change models, set `EMBED_MODEL` or `CHAT_MODEL` in `.env`.

## 📜 Copy/Paste Commands

- DEV scrape: `python scrap.py --dev --log-level INFO`
- PROD scrape (single page): `python scrap.py --prod --url https://www.chevrolet.ca/en/suvs/previous-year-equinox --log-level INFO`
- Build graph: `python -m embedding.chevy_embed --input output_PROD.json --normalized-json output_embedding/embedding.json`

- Run agent: `python agent.py`
