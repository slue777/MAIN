#!/usr/bin/env python
"""
Minimal OFFLINE RAG-Anything example — no API key, no network, no MinerU.

Why this exists
---------------
A normal RAG-Anything run calls an LLM (OpenAI by default) for entity/relation
extraction and answer generation, an embedding API for vectors, and MinerU to
parse documents. This script replaces the first two with tiny *local* stub
functions and skips parsing by feeding pre-structured content through
`insert_content_list()`. That lets you watch the real pipeline run end to end
with zero external dependencies:

  * content is chunked and written to the on-disk store,
  * chunks are embedded with a deterministic local (feature-hashing) embedder,
  * a `naive` query embeds the question, does a real cosine-similarity search
    over the stored chunks, and the stub "LLM" answers from what was retrieved.

Graph-based modes (local/global/hybrid) need a real LLM to extract entities,
so they stay shallow here on purpose. Swap the two stub functions for real
OpenAI ones (see examples/insert_content_list_example.py) and everything else
works unchanged. The point of this file is to prove the install and the
retrieval machinery, offline.
"""

import asyncio
import hashlib
import logging
import re
import sys
from pathlib import Path

import numpy as np

sys.path.append(str(Path(__file__).parent.parent))

from lightrag.utils import EmbeddingFunc  # noqa: E402
from raganything import RAGAnything, RAGAnythingConfig  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("offline_demo")

EMBED_DIM = 256


# --------------------------------------------------------------------------- #
# Local deterministic embedding: feature hashing + L2 normalization.          #
# Token hashed into a bucket; counts form the vector. Gives real, repeatable  #
# cosine similarity with no model and no network.                             #
# --------------------------------------------------------------------------- #
def _embed_one(text: str) -> np.ndarray:
    vec = np.zeros(EMBED_DIM, dtype=np.float32)
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % EMBED_DIM] += 1.0
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


async def local_embed(texts):
    return np.array([_embed_one(t) for t in texts], dtype=np.float32)


# --------------------------------------------------------------------------- #
# Stub "LLM": no model. For answer generation it pulls the retrieved document #
# chunks out of LightRAG's RAG prompt and returns them, so you can see what   #
# retrieval surfaced for the question. For extraction/keyword calls it returns #
# an empty result (fine for `naive` mode, which doesn't use the graph).        #
# --------------------------------------------------------------------------- #
async def stub_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
    if kwargs.get("keyword_extraction"):
        return '{"high_level_keywords": [], "low_level_keywords": []}'

    # Answer path: LightRAG embeds the retrieved chunks inside the prompt.
    # Grab the most informative lines to show what was retrieved.
    lines = [ln.strip() for ln in prompt.splitlines() if len(ln.strip()) > 40]
    # Prefer lines that look like real content, not prompt scaffolding.
    content = [ln for ln in lines if not ln.lower().startswith(("you ", "---", "role", "below", "given"))]
    picked = content[:4] if content else lines[:4]
    if not picked:
        return "[stub LLM] No context was retrieved for this question."
    body = "\n  - ".join(picked)
    return f"[stub LLM — answer assembled from retrieved context]\n  - {body}"


async def stub_vision(prompt, system_prompt=None, history_messages=None, image_data=None, messages=None, **kwargs):
    return "[stub vision model — image understanding disabled offline]"


SAMPLE_CONTENT = [
    {
        "type": "text",
        "text": (
            "RAG-Anything is an all-in-one multimodal RAG system built on LightRAG. "
            "It ingests PDFs, Office documents, and images, then answers questions "
            "over a knowledge graph combined with vector retrieval."
        ),
        "page_idx": 0,
    },
    {
        "type": "text",
        "text": (
            "The default parser is MinerU, which extracts text, tables, images, and "
            "equations from documents. An alternative Docling parser is available, "
            "and is the recommended parser on Python 3.14 where MinerU is unsupported."
        ),
        "page_idx": 1,
    },
    {
        "type": "table",
        "table_body": (
            "| Modality | Processor |\n"
            "|----------|-----------|\n"
            "| Text | LightRAG core |\n"
            "| Image | Vision model |\n"
            "| Table | Table processor |\n"
            "| Equation | Equation processor |"
        ),
        "table_caption": ["Table 1: Modality to processor mapping"],
        "page_idx": 2,
    },
    {
        "type": "text",
        "text": (
            "Querying supports several modes: naive does pure vector search over "
            "chunks, while local, global, and hybrid modes use the extracted entity "
            "and relationship graph for richer, multi-hop answers."
        ),
        "page_idx": 3,
    },
]


async def main():
    # Name matches the repo's `rag_storage*/` .gitignore rule, so the runtime
    # store never lands in version control.
    working_dir = Path(__file__).resolve().parent.parent / "rag_storage_offline"
    log.info("Working dir: %s", working_dir)

    config = RAGAnythingConfig(
        working_dir=str(working_dir),
        enable_image_processing=False,
        enable_table_processing=True,
        enable_equation_processing=True,
    )

    rag = RAGAnything(
        config=config,
        llm_model_func=stub_llm,
        vision_model_func=stub_vision,
        embedding_func=EmbeddingFunc(
            embedding_dim=EMBED_DIM,
            max_token_size=8192,
            func=local_embed,
        ),
    )

    log.info("Inserting %d content items (no parsing, no API)...", len(SAMPLE_CONTENT))
    await rag.insert_content_list(
        content_list=SAMPLE_CONTENT,
        file_path="raganything_overview.pdf",
        doc_id="offline-demo-001",
        display_stats=True,
    )
    log.info("Insert complete. On-disk store:")
    for p in sorted(working_dir.glob("*.json")):
        log.info("  %s (%d bytes)", p.name, p.stat().st_size)

    questions = [
        "What is RAG-Anything built on and what can it ingest?",
        "Which parser is recommended on Python 3.14 and why?",
        "What is the difference between naive and hybrid query modes?",
    ]
    for q in questions:
        print("\n" + "=" * 78)
        print(f"Q: {q}")
        answer = await rag.aquery(q, mode="naive")
        print(answer)


if __name__ == "__main__":
    asyncio.run(main())
