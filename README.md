# Chevrolet Silverado 1500 Semantic Scraper

A focused Scrapy-based spider that converts selected parts of chevrolet.ca’s Silverado 1500 page into a compact, semantically meaningful JSON structure. It supports a development mode (offline, deterministic, fixture-based) and a production mode (live site, optionally browser-rendered), and it can inject official disclosure content into the output when present on the page.

This README explains:

- How the data is fetched, parsed, and transformed
- How DEV vs PROD modes work and why they differ
- How disclosures are integrated
- How to set up and run the project in both modes

## Project layout (relevant files)

- `main.py` — CLI entrypoint; sets mode, loads disclosures, runs the Chevy spider
- `scrapper/chevy_scrapper.py` — The `ChevyScapper` spider responsible for scraping and DOM-to-JSON transformation
- `scrapper/disclosure.py` — Disclosures loader and standalone scraper; includes the `load_disclosures` function used by `main.py`
- `samples/` — Local fixtures used in DEV mode (expected: `silverado1500.html`, `disclosurespurejson.json`)
- `utils/logger.py` — Logging utility (not shown here)

## How the scraper works (end-to-end flow)

1. Entry (CLI)

- Run `python main.py` with Click options to choose DEV/PROD, logging level, and whether to save HTML.
- The CLI sets logging, stores the mode in `os.environ["DEV"]`, and loads disclosures before starting the spider.

2. Disclosures loading

- `main.py` calls `load_disclosures(dev_mode=dev)` from `scrapper/disclosure.py`.
  - In DEV: reads `samples/disclosurespurejson.json` on disk and returns a dict.
  - In PROD: fetches <https://www.chevrolet.ca/content/chevrolet/na/ca/en/index.disclosurespurejson.html>, parses it into a dict (using robust JSON cleaning), and returns it.
- The resulting dict is passed to the spider so disclosure markers on the page (elements with `data-disclosure-id`) can be replaced with full text.

3. Spider launch

- `main.py` starts a `CrawlerProcess` and runs `scrapper.chevy_scrapper.ChevyScapper` with two runtime parameters:
  - `disclosures`: the mapping loaded in step 2 (or None if unavailable)
  - `save_html`: whether to persist a raw HTML copy (only in PROD)

4. Page selection by mode

- In DEV: the spider reads `samples/silverado1500.html` using a `file://` URL (no network).
- In PROD: the spider uses the live page `https://www.chevrolet.ca/en/trucks/silverado-1500`.
  - If a browser integration (e.g., scrapy-playwright) is configured in the base `Scrapper` class, the response may contain a `playwright_page` object.

### 1. DOM-to-JSON transformation

- The spider extracts high-level sections via XPath:
  - Navbar: `//gb-global-nav/template[@id='gb-global-nav-content']`
  - Main body: `//main[@id='gb-main-content']`
  - Footer: `//gb-global-footer`
- Each section is transformed with a DFS that:
  - Skips layout-only or noisy tags (see EXCLUDE)
  - Flattens trivial wrappers (see WRAPPERS)
  - Applies specialized serializers for semantics:
    - Links (`a`) with `text`, `href`, internal/external classification
    - Buttons (`button`, `input[type in {button, submit, reset}]`) with action URLs, ARIA attributes, data- attributes
    - Images (`img`) with `src`, `alt`, `title`, loading, data- attributes
    - Responsive sources (`source`) with resolved `srcset`
    - Headings (`h1`–`h6`) as simple text
    - Lists (`ul`, `ol`, `li`) preserving structure
    - Paragraphs (`p`) with inline content preserved
    - SVG and `path` with compact path serialization
    - Tables serialized as row arrays
    - GM-specific components:
      - `gb-dynamic-text` (content + structured attributes)
      - `gb-region-selector` (structured attributes)
      - `gb-myaccount-flyout`
      - `gb-disclosure` (see next section)
- The spider yields one item per page with:
  - `url`
  - `metadata` (via a base method, e.g., title/description/meta tags)
  - `navbar`
  - `main_body_content`
  - `footer`

6. Output

- Items are yielded through Scrapy’s item pipeline. The final write destination depends on FEEDS configuration.
- If your base `Scrapper` class or project settings define FEEDS, items will be written accordingly. If not, you can override `CrawlerProcess(settings={...})` in `main.py` to add FEEDS.

Tip (optional): to force a local file export, you can change `settings={}` in `main.py` to include a FEEDS block that picks a filename based on DEV/PROD (JSON, overwrite=true).

## Disclosures integration

- On chevrolet.ca pages, disclosures are often referenced via elements like `<gb-disclosure data-disclosure-id="SOME_KEY">...</gb-disclosure>`.
- At runtime, `ChevyScapper.serialize_disclosure`:
  - Looks up `data-disclosure-id` in the `disclosures` mapping provided at spider start
  - If found, replaces the node with the full disclosure content (cleaned of basic tags like `<p>`, `<sup>` by the loader)
  - If not found, emits a fallback structure containing any inline text plus the `disclosure_id` for later reconciliation

Refreshing local DEV disclosures

- Run the standalone disclosures spider to fetch the latest live payload and save it into `samples/`:
  python scrapper/disclosure.py --save-json --file-name disclosurespurejson.json
  - You can also use `--out <path>` to save to a custom location.

Programmatic loader (`load_disclosures`)

- Used by `main.py` for both DEV and PROD
- DEV: reads from `samples/disclosurespurejson.json`
- PROD: downloads and parses the remote JSON (using certifi if available)

## DEV vs PROD: what changes

Data source

- DEV: Reads from local fixtures in `samples/` (no network, deterministic)
- PROD: Fetches the live site and live disclosures

Rendering and page handle

- DEV: No browser/page handle; strictly file content
- PROD: If a browser integration is configured, a `playwright_page` may be present in `response.meta` and is explicitly closed by the spider

HTML capture

- DEV: `--save-html` is ignored
- PROD: When `--save-html True` is set, the spider saves the raw HTML response for future offline development

Operational characteristics

- DEV: Fast iteration, stable structure, safe for frequent runs
- PROD: Network-dependent, reflects the current site, subject to live changes

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

## Running the code

Prerequisites

- Python 3.10+ recommended
- Install project dependencies (for example, using a requirements.txt if present)
- If your base Scrapper integrates a browser (e.g., scrapy-playwright), ensure browsers are installed (e.g., `playwright install chromium`)

Install

- Create and activate a virtual environment, then install dependencies:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

If no requirements file is provided, install at least: scrapy, click, lxml (plus certifi for PROD disclosures). If your base uses a browser, also install scrapy-playwright and Playwright, then run `playwright install chromium`.

Quick start: Development mode (offline, local fixtures)

- Ensure `samples/silverado1500.html` and `samples/disclosurespurejson.json` exist
- Run:
  ```bash
  python main.py --dev --log-level INFO
  ```
  Notes:
  - Uses the local HTML file and local disclosures
  - Fast and deterministic
  - `--save-html` has no effect in DEV

Quick start: Production mode (live site)

- Run:

```bash
python main.py --prod --log-level INFO --save-html True
```

Notes:

- Fetches the live page and live disclosures
- If configured, may open a browser context to render dynamic content
- Saves raw HTML for reuse in DEV if `--save-html True` is provided

CLI options for `main.py`

- `--dev/--prod` (default: `--dev`): Mode toggle
- `--log-level, -l`: One of DEBUG, INFO, WARNING, ERROR, CRITICAL (default: CRITICAL)
- `--save-html, -s`: True/False, only effective in PROD

Where is the output?

- The spider yields a single item of the shape:
  - url: string
  - metadata: object (document metadata)
  - navbar: array/object (semantic structure)
  - main_body_content: array/object (semantic structure)
  - footer: array/object (semantic structure)
- File export is controlled by Scrapy FEEDS settings. If the base class or project config does not set FEEDS, nothing will be written automatically.
- To force writing to a file, add a FEEDS block to the `CrawlerProcess` settings in `main.py` (e.g., choose a filename based on DEV/PROD, JSON format, overwrite=true).

## What gets serialized (high-level)

Noise reduction

- EXCLUDE set drops structural/noisy tags but retains their children: script, style, template, noscript, div, nav, section, article, grid/wrapper components, etc.

Wrapper flattening

- WRAPPERS set flattens trivial containers (header, main, footer, picture, aside, gb-dynamic-text, adv-grid) unless a specialized serializer exists.

Specialized serializers (selected)

- Links (`a`): text, href, link_type (internal/external), target, nested content
- Buttons-like (`button`, `input` with type in {button, submit, reset}): text, action URL, ARIA attrs, data- attributes
- Images (`img`): src, alt, title, loading, data-\*
- Sources (`source`): parsed srcset with resolved URLs
- Headings (`h1`–`h6`): extracted text
- Lists (`ul`, `ol`, `li`): preserves structure and nested content
- Paragraphs (`p`): text plus nested content
- Tables: emitted as lists of row arrays
- SVG and `path`: compact attribute/path payload
- GM components: `gb-dynamic-text`, `gb-region-selector`, `gb-myaccount-flyout`, `gb-disclosure` (with disclosure injection when available)

Utilities

- URL normalization and internal/external classification
- Attribute JSON parsing with safe fallbacks and NBSP handling
- Metadata extraction via the base `Scrapper` class

## Updating or extending

- To scrape a different Chevrolet page, change `prod_url` (and the DEV fixture) in `ChevyScapper`.
- To support additional components, add a serializer in `get_native()` and its implementation.
- To alter which regions of the DOM are parsed, adjust the XPaths in `parse()`.

## Troubleshooting

- No output file appears
  - Ensure FEEDS are configured either in the base `Scrapper` or passed to `CrawlerProcess(settings=...)`.
- Disclosures missing
  - Confirm the disclosure key exists in the loaded mapping (DEV: samples file; PROD: remote endpoint).
  - Use the standalone disclosure CLI to refresh DEV data.
- HTML save not working
  - `--save-html` only applies in PROD.
  - The save implementation lives in the base `Scrapper` (`save_response_html`), which determines the final path/name.

## Why DEV and PROD modes

- DEV exists for speed, determinism, and cost control. You can iterate on the DOM-to-JSON logic without live network or a browser.
- PROD exists to validate against the live site with dynamic rendering and the current disclosures content.

This separation keeps iteration fast while ensuring your extractor stays faithful to production reality.
