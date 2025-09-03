# 🚗 Chevrolet Scraper + Q&A Agent

Scrape Chevrolet vehicle pages, produce a clean JSON, build a normalized embedding graph, and ask questions locally with a simple agent.

## ✅ What This Repo Provides

- Scraper (Scrapy) → `output_DEV.json` or `output_PROD.json`
- Normalized graph (for retrieval) → `output_embedding/embedding.json`
- Local Q&A agent (OpenAI) → `agent.py`

## ⚙️ Requirements

- Python 3.10+
- Install deps: `pip install -r requirements.txt`
- For PROD (JS-rendered pages): `python -m playwright install chromium`

## 🚀 Quickstart

1) Configure environment

- Run `python setup.py` and enter your keys, or copy `.env.example` to `.env` and set:
  - `OPENAI_API_KEY=...`
  - `OPENAI_PROJECT=...` (optional)
  - `GRAPH_PATH=output_embedding/embedding.json`

2) Scrape

- DEV (uses local fixtures):
  - `python scrap.py --dev --log-level INFO` → writes `output_DEV.json`
- PROD (live site):
  - Single page: `python scrap.py --prod --url https://www.chevrolet.ca/en/suvs/previous-year-equinox --log-level INFO`
  - Discover by category: `python scrap.py --prod --discover-vehicles --category crossovers-suvs --log-level INFO`

3) Build the embedding graph

- From the newest crawl: `make embed-latest`
- Or explicitly: `python -m embedding.chevy_embed --input output_PROD.json --normalized-json output_embedding/embedding.json`

4) Ask questions

- `python agent.py`
- The agent reads `GRAPH_PATH` (or defaults to `output_embedding/embedding.json`).

## 📥 Scraping Overview (Assignment)

- Purpose: collect on-page marketing content from specific Chevrolet Canada vehicle pages so an AI system can reference it when communicating with customers. Produce a clean, structured JSON.
- Scope (fixed pages):
  - Silverado 1500: <https://www.chevrolet.ca/en/trucks/silverado-1500>
  - Equinox (Previous Year): <https://www.chevrolet.ca/en/suvs/previous-year-equinox>
- What’s extracted:
  - Page metadata: title, description, canonical, OpenGraph/Twitter
  - Headings and paragraphs: cleaned and deduplicated
  - Bullet lists: feature highlights and benefits
  - Images and captions: hero, gallery, badges/awards
  - Videos: embedded YouTube/Vimeo or site-hosted
  - Calls-to-action: text and links (e.g., “Build & Price”, “Find a Dealer”)
  - Awards and badges: recognitions on the page
  - Links: internal Chevrolet.ca and external references
  - Content chunks: 1–3 paragraph segments for retrieval
- Output: a single JSON file per page/run. For the assignment deliverable, copy or name the latest crawl as `output.json` (canonical scraping output).
  - Example: `python scrap.py --prod --url https://www.chevrolet.ca/en/suvs/previous-year-equinox && cp output_PROD.json output.json`

## 🔎 Modes (DEV vs PROD)

- DEV: offline, fast; reads fixtures from `samples/`; outputs `output_DEV.json`.
- PROD: fetches live pages with Playwright; supports `--url` and `--discover-vehicles`; outputs `output_PROD.json`.
- After either: run `make embed-latest` to produce `output_embedding/embedding.json` used by the agent.

## 📦 Outputs

- Crawl output: `output_DEV.json` or `output_PROD.json` (use `output.json` as the canonical deliverable for scraping)
- Normalized graph: `output_embedding/embedding.json` (single JSON used for retrieval)

## 🤖 AI Query Proof Of Concept

- Goal: demonstrate retrieval-augmented answers over the scraped Chevrolet content using a simple local agent.
- Generate embedding table (normalized graph):
  - From latest crawl: `make embed-latest` → writes `output_embedding/embedding.json`
  - From canonical file: `python -m embedding.chevy_embed --input output.json --normalized-json output_embedding/embedding.json`
- Run the agent: `python agent.py`
  - Reads `GRAPH_PATH` (or defaults to `output_embedding/embedding.json`)
  - Builds a lightweight index, retrieves most similar chunks, and answers with context

## 🧩 Configuration

- Models: set `EMBED_MODEL` and `CHAT_MODEL` in `.env` (defaults provided).
- Override graph path with `GRAPH_PATH` in `.env`.

## 🧭 Handy Commands

- DEV scrape: `python scrap.py --dev --log-level INFO`
- PROD scrape (single page): `python scrap.py --prod --url https://www.chevrolet.ca/en/suvs/previous-year-equinox --log-level INFO`
- Build graph (latest): `make embed-latest`
- Build graph (explicit): `python -m embedding.chevy_embed --input output_PROD.json --normalized-json output_embedding/embedding.json`
- Run agent: `python agent.py`

## 📝 Notes

- If Playwright is missing: `python -m playwright install chromium`.
- You can also set `CHEVY_START_URL` for a default PROD start page when not using `--url`.
- Each record in the graph nests full page `<head>` metadata under `metadata.page_metadata`.

## 📂 Project Layout

- `scrap.py`: CLI to run the scraper (DEV/PROD, discovery)
- `scrapper/`: spider + helpers
- `embedding/`: graph builder (`embedding.chevy_embed`)
- `agent.py`: retrieval + OpenAI chat interface
