"""
Minimal utilities to build embedding-ready tables.

- EmbeddingConfig: basic settings used downstream when generating vectors
- Record: row structure for embedding tables
- BaseEmbedder: reads input, extracts domain records, writes JSONL
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional


@dataclass
class EmbeddingConfig:
    """Configuration for embedding generation.

    Note: This does not implement actual embedding calls. Subclasses or
    downstream logic can use these settings to generate embeddings.
    """

    model: str = "text-embedding-3-small"
    dimension: Optional[int] = None
    chunk_size: int = 1200
    chunk_overlap: int = 150
    id_prefix: str = "doc"
    metadata_keys: Optional[List[str]] = None


@dataclass
class Record:
    """Single row in an embedding table."""

    id: str
    text: str
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None  # placeholder; to be filled later


class BaseEmbedder:
    """Base class to turn source data into an embedding table.

    Subclasses should implement `extract_records`.
    """

    def __init__(
        self,
        input_path: str | Path,
        output_path: str | Path,
        config: Optional[EmbeddingConfig] = None,
    ):
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)
        self.config = config or EmbeddingConfig()

    def run(self) -> Path:
        """Read input, extract records, write JSONL. Returns output path."""
        data = self.load_input()
        table = list(self.build_table(data))
        self.write_output(table)
        return self.output_path

    def extract_records(
        self, item: Dict[str, Any], index: int
    ) -> Iterable[Record]:
        """Yield `Record` objects from one domain item (override in subclasses)."""
        raise NotImplementedError

    def load_input(self) -> Any:
        """Load JSON or JSONL from `self.input_path`. Detects array vs JSONL."""
        if not self.input_path.exists():
            raise FileNotFoundError(f"Input not found: {self.input_path}")

        with self.input_path.open("r", encoding="utf-8") as f:
            head = f.read(1)
            f.seek(0)
            if head == "[":
                return json.load(f)
            else:
                return [json.loads(line) for line in f if line.strip()]

    def write_output(self, table: List[Record]) -> None:
        """Writes records as JSON Lines.

        Each line is a dict with keys: id, text, metadata, embedding.
        """
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("w", encoding="utf-8") as f:
            for rec in table:
                f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")

    def build_table(self, data: Any) -> Iterator[Record]:
        """Iterate input data and yield records via `extract_records`."""
        if isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    yield from self.extract_records(item, i)
        elif isinstance(data, dict):
            yield from self.extract_records(data, 0)

    def new_id(self, *parts: Any) -> str:
        """Create id prefixed with config.id_prefix, with fallback UUID suffix."""
        prefix = self.config.id_prefix
        tail = "-".join(str(p) for p in parts if p is not None and str(p) != "")
        if not tail:
            tail = uuid.uuid4().hex[:8]
        return f"{prefix}:{tail}"

    @staticmethod
    def extract_text_blobs(value: Any, preferred_keys: Optional[List[str]] = None, max_len: int = 20_000) -> str:
        """Recursively extract readable text from nested structures; truncate to `max_len`."""
        keys = preferred_keys or [
            "text",
            "title",
            "heading",
            "label",
            "alt",
            "name",
            "ariaLabel",
            "description",
            "contentText",
        ]

        def _walk(obj: Any) -> List[str]:
            out: List[str] = []
            if obj is None:
                return out
            if isinstance(obj, str):
                s = obj.strip()
                if s:
                    out.append(s)
                return out
            if isinstance(obj, (int, float)):
                out.append(str(obj))
                return out
            if isinstance(obj, dict):
                for k in keys:
                    if k in obj:
                        out.extend(_walk(obj[k]))
                for k, v in obj.items():
                    if k in keys:
                        continue
                    if isinstance(v, (str, int, float)):
                        out.extend(_walk(v))
                    elif isinstance(v, (dict, list)):
                        out.extend(_walk(v))
                return out
            if isinstance(obj, list):
                for el in obj:
                    out.extend(_walk(el))
                return out
            return out

        text = "\n".join(_walk(value))
        if len(text) > max_len:
            text = text[:max_len] + "…"
        return text
