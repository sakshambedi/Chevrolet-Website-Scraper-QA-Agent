# 🚗 Chevrolet Website — Scraper + Q&A Agent

Scrape the Silverado 1500 website, turn it into clean semantic JSON, build embedding artifacts, and ask questions with a local Q&A agent.

## ✨ What You Get

- 🕷️ Scraper (Scrapy) → `output_DEV.json` / `output_PROD.json`
- 🧱 Normalized graph → `output_embedding/embedding.json`
- 🧠 Optional JSONL table → `embeddings/chevy_embeddings.jsonl`
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

- DEV (fixture): `python scrap.py --dev --log-level INFO` → `output_DEV.json`
- PROD (live): `python scrap.py --prod --log-level INFO` → `output_PROD.json`
- Multi-page options:
  - Discover: `python scrap.py --prod --discover-vehicles --category trucks`
  - File: `python scrap.py --prod --urls-file urls.json`

3. Build embedding artifacts

- JSONL + graph:
  `python -m embedding.chevy_embed --input output_DEV.json --output embeddings/chevy_embeddings.jsonl --normalized-json output_embedding/embedding.json`
- Graph only (skip JSONL):
  `python -m embedding.chevy_embed --input output_DEV.json --skip-jsonl --normalized-json output_embedding/embedding.json`

4. Ask questions

- `python agent.py`
- The agent uses `GRAPH_PATH` if set; otherwise it looks for `output_embedding/embedding.json`.

### Example Usage

Below are examples of using the agent.py interactive console:

1. When you run the agent, it will build an index from your embedding file:
   ![Agent Initialization](imgs/Screenshot%202025-09-01%20at%2010.23.52%20PM.jpg)

2. You can ask questions about the Chevrolet Silverado, and the agent will find relevant context:
   ![Agent Question](imgs/Screenshot%202025-09-01%20at%2010.24.08%20PM.jpg)

3. The agent provides answers based on the retrieved information:
   ![Agent Answer](imgs/Screenshot%202025-09-01%20at%2010.52.04%20PM.jpg)

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
- PROD scrape: `python scrap.py --prod --log-level INFO`
- Build JSONL + graph: `python -m embedding.chevy_embed --input output_DEV.json --output embeddings/chevy_embeddings.jsonl --normalized-json output_embedding/embedding.json`
- Graph only: `python -m embedding.chevy_embed --input output_DEV.json --skip-jsonl --normalized-json output_embedding/embedding.json`
- Run agent: `python agent.py`
