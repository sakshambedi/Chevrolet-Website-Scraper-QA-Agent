# Semantic DOM-to-JSON Scraper (Scrapy + Playwright)

A production-grade web scraper that converts complex DOM structures into semantically meaningful JSON optimized for LLM consumption. Built for Chevrolet's dynamic e-commerce pages but architected for extensibility across different sites.

## Why Scrapy

**Decision**: Scrapy over alternatives (BeautifulSoup, Selenium, custom asyncio)

**Rationale**:

- **Production reliability**: Built-in retry logic, connection pooling, and error handling
- **Observability**: Comprehensive logging, metrics, and debugging capabilities
- **Extensibility**: Middleware/pipeline architecture enables clean separation of concerns
- **Performance**: Async I/O with configurable throttling and concurrency controls
- **Standards compliance**: ROBOTSTXT_OBEY, proper header management, respectful crawling

### Dynamic Content: Playwright Integration

**Decision**: Scrapy-Playwright over pure Scrapy or Selenium

**Rationale**:

- Modern automotive sites heavily rely on JavaScript for navigation and content rendering
- Playwright provides faster browser automation than Selenium with better resource management
- Scrapy-Playwright maintains Scrapy's architectural benefits while adding browser capabilities
- Configurable browser lifecycle management (headless, viewport, timeouts)

**Implementation Strategy**:

```python
# Production settings enable Playwright selectively
if not DEV_MODE:
    custom_settings.update({
        "DOWNLOAD_HANDLERS": {
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 60000,
    })
```

### Development Workflow: DEV/PROD Mode Separation

**Decision**: Environment-based mode switching with local fixtures
**Rationale**:

- **Iteration speed**: DOM parsing logic development without browser overhead
- **Deterministic testing**: Static HTML fixtures ensure consistent parser behavior
- **Rate limit compliance**: Avoid hitting production endpoints during development
- **Cost efficiency**: No unnecessary Playwright browser launches

**Implementation**:

- `DEV=true` → loads `samples/silverado1500.html` via `file://` protocol
- `DEV=false/unset` → full Playwright rendering of live site

### Semantic JSON Design Philosophy

**Problem**: Raw HTML is verbose, inconsistent, and poorly suited for LLM reasoning
**Solution**: Depth-First Search (DFS) transformation to semantic JSON nodes

**Key Design Principles**:

1. **Semantic Preservation**: Each HTML element maps to a meaningful JSON structure

   ```json
   {"a": {"text": "View Inventory", "href": "/inventory", "link_type": "internal"}}
   {"img": {"src": "/photo.jpg", "alt": "Silverado", "link_type": "internal"}}
   {"heading": "2025 Silverado Features"}
   ```

2. **Noise Reduction**: Aggressive filtering of layout-only elements
   - `EXCLUDE` set removes `<script>`, `<style>`, wrapper `<div>`s, custom components
   - `WRAPPERS` flattening eliminates trivial container nesting

3. **Link Intelligence**: Comprehensive URL analysis and classification

   ```python
   def is_internal_link(self, url: str, base_domain: str) -> bool:
       # Classify internal vs external links for downstream LLM understanding
   ```

4. **Structured Data Extraction**: Custom serializers for complex elements
   - Lists → normalized `{"items": [...]}` arrays
   - Buttons → action URLs, form targets, ARIA attributes
   - Images → responsive `srcset`, data attributes, accessibility info

### Parser Architecture

**Core Algorithm**: Recursive DFS with specialized serializers

```python
def dfs(self, node, base_url):
    tag = node.xpath("name()").get().lower()

    # Skip noise elements but preserve children
    if tag in self.EXCLUDE:
        return [child for child in self._process_children(node, base_url)]

    # Use specialized serializer if available
    if tag in self.NATIVE:
        return self.NATIVE[tag](node, base_url)

    # Fallback to generic serialization
    return self._serialize_generic(node, base_url)
```

**Serializer Strategy**: Each HTML element type has a dedicated serializer optimizing for LLM consumption:

- **Links**: Extract href, classify internal/external, preserve navigation context
- **Media**: Normalize URLs, extract responsive attributes, maintain accessibility data
- **Interactive Elements**: Capture form actions, button behaviors, ARIA semantics
- **Content Blocks**: Preserve heading hierarchy, list structure, semantic markup

### Error Handling & Resilience

**Graceful Degradation**: Parser failures don't break entire extraction

```python
try:
    return specialized_serializer(node, base_url)
except Exception as e:
    logger.warning(f"Serializer failed for {tag}: {e}")
    return generic_fallback(node, base_url)
```

**Validation Pipeline**: Multi-layer validation ensures output quality

- URL normalization with `urljoin()` for relative links
- JSON attribute parsing with robust error handling
- Text extraction with HTML entity decoding

### Performance Optimizations

**Selective Processing**: Only parse semantically valuable DOM regions

- Navbar: `//gb-global-nav/template[@id='gb-global-nav-content']`
- Main content: `//main[@id='gb-main-content']`
- Skip footer, advertising, tracking elements

**Memory Efficiency**: Streaming JSON output via Scrapy FEEDS

```python
custom_settings = {
    "FEEDS": {"output.json": {"format": "json", "overwrite": True}},
}
```

**Concurrency Control**: Configurable throttling for respectful crawling

```python
"AUTOTHROTTLE_ENABLED": True,
"AUTOTHROTTLE_START_DELAY": 1.0,
```

## Project Structure & Extensibility

**Inheritance Hierarchy**: Abstract base class enables site-specific implementations

```
Scrapper (ABC) → ChevyScapper → [Future: FordScapper, ToyotaScapper]
```

**Configuration Management**: Environment-driven settings with sensible defaults

- `.env` file for local development configuration
- Spider-level `custom_settings` for production overrides
- Logging configuration via Click CLI options

**Output Schema**: Structured for downstream LLM consumption

```json
{
  "url": "https://...",
  "metadata": {"title": "...", "description": "...", "opengraph": {...}},
  "navbar": {"navbar_content": [...]},
  "main_body_content": [...]
}
```

## Current Implementation Status

**Fully Implemented**:

- ✅ Metadata extraction (title, description, OpenGraph, Twitter cards)
- ✅ Navigation parsing with complete semantic structure
- ✅ Main body content extraction with DFS algorithm
- ✅ DEV/PROD mode switching
- ✅ Comprehensive link classification and URL normalization
- ✅ Specialized serializers for 15+ HTML element types

**Architecture Ready for Extension**:

- Additional automotive sites (Ford, Toyota, etc.)
- Different content types (product catalogs, reviews, specifications)
- Alternative output formats (CSV, XML, database)
- Advanced LLM preprocessing (summarization, entity extraction)

## Setup & Usage

### Environment Setup

Create a `.env` file in the root directory with the following basic settings:

```bash
# Development (fast iteration with local fixtures)
DEV=true

# Production (full browser rendering)
DEV=false
```

The application relies on this environment variable to determine whether to use local HTML files (DEV=true) or fetch content from the live website (DEV=false).

### Installation

**Using pip**:

```bash
# Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (required for production mode)
playwright install chromium
```

**Using uv** (faster Python package installer):

```bash
# Create and activate a virtual environment
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -r requirements.txt

# Install Playwright browsers (required for production mode)
playwright install chromium
```

### Running the Scraper

**Using Make**:

```bash
# Run in default mode (CRITICAL log level)
make run

# Run with INFO logging level
make rund
```

**Direct Python execution**:

```bash
# Run with default settings
python main.py

# Run with custom log level
python main.py --log-level INFO

# Run with HTML saving enabled
python main.py --save-html True

# Run with both options
python main.py --log-level DEBUG --save-html True
```

**Command Line Options**:

- `--log-level` or `-l`: Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `--save-html` or `-s`: Save HTML from website (True/False)

**Outputs**:

- `output.json` contains structured semantic data ready for LLM consumption
- When `--save-html True` is specified and in production mode (`DEV=false`), the HTML content from the scraped website will be saved to the `samples` directory with a timestamped filename for future use in development mode

### HTML Samples

The `samples` directory contains HTML files from previously scraped websites that can be used in development mode:

- When `DEV=true` in the `.env` file, the scraper will use these local HTML files instead of making requests to the live website
- New samples can be added by running the scraper in production mode with the `--save-html True` option
- These samples are essential for development and testing without repeatedly hitting the production website

## Technical Decisions Summary

1. **Scrapy + Playwright**: Production reliability with modern browser capabilities
2. **Semantic JSON Schema**: LLM-optimized data structures over raw HTML
3. **DEV/PROD Separation**: Fast iteration without compromising production fidelity
4. **DFS + Specialized Serializers**: Comprehensive DOM understanding with graceful fallbacks
5. **Abstract Base Architecture**: Clean extensibility for multi-site scraping
6. **Environment-Driven Configuration**: Deployment flexibility with sensible defaults

This architecture demonstrates production-ready web scraping with clear separation of concerns, comprehensive error handling, and optimization for downstream AI/ML workflows.

## Future Plans

```mermaid
flowchart TD
    A[TUI Interface (Prompt Toolkit)] --> B[Query Handler]
    B --> C[Embedding (OpenAI API)]
    B --> D[Vector Search (FAISS)]
    D --> E[Top-K Chunks]
    E --> F[OpenAI Chat Completion]
    F --> A

    subgraph Supabase
        G[JSON Website Dump] --> B
    end

```
