"""
Chevrolet Silverado 1500 embedding builder.

Reads a semantic JSON/JSONL dump and writes:
- JSONL (id, text, metadata, embedding=None) unless --skip-jsonl
- Normalized graph JSON for downstream use
"""

from __future__ import annotations

from pathlib import Path
import json

import click

from embedding.embedding import EmbeddingConfig
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
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=Path("embeddings/chevy_embeddings.jsonl"),
    show_default=True,
    help="Path to write JSONL embedding table.",
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
@click.option(
    "--skip-jsonl",
    is_flag=True,
    default=False,
    help="Skip writing the JSONL table and only write the normalized graph.",
)
def main(
    input_path: Path,
    output_path: Path,
    model: str,
    chunk_size: int,
    chunk_overlap: int,
    normalized_json: Path,
    skip_jsonl: bool,
) -> None:
    """Build a JSONL embedding table from Chevy's semantic JSON.

    The script reads a semantic JSON/JSONL dump produced by the scraper and
    writes two artifacts:
    - A JSONL embedding table at `--output` with rows: id, text, metadata, embedding=None
    - A normalized graph JSON at `--normalized-json` for inspection/reuse
    """
    cfg = EmbeddingConfig(
        model=model,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        id_prefix="chevy",
    )
    embedder = ChevyEmbedder(input_path=input_path, output_path=output_path, config=cfg)
    if skip_jsonl:
        # Build table but do not write JSONL
        _ = embedder.load_input()  # ensure file exists/valid
        click.echo("Skipping JSONL output as requested (--skip-jsonl).")
    else:
        out = embedder.run()
        click.echo(f"Wrote embedding table: {out}")

    # Also emit the normalized graph for inspection/use
    data = embedder.load_input()
    graph = embedder.normalize_all(data)
    normalized_json.parent.mkdir(parents=True, exist_ok=True)
    normalized_json.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    click.echo(f"Wrote normalized graph: {normalized_json}")


if __name__ == "__main__":
    main()
