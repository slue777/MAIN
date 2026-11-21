#!/usr/bin/env python
"""
RAG-Anything using ONLY Anthropic — Claude Sonnet for LLM + vision, and a
local (keyless) embedder so no second paid API is needed.

Why a local embedder?
---------------------
Anthropic exposes no embeddings endpoint, so a RAG pipeline that must not
depend on any non-Anthropic *API* has to produce vectors locally. This example
uses a deterministic feature-hashing embedder (no model download, no network,
no key) so the ONLY external dependency is ANTHROPIC_API_KEY. It is meant to
verify the Claude integration end to end without needing OpenAI/Voyage credits.

For production retrieval quality, swap `local_embed` for a real local model
(e.g. sentence-transformers `BAAI/bge-m3`, still keyless) or a hosted embedder
(OpenAI / Voyage, which need their own keys). The LLM/vision wiring is unchanged.

Model routing:
  * llm_model_func    -> Claude Sonnet 5.5 (claude-sonnet-5-5)
  * vision_model_func -> Claude Sonnet 5.5 (multimodal, images via base64)
  * embedding_func    -> local deterministic hash embedder (keyless)

Run (needs ANTHROPIC_API_KEY in the environment):
    export ANTHROPIC_API_KEY=sk-ant-...
    python examples/claude_only_example.py

NOTE on cloud sessions: the Claude API key cannot be a proxy-injected network
secret — it must be a real ANTHROPIC_API_KEY environment variable, which only a
NEW session picks up. Use RAGANYTHING_DRY_RUN=1 to validate wiring (and the
local embedder) without any Claude call.
"""

import asyncio
import hashlib
import logging
import os
import re
import sys
from pathlib import Path

import numpy as np

sys.path.append(str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env", override=False)

from anthropic import AsyncAnthropic
from lightrag.llm.anthropic import anthropic_complete_if_cache
from lightrag.utils import EmbeddingFunc, Tokenizer
from raganything import RAGAnything, RAGAnythingConfig

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("claude_only_demo")

LLM_MODEL = "claude-sonnet-5-5"
ANTHROPIC_MAX_TOKENS = 8000
EMBED_DIM = 256


# --- Keyless local embedder: feature hashing + L2 norm (real cosine sim) ---
def _embed_one(text: str) -> np.ndarray:
    vec = np.zeros(EMBED_DIM, dtype=np.float32)
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        vec[int(hashlib.md5(tok.encode()).hexdigest(), 16) % EMBED_DIM] += 1.0
    n = np.linalg.norm(vec)
    return vec / n if n else vec


async def local_embed(texts):
    return np.array([_embed_one(t) for t in texts], dtype=np.float32)


# --- Network-free tokenizer (LightRAG's tiktoken default downloads its BPE) ---
class _ByteTokenizerImpl:
    def encode(self, content: str):
        return list(content.encode("utf-8"))

    def decode(self, tokens):
        return bytes(t & 0xFF for t in tokens).decode("utf-8", errors="ignore")


OFFLINE_TOKENIZER = Tokenizer(model_name="byte-offline", tokenizer=_ByteTokenizerImpl())


def build_llm_func(api_key, base_url=None):
    def llm_model_func(prompt, system_prompt=None, history_messages=None, **kwargs):
        kwargs.setdefault("max_tokens", ANTHROPIC_MAX_TOKENS)
        return anthropic_complete_if_cache(
            LLM_MODEL, prompt, system_prompt=system_prompt,
            history_messages=history_messages or [],
            api_key=api_key, base_url=base_url, **kwargs,
        )
    return llm_model_func


def build_vision_func(api_key, base_url=None):
    client = AsyncAnthropic(api_key=api_key, base_url=base_url)
    text_func = build_llm_func(api_key, base_url)

    async def vision_model_func(prompt, system_prompt=None, history_messages=None,
                                image_data=None, messages=None, **kwargs):
        if messages:
            resp = await client.messages.create(
                model=LLM_MODEL, max_tokens=ANTHROPIC_MAX_TOKENS, messages=messages)
            return "".join(b.text for b in resp.content if b.type == "text")
        if image_data:
            resp = await client.messages.create(
                model=LLM_MODEL, max_tokens=ANTHROPIC_MAX_TOKENS,
                system=system_prompt or "",
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64",
                     "media_type": "image/jpeg", "data": image_data}},
                    {"type": "text", "text": prompt}]}])
            return "".join(b.text for b in resp.content if b.type == "text")
        return await text_func(prompt, system_prompt, history_messages, **kwargs)
    return vision_model_func


SAMPLE_CONTENT = [
    {"type": "text", "page_idx": 0, "text":
        "RAG-Anything is a multimodal RAG framework built on LightRAG. In this "
        "setup every LLM and vision call is served by Claude Sonnet."},
    {"type": "text", "page_idx": 1, "text":
        "Anthropic has no embeddings API, so embeddings here are produced by a "
        "local keyless embedder, keeping Claude as the only external dependency."},
    {"type": "text", "page_idx": 2, "text":
        "The default document parser is MinerU; on Python 3.14 the Docling parser "
        "is recommended because MinerU does not support 3.14."},
]


async def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    base_url = os.getenv("ANTHROPIC_BASE_URL")
    dry_run = os.getenv("RAGANYTHING_DRY_RUN") == "1"

    if not api_key and not dry_run:
        log.error("ANTHROPIC_API_KEY is not set. Set it (new cloud session required "
                  "for env vars), or run with RAGANYTHING_DRY_RUN=1 to check wiring.")
        sys.exit(1)

    rag = RAGAnything(
        config=RAGAnythingConfig(
            working_dir="./rag_storage_claude_only",
            enable_image_processing=True,
            enable_table_processing=True,
            enable_equation_processing=True,
        ),
        llm_model_func=build_llm_func(api_key, base_url),
        vision_model_func=build_vision_func(api_key, base_url),
        embedding_func=EmbeddingFunc(
            embedding_dim=EMBED_DIM, max_token_size=8192, func=local_embed),
        lightrag_kwargs={
            "tokenizer": OFFLINE_TOKENIZER,
            "chunk_token_size": 200,
            "chunk_overlap_token_size": 30,
        },
    )
    log.info("Constructed: LLM/vision=%s, embeddings=local(keyless)", LLM_MODEL)

    # Prove the local embedder works right here (no key needed).
    vecs = await local_embed(["anthropic only", "local embeddings"])
    log.info("Local embedder OK: shape=%s", np.array(vecs).shape)

    if dry_run:
        log.info("RAGANYTHING_DRY_RUN=1 — wiring + local embedder OK; skipping Claude calls.")
        return

    log.info("Inserting %d content items (Claude will extract entities)...", len(SAMPLE_CONTENT))
    await rag.insert_content_list(
        content_list=SAMPLE_CONTENT,
        file_path="claude_only_overview.pdf",
        doc_id="claude-only-001",
        display_stats=True,
    )

    for q in [
        "Which model serves the LLM and vision calls here?",
        "Why are embeddings produced locally instead of by Anthropic?",
        "Which parser is recommended on Python 3.14?",
    ]:
        print("\n" + "=" * 78)
        print(f"Q: {q}")
        answer = await rag.aquery(q, mode="hybrid")
        print(answer)


if __name__ == "__main__":
    asyncio.run(main())
