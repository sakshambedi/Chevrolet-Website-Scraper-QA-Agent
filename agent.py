from __future__ import annotations

import json
import math
import os
import signal
import sys

# import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv
from rich import box
from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

# Reuse Chevy/GM embedding doc builder to turn normalized graph -> docs
from embedding.chevy_embed import ChevyEmbedder
from embedding.embedding import Record

console = Console()


@dataclass
class IndexedDoc:
    id: str
    text: str
    metadata: Dict[str, Any]
    embedding: List[float]


def load_normalized_graph(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"embedding graph not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_docs_from_graph(graph: Dict[str, Any]) -> List[Record]:
    # Instantiate embedder just to use its _build_docs implementation
    dummy = ChevyEmbedder(input_path=Path("."), output_path=Path("./.ignore"))
    docs = dummy._build_docs(graph)  # type: ignore[attr-defined]
    # Convert to Records (embedding=None placeholder)
    out: List[Record] = []
    for d in docs:
        out.append(Record(id=d["id"], text=d["text"], metadata=d["metadata"], embedding=None))
    return out


def batched(seq: List[Any], size: int) -> List[List[Any]]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def cosine_sim(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0 or nb == 0:
        return -1.0
    return dot / math.sqrt(na * nb)


def get_openai_client():
    # Lazy import to avoid hard dep if not used
    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:
        raise RuntimeError("The 'openai' package is required. Please `pip install openai`.") from e
    # Explicitly pass credentials so .env values are honored and to support project keys
    # Support both standard and admin key env names
    api_key = (
        os.environ.get("OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY_ADMIN")
        or os.environ.get("OPENAI_ADMIN_KEY")
    )
    organization = os.environ.get("OPENAI_ORGANIZATION") or os.environ.get("OPENAI_ORG_ID")
    project = os.environ.get("OPENAI_PROJECT")
    base_url = os.environ.get("OPENAI_BASE_URL")
    # If using a project-scoped key, prefer the project encoded in the key
    # to avoid mismatches with a stale OPENAI_PROJECT env var.
    kwargs = {"api_key": api_key}
    if organization:
        kwargs["organization"] = organization
    # If using an admin/org key, the project must be specified for most endpoints
    if project and not (api_key or "").startswith("sk-proj-"):
        kwargs["project"] = project
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)  # pyright: ignore


def embed_texts(texts: List[str], model: str = "text-embedding-3-small") -> List[List[float]]:
    # def embed_texts(texts: List[str], model: str = "text-embedding-3-small") -> List[List[float]]:
    client = get_openai_client()
    vectors: List[List[float]] = []
    # Batch to respect payload sizes; 100 is safe for small inputs
    for chunk in batched(texts, 100):
        resp = client.embeddings.create(model=model, input=chunk)
        # The SDK returns results in the same order as inputs
        vectors.extend([d.embedding for d in resp.data])  # type: ignore[attr-defined]
    return vectors


def index_from_graph(graph_path: Path, embed_model: str) -> List[IndexedDoc]:
    graph = load_normalized_graph(graph_path)
    docs = build_docs_from_graph(graph)
    if not docs:
        raise RuntimeError("No docs produced from graph; cannot build index.")

    # Prepare texts for embedding
    texts = [d.text for d in docs]

    # Visual loader while embedding
    with Live(
        Spinner("dots", text="Indexing: generating embeddings…"),
        console=console,
        refresh_per_second=16,
    ):
        vectors = embed_texts(texts, model=embed_model)

    indexed: List[IndexedDoc] = []
    for d, v in zip(docs, vectors):
        indexed.append(IndexedDoc(id=d.id, text=d.text, metadata=d.metadata, embedding=v))
    return indexed


def retrieve(
    index: List[IndexedDoc], query: str, embed_model: str, k: int = 5
) -> Tuple[List[IndexedDoc], List[Tuple[int, float]]]:
    q_vec = embed_texts([query], model=embed_model)[0]
    scored: List[Tuple[int, float]] = []
    for i, doc in enumerate(index):
        s = cosine_sim(q_vec, doc.embedding)
        scored.append((i, s))
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:k]
    return [index[i] for i, _ in top], top


def format_context(docs: List[IndexedDoc]) -> str:
    parts: List[str] = []
    for i, d in enumerate(docs, start=1):
        title = d.metadata.get("section_title") or d.metadata.get("doc_type") or "Context"
        src = d.metadata.get("source_url")
        region = d.metadata.get("region")
        doc_type = d.metadata.get("doc_type")
        model = d.metadata.get("model_name")
        meta_bits = []
        if model:
            meta_bits.append(f"model={model}")
        if doc_type:
            meta_bits.append(f"type={doc_type}")
        if region:
            meta_bits.append(f"region={region}")
        idx = d.metadata.get("chunk_index")
        cnt = d.metadata.get("chunk_count")
        if idx and cnt:
            meta_bits.append(f"chunk={idx}/{cnt}")
        header = f"[Doc {i}] {title} — {d.id}"
        if src:
            header += f"\nSource: {src}"
        if meta_bits:
            header += f"\nMeta: {'; '.join(meta_bits)}"
        parts.append(f"{header}\n{d.text}".strip())
    return "\n\n---\n\n".join(parts)


def stream_chat_answer(query: str, context: str, model: str = "gpt-4o-mini") -> str:
    client = get_openai_client()
    system_text = (
        "You are Chevy Q&A Agent. Answer strictly from the provided context. "
        "If the answer is not in context, say: 'Not in the provided context.' "
        "Guidelines: \n"
        "- Be concise and factual.\n"
        "- Preserve units/currency as shown (e.g., CAD $XX,XXX).\n"
        "- For pricing, include region codes and both 'From' and 'As shown' when present.\n"
        "- If disclosures are referenced, add: 'See disclosures.' without inventing details.\n"
        "- Do not speculate or use outside knowledge."
    )
    user_text = (
        "Use the context below to answer the question.\n\n"
        f"Question: {query}\n\n"
        f"Context:\n{context}"
    )

    # Stream tokens to the console
    answer_chunks: List[str] = []
    with Live(console=console, refresh_per_second=20) as live:
        live.update(Panel(Spinner("line", text="Thinking…"), title="AI", border_style="cyan"))
        stream = client.chat.completions.create(
            model=model,
            stream=True,
            messages=[
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ],
        )
        buff = ""
        for chunk in stream:
            try:
                delta = chunk.choices[0].delta.content  # type: ignore[attr-defined]
            except Exception:
                delta = None
            if delta:
                buff += delta
                answer_chunks.append(delta)
                live.update(
                    Panel(
                        Align.left(Text(buff)),
                        title="Answer (streaming)",
                        border_style="green",
                        box=box.ROUNDED,
                    )
                )
        # final render is kept by leaving context manager
    return "".join(answer_chunks)


def render_hits_table(hits: List[IndexedDoc], scores: List[Tuple[int, float]]) -> Table:
    table = Table(title="Top Matches", show_header=True, header_style="bold magenta")
    table.add_column("Rank", justify="right", width=5)
    table.add_column("Similarity", justify="right", width=10)
    table.add_column("Doc Id", overflow="fold")
    table.add_column("Section", overflow="fold")
    table.add_column("Region", justify="center", width=8)
    for i, (doc, (_, score)) in enumerate(zip(hits, scores), start=1):
        sec = str(doc.metadata.get("section_title") or doc.metadata.get("doc_type") or "")
        reg = str(doc.metadata.get("region") or "-")
        table.add_row(str(i), f"{score:.3f}", doc.id, sec, reg)
    return table


def main() -> None:
    # Load only .env (not .env.example); .env overrides existing env vars
    load_dotenv(dotenv_path=Path(".env"), override=True)

    graph_env = os.environ.get("GRAPH_PATH")
    if graph_env:
        graph_path = Path(graph_env).resolve()
    else:
        # Prefer new default location if present
        cand = Path("output_embedding/embedding.json")
        graph_path = cand.resolve() if cand.exists() else Path("embedding.json").resolve()
    embed_model = os.environ.get("EMBED_MODEL", "text-embedding-3-small")
    chat_model = os.environ.get("CHAT_MODEL", "gpt-4o-mini")

    # Quick check for API key (supports admin key env names)
    api_key = (
        os.environ.get("OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY_ADMIN")
        or os.environ.get("OPENAI_ADMIN_KEY")
    )
    if not api_key:
        console.print(
            Panel(
                Text(
                    "No OpenAI API key found. Set `OPENAI_API_KEY` or `OPENAI_API_KEY_ADMIN` in your environment.",
                    style="yellow",
                ),
                title="Warning",
                border_style="yellow",
            )
        )
    else:
        # Hint when using project keys without OPENAI_PROJECT
        key = str(api_key)
        if key.startswith("sk-proj-") and not os.environ.get("OPENAI_PROJECT"):
            console.print(
                Panel(
                    Text(
                        "Detected a project API key (sk-proj-…). Consider setting OPENAI_PROJECT as well to avoid 401.",
                        style="yellow",
                    ),
                    title="Notice",
                    border_style="yellow",
                )
            )
        # Hint when using admin/org keys without OPENAI_PROJECT
        if (key.startswith("sk-admin-") or key.startswith("sk-")) and not key.startswith(
            "sk-proj-"
        ):
            if not os.environ.get("OPENAI_PROJECT"):
                console.print(
                    Panel(
                        Text(
                            "Detected a non-project OpenAI key. Set OPENAI_PROJECT to route requests to a project.",
                            style="yellow",
                        ),
                        title="Notice",
                        border_style="yellow",
                    )
                )

    console.rule("Chevy Q&A Agent")
    console.print(Text(f"Building index from {graph_path.name} using {embed_model}…", style="cyan"))

    try:
        index = index_from_graph(graph_path, embed_model)
    except Exception as e:
        console.print(Panel(str(e), title="Indexing Error", border_style="red"))
        sys.exit(1)

    # Dynamic prompt message based on model in the graph
    model_name = None
    for d in index:
        try:
            model_name = str(d.metadata.get("model_name") or "").strip()
        except Exception:
            model_name = None
        if model_name:
            break
    if model_name:
        ready_text = f"Ready. Ask a question about Chevrolet {model_name}.\nType 'exit' or press Ctrl+C to quit."
    else:
        ready_text = "Ready. Ask a question about Chevrolet vehicles.\nType 'exit' or press Ctrl+C to quit."

    console.print(
        Panel(
            Text(ready_text, style="green"),
            title="Interactive Mode",
            border_style="green",
        )
    )

    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    while True:
        q = Prompt.ask("Your question")
        if not q:
            continue
        if q.strip().lower() in {"quit", "q", "exit"}:
            break

        # Retrieve top docs
        with Live(
            Spinner("dots", text="Searching context…"), console=console, refresh_per_second=18
        ):
            hits, scored = retrieve(index, q, embed_model, k=5)

        console.print(render_hits_table(hits, scored))
        ctx = format_context(hits)

        # Stream answer
        try:
            _ = stream_chat_answer(q, ctx, model=chat_model)
        except Exception as e:
            console.print(Panel(str(e), title="Chat Error", border_style="red"))

        console.rule()


if __name__ == "__main__":
    main()
