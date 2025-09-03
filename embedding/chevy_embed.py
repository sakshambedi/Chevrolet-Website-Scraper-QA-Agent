"""
Chevrolet Silverado 1500 embedding builder.

Reads a semantic JSON/JSONL dump and writes a normalized graph JSON for downstream use.
"""

from __future__ import annotations

from pathlib import Path
import json

import click

from typing import Any, Dict, Iterable

from embedding.embedding import EmbeddingConfig, Record
from embedding.gm_base import GMBaseEmbedder


class ChevyEmbedder(GMBaseEmbedder):
    """Chevy-specific embedder that reuses GM shared logic.

    Only brand/model specifics are defined here (e.g., known trims).
    """

    TRIM_NAMES = [
        "WT",
        "Custom",
        "LT",
        "RST",
        "LTZ",
        "High Country",
        "Custom Trail Boss",
        "LT Trail Boss",
        "ZR2",
    ]

    def extract_records(self, item: Dict[str, Any], index: int) -> Iterable[Record]:
        """Override to include full page metadata from the source JSON.

        We reuse the GM normalization/doc building, then attach the original
        top-level `item["metadata"]` under `page_metadata` for each record.
        This preserves all existing computed fields while exposing the raw
        page metadata alongside them in the embedding table.
        """
        norm = self._normalize_item(item)
        docs = self._build_docs(norm)
        page_meta = item.get("metadata") or {}

        for d in docs:
            meta = dict(d.get("metadata") or {})
            # Attach the full source page metadata without overwriting computed keys
            # Use a nested key to avoid collisions and keep structure intact.
            meta["page_metadata"] = page_meta
            yield Record(id=d["id"], text=d["text"], metadata=meta)


@click.command()
@click.option(
    "--input",
    "input_path",
    type=click.Path(path_type=Path),
    default=Path("output_DEV.json"),
    show_default=True,
    help="Path to input JSON/JSONL.",
)
@click.option(
    "--model",
    default="text-embedding-3-small",
    show_default=True,
    help="Embedding model name (for downstream use).",
)
@click.option("--chunk-size", default=1200, show_default=True, help="Chunk size hint.")
@click.option("--chunk-overlap", default=150, show_default=True, help="Chunk overlap hint.")
@click.option(
    "--normalized-json",
    type=click.Path(path_type=Path),
    default=Path("output_embedding/embedding.json"),
    show_default=True,
    help="Path to write the normalized graph (models/prices/disclosures/assets/sections/awards).",
)
def main(
    input_path: Path,
    model: str,
    chunk_size: int,
    chunk_overlap: int,
    normalized_json: Path,
) -> None:
    """Build a normalized graph from Chevy's semantic JSON.

    The script reads a semantic JSON or JSONL dump produced by the scraper
    and writes a single normalized graph JSON at `--normalized-json` for
    inspection and use by the agent.
    """
    cfg = EmbeddingConfig(
        model=model,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        id_prefix="chevy",
    )
    # Validate input and proceed without writing JSONL
    embedder = ChevyEmbedder(input_path=input_path, output_path=Path("/dev/null"), config=cfg)
    _ = embedder.load_input()
    click.echo("Building normalized graph…")

    # Also emit the normalized graph for inspection/use
    data = embedder.load_input()
    graph = embedder.normalize_all(data)
    normalized_json.parent.mkdir(parents=True, exist_ok=True)
    normalized_json.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    click.echo(f"Wrote normalized graph: {normalized_json}")


if __name__ == "__main__":
    main()
