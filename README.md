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

**Dependencies**:

```bash
pip install -r requirements.txt
playwright install chromium  # Production mode only
```

**Environment Configuration**:

```bash
# Development (fast iteration)
echo "DEV=true" > .env

# Production (full browser rendering)
echo "DEV=false" > .env
```

**Execution**:

```bash
# Development mode
make run

# Production with debug logging
make run-debug

# Direct Python execution
python main.py --log-level INFO
```

**Output**: `output.json` contains structured semantic data ready for LLM consumption

## Technical Decisions Summary

1. **Scrapy + Playwright**: Production reliability with modern browser capabilities
2. **Semantic JSON Schema**: LLM-optimized data structures over raw HTML
3. **DEV/PROD Separation**: Fast iteration without compromising production fidelity
4. **DFS + Specialized Serializers**: Comprehensive DOM understanding with graceful fallbacks
5. **Abstract Base Architecture**: Clean extensibility for multi-site scraping
6. **Environment-Driven Configuration**: Deployment flexibility with sensible defaults

This architecture demonstrates production-ready web scraping with clear separation of concerns, comprehensive error handling, and optimization for downstream AI/ML workflows.
