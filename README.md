# Semantic DOM-to-JSON Scraper (Scrapy + Playwright)

This project crawls a target web page and converts key parts of its DOM into a compact, semantically meaningful JSON structure that is friendlier for downstream LLM consumption. It currently focuses on Chevrolet Silverado content and demonstrates a generic approach that can be adapted to other sites.

- Core runtime: Scrapy
- Dynamic rendering: Playwright (production mode only)
- CLI: Click
- Logging: lightweight singleton in `utils/logger.py`
- Output: `assingment/output.json`

## Why Scrapy

I chose Scrapy because it is:
- Production-proven: battle-tested crawling framework with great ergonomics and observability.
- Extensible by design: middlewares, pipelines, signals, built-in feed exporters (here used to write `output.json`).
- Sensible constraints out of the box: `ROBOTSTXT_OBEY=True`, header spoofing, throttling and concurrency controls.
- Async-ready: integrates cleanly with Playwright through `scrapy-playwright` and Twisted’s asyncio reactor.
- Declarative crawling: `Spider` lifecycle, `start_requests`, `parse`, and per-spider `custom_settings` keep code cohesive.

## Playwright integration

Many modern pages render navigation and content dynamically. In production mode, the spider enables Playwright:
- Uses Chromium and waits for `domcontentloaded`.
- Applies viewport, locale, throttling, and concurrency settings per-spider in `custom_settings`.
- Ensures the Playwright page is closed after use.

Important: you must install Playwright’s browser binaries once (e.g., `python -m playwright install chromium`) or `playwright install`.

## DEV vs PROD modes

The spider supports a fast, deterministic local development mode for iterating DOM parsing logic:
- Environment variable `DEV` (read via `python-dotenv`) toggles modes.
- When `DEV=true`, the spider loads a sample file at `assingment/samples/silverado_navbar.html` using a `file://` URL.
- When `DEV` is unset or false, the spider hits `https://www.chevrolet.ca/en/trucks/silverado-1500` via Playwright to render dynamic content.

This pattern keeps iteration fast and Playwright-free while developing tree parsers and serializers.

## Approach: DFS DOM parsing to semantic JSON

I use a unified depth-first search (DFS) to traverse the DOM and materialize a JSON tree with semantic nodes. The key ideas:

1) Drop noisy containers but preserve useful children
   - Some tags add visual layout but add little semantic value (e.g., `script`, `style`, `template`, specific component wrappers).
   - These are listed in `EXCLUDE`. When encountered, the parser returns only their children, not the node itself.

2) Flatten trivial wrappers
   - For tags like `div`, `section`, etc., if there’s no meaningful class/text and a single child, we collapse the wrapper, keeping the tree shallower (`WRAPPERS` set).

3) Specialized serializers for important tags
   - `NATIVE` maps HTML tags to serializer functions that capture semantically relevant fields.
   - Examples:
     - `a`: text, `href` normalized with `urljoin`, `link_type` (internal/external), classes, `target`, and nested content.
     - `button`-like (including certain `input`): text, url/form action, link type, classes, aria attributes, and data-* attributes.
     - `img/source`: normalized URLs, alt/title, responsive `srcset`, data attributes, inferred link_type.
     - `h1`…`h6`: compact heading text nodes.
     - Lists: `ul/ol/li` normalize items into `items` for predictable downstream handling.
     - Project-specific custom elements (e.g., `gb-dynamic-text` and `gb-myaccount-flyout`) parse JSON-like attributes with robust unescaping.
   - If a specialized serializer fails, we gracefully fall back to a generic serializer.

4) Preserve verbatim attributes when needed
   - The parser intentionally keeps raw attributes (e.g., data attributes) to avoid opinionated data loss.
   - Utility helpers:
     - `_norm_url` and `is_internal_link` classify and normalize links.
     - `own_text` vs `all_text` to control text extraction scope.
     - `parse_json` to robustly decode JSON present in HTML attributes.

5) Output structure is LLM-friendly
   - Nodes are small, consistent dictionaries (e.g., `{"a": {...}}`, `{"img": {...}}`, `{"heading": "..."} }`) with optional `content` for nested children.
   - This schema encourages easier programmatic summarization, grounding, and retrieval augmentation for LLMs.

## What’s extracted today

- `metadata` from the `<head>`:
  - `title`, `description`, `canonical`, `language`, `template`, `viewport`
  - OpenGraph: `type`, `url`, `site_name`
  - Twitter: `card`, `site`

- `navbar` content:
  - The spider targets `//gb-global-nav/template[@id='gb-global-nav-content']` and runs the unified DFS over it.
  - Produces a structured semantic JSON tree for the navigation.

- `body_content`:
  - Currently a placeholder returning `"No BODY IS PARSED RIGHT NOW"`.
  - The DFS serializer is written to be reusable; wiring it into full body parsing is straightforward next.

## Repository layout

- `assingment/main.py`: Click CLI entrypoint; sets log level, triggers Scrapy `CrawlerProcess` and writes `output.json` via FEEDS.
- `assingment/scrapper.py`: The `Scrapper` spider (name: `Chevy Silverado`), Playwright settings, metadata extraction, navbar parsing, DFS and serializers.
- `assingment/utils/logger.py`: Simple singleton logger with `Logger.configure(...)`.
- `assingment/samples/*.html`: Local fixtures for DEV mode iteration.
- `assingment/requirements.txt`: Python dependencies.
- `assingment/output.json`: Latest crawl output (overwritten on each run).
- `assingment/makefile`: Convenience `make run` and `make run-debug`.

Note: `--save-html/-s` is a CLI flag that’s currently a placeholder and not yet implemented.

## Setup

1) Python environment
   - Create and activate a virtualenv (optional but recommended).
   - Install dependencies: `pip install -r assingment/requirements.txt`

2) Playwright browser installation (only needed for PROD)
   - Install a browser target: `python -m playwright install chromium` (or `playwright install`)
   - First run may take a minute to download
