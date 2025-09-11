# Embedding Graph Builder

I built this package to turn the Chevrolet scraper output into a clean, normalized graph and then into embedding‑ready documents with rich metadata. The agent consumes the graph, embeds the docs, and retrieves relevant chunks to answer questions.

## What This Does

- Reads a semantic JSON/JSONL dump (from the scraper) of a Chevrolet model page.
- Normalizes it into a single graph JSON: models, prices, disclosures, assets, sections, trims, related models, awards.
- Builds embedding‑ready docs (text + metadata) for retrieval and Q&A.

## How It Fits Together

1. Scraper writes `output_DEV.json` or `output_PROD.json` (see repository README for scraping).
2. I run `python -m embedding.chevy_embed --input output.json --normalized-json output_embedding/embedding.json` to produce the normalized graph.
3. The agent (`agent.py`) reads the graph, builds docs, calls OpenAI Embeddings, and performs retrieval + answer synthesis.

## Key Files

- `embedding/embedding.py`
  - Tiny framework: config, record schema, base embedder utils.
  - `EmbeddingConfig`: settings for chunk sizes, model name, and id prefix.
  - `Record`: a single row (id, text, metadata, embedding placeholder).
  - `BaseEmbedder`: reads input (JSON or JSONL), iterates items, and delegates domain‑specific extraction to subclasses.
  - `extract_text_blobs()`: utility to recursively pull human‑readable text from nested structures.

- `embedding/gm_base.py`
  - Core normalizer/doc builder for GM sites with a shared JSON shape.
  - Knows how to detect: model/year, navbar prices, feature sections, images, trims, related models, awards, and useful links.
  - Produces a normalized graph and then builds embedding‑ready docs with detailed metadata.

- `embedding/chevy_embed.py`
  - Chevrolet‑specific subclass that provides known Silverado trims and a CLI entry point.
  - Writes the normalized graph to `output_embedding/embedding.json`.

## Data Flow

- Input: one or more page dumps (array JSON or JSONL). I auto‑detect the format.
- Normalized graph: a single JSON with these arrays:
  - `models`: id, name, year, canonical URL, locale, links to other entities, and full page `<head>` metadata for traceability.
  - `prices`: region‑specific entries (from price, as shown price, currency) deduped/merged from navbar blocks.
  - `disclosures`: footnote/asterisk text captured and deduped with stable ids like `disc:<hash>`.
  - `assets`: images discovered across the page.
  - `sections`: only “interesting” sections (towing/performance/interior/technology/safety/capability/awards) with collected paragraphs and disclosures.
  - `trims`: trims found near the “Models” slider (based on known names); optionally enriched with region/price hints.
  - `related_models`: navbar vehicles with inferred ids and price snippets.
  - `awards`: award/accolade blocks with summaries and disclosures.

## Normalization Details (GMBaseEmbedder)

- Model/year parsing: I parse the `<title>` using known GM brands (Chevrolet, GMC, Buick, Cadillac), slug the model name, and extract a year token (e.g., 2024) if present.
- Disclosures: I register every `gb-disclosure` encountered and store the unique text into `disclosures` keyed by a short hash. Docs reference them by id.
- Prices (navbar): I scan `type="a link"` nodes with nested `gb-dynamic-text` and `regional_information`, detecting “from/starting” and “as shown/as configured” cues. I merge partials per region to keep the best available pair of prices and dedupe attached disclosures.
- Sections: I walk `main_body_content`, look for headings matching an interest regex (towing|performance|interior|safety|technology|capability|award|accolades|dependability). I then collect sibling paragraphs and nested disclosures until the next heading.
- Assets: I gather unique image URLs into `assets` with a short id.
- Trims: If the subclass defines `TRIM_NAMES`, I detect trim names near the “Models” slider and create trim objects. `_enrich_trims` associates text bullets and regional price tidbits when available.
- Related models: From navbar links that contain price markers, I infer related model ids (from URL slugs) and attach small price maps by region.
- Links: I gather `build & price`, `inventory`, and `find a dealer` URLs and then select the most relevant ones per model by slug/name.
- Graph merging: `normalize_all()` can accept an array of pages and folds them into a single deduped graph keyed by object ids, merging lists and preferring longer bodies for text fields.

## Doc Building (embedding docs)

I convert the normalized graph into embedding‑ready docs with strong traceability. For each model:

- Text cleaning:
  - Deduplicate lines.
  - Strip stray asterisks (footnote markers) and add a short “See disclosures” cue where relevant.
  - Add unit annotations inline: e.g., “5,000 lb” becomes “5,000 lb (2,268 kg)” if kg isn’t nearby; and vice versa for kg→lb.
- Doc types:
  - `price`: region‑specific summaries for “from” and “as shown”, formatted as CAD when numeric.
  - `overview`: a short model page summary (title/description context) tied to the canonical URL.
  - `feature`: one per interesting section; I chunk long sections into ~2–3 paragraph chunks and then further split if a chunk exceeds ~350 words.
  - `award`: one per award/accolade block.
- Metadata per doc includes: model id/name/year, section id/title, region (if any), `doc_type`, locale, asset ids, disclosure ids, full page metadata, schema version, chunk index/count, char/word counts, `last_scraped_at`, `content_hash`, source URL, and source domain. If section text mentions a known trim, I attach `trim_id`/`trim_ids`.

Note: In the CLI, I emit only the normalized graph. The agent uses the same doc‑builder to produce docs from that graph and then computes embeddings.

## Chevrolet Subclass

`ChevyEmbedder(GMBaseEmbedder)` sets:

- `TRIM_NAMES = ["WT", "Custom", "LT", "RST", "LTZ", "High Country", "Custom Trail Boss", "LT Trail Boss", "ZR2"]`.
- It overrides `extract_records()` to make sure the full original page `<head>` metadata is nested on every doc’s `metadata.page_metadata` (so answers can always be traced back to source context).

## How The Agent Uses This

- The agent loads `output_embedding/embedding.json` (or `GRAPH_PATH` env var).
- It reuses my `_build_docs` implementation to convert the graph to docs in memory.
- It calls OpenAI’s Embeddings API to vectorize those texts and then retrieves top‑k docs by cosine similarity.
- Prompts are constructed with well‑labeled context blocks: doc id, section title, source URL, and compact metadata.

## Commands I Use

- Build the graph from the latest crawl (see Makefile):
  - `make embed-latest`
- Build explicitly from a specific file:
  - `python -m embedding.chevy_embed --input output.json --normalized-json output_embedding/embedding.json`
- Run the agent locally:
  - `python agent.py`

## Design Choices

- Normalize first, embed later: The single graph JSON is easy to inspect, test, and merge across pages before chunking/embedding.
- Traceability by default: I always keep the original page metadata, URLs, domains, and disclosure ids so answers can be verified.
- Robust traversal + targeted cues: I traverse arbitrary nested JSON but lock onto durable content markers (headings, `gb-dynamic-text`, and the Models slider) to extract the right data.
- Practical heuristics: interest regex to filter meaningful sections; unit annotations to improve clarity; link classification to surface the right CTAs.
- Extensible to other GM brands: Subclass `GMBaseEmbedder`, set `TRIM_NAMES`, and override/extend specifics if needed.

## Limitations (and how I handle them)

- Trims are based on a static list; if the site adds new trims, I expand `TRIM_NAMES`.
- Price and link parsing rely on specific labels like “from/starting” and “as shown/as configured”; copy changes might require regex tweaks.
- Chunking is paragraph/word‑based, not semantic; it’s simple and reliable, and I keep chunks smaller than typical embedding limits.

## Extending To Other Brands

- Create a new subclass of `GMBaseEmbedder` (e.g., `GMCEmbedder`) and define brand‑specific `TRIM_NAMES`.
- Optionally tune the interest regex, price/region handling, and link selection heuristics.
- Reuse `normalize_all()` and `_build_docs()` to keep the same graph/doc shape the agent expects.

When I need to debug a page, I load the raw output JSON, run `ChevyEmbedder.normalize_all()` in a REPL, and inspect the resulting `models`, `sections`, and `prices`. It keeps iteration fast without running embeddings until I’m satisfied with the graph.
