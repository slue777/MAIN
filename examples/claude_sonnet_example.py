#!/usr/bin/env python
"""
RAG-Anything with Claude Sonnet (LLM + vision) and OpenAI embeddings.

What this shows
---------------
RAG-Anything's model hooks are pluggable, so you can run the LLM and vision
steps on Claude while getting embeddings from OpenAI. This matters because
**Anthropic has no embeddings API** — Claude handles text and vision, but
vectors must come from elsewhere (here, OpenAI's `text-embedding-3-small`).

Model routing:
  * llm_model_func    -> Claude Sonnet 5.5 (claude-sonnet-5-5)
  * vision_model_func -> Claude Sonnet 5.5 (multimodal; images via base64)
  * embedding_func    -> OpenAI text-embedding-3-small

Keys (read from the environment / .env):
  * ANTHROPIC_API_KEY   (required — LLM + vision)
  * OPENAI_API_KEY      (required — embeddings only)
  * OPENAI_BASE_URL     (optional — e.g. an Azure/compatible gateway)

This uses insert_content_list(), so it needs no document parser (MinerU) and
no model downloads — only the two API keys. Run:

    python examples/claude_sonnet_example.py

If you only want to check wiring without spending tokens, set
RAGANYTHING_DRY_RUN=1 to construct everything and skip the API calls.
"""

import asyncio
import base64
import logging
import os
import sys
from functools import partial
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env", override=False)

from anthropic import AsyncAnthropic
from lightrag.llm.anthropic import anthropic_complete_if_cache
from lightrag.llm.openai import openai_embed
from lightrag.utils import EmbeddingFunc
from raganything import RAGAnything, RAGAnythingConfig

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("claude_sonnet_demo")

# Claude Sonnet 5.5. `max_tokens` is required by the Anthropic API and the
# LightRAG binding doesn't set a default, so we pass it through here.
LLM_MODEL = "claude-sonnet-5-5"
ANTHROPIC_MAX_TOKENS = 8000

# OpenAI embeddings. text-embedding-3-small is 1536-dim.
EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536


def build_llm_func(anthropic_api_key, anthropic_base_url=None):
    """Text LLM via LightRAG's Anthropic binding (handles LightRAG conventions
    like keyword_extraction and response caching). Signature matches what
    RAGAnything/LightRAG call."""

    def llm_model_func(prompt, system_prompt=None, history_messages=None, **kwargs):
        kwargs.setdefault("max_tokens", ANTHROPIC_MAX_TOKENS)
        return anthropic_complete_if_cache(
            LLM_MODEL,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages or [],
            api_key=anthropic_api_key,
            base_url=anthropic_base_url,
            **kwargs,
        )

    return llm_model_func


def build_vision_func(anthropic_api_key, anthropic_base_url=None):
    """Vision via the Anthropic SDK directly (Claude is multimodal). Falls back
    to the text path when no image is supplied."""
    client = AsyncAnthropic(api_key=anthropic_api_key, base_url=anthropic_base_url)
    text_func = build_llm_func(anthropic_api_key, anthropic_base_url)

    async def vision_model_func(
        prompt,
        system_prompt=None,
        history_messages=None,
        image_data=None,
        messages=None,
        **kwargs,
    ):
        # VLM-enhanced query path may pass pre-built messages.
        if messages:
            resp = await client.messages.create(
                model=LLM_MODEL, max_tokens=ANTHROPIC_MAX_TOKENS, messages=messages
            )
            return "".join(b.text for b in resp.content if b.type == "text")
        if image_data:
            content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": image_data,
                    },
                },
                {"type": "text", "text": prompt},
            ]
            resp = await client.messages.create(
                model=LLM_MODEL,
                max_tokens=ANTHROPIC_MAX_TOKENS,
                system=system_prompt or "",
                messages=[{"role": "user", "content": content}],
            )
            return "".join(b.text for b in resp.content if b.type == "text")
        # No image: delegate to the text LLM (await its coroutine).
        return await text_func(prompt, system_prompt, history_messages, **kwargs)

    return vision_model_func


SAMPLE_CONTENT = [
    {
        "type": "text",
        "text": (
            "RAG-Anything is an all-in-one multimodal RAG framework built on "
            "LightRAG. LLM and vision calls here are served by Claude Sonnet, "
            "while embeddings come from OpenAI because Anthropic exposes no "
            "embeddings endpoint."
        ),
        "page_idx": 0,
    },
    {
        "type": "table",
        "table_body": (
            "| Role | Provider |\n"
            "|------|----------|\n"
            "| LLM | Claude Sonnet 5.5 |\n"
            "| Vision | Claude Sonnet 5.5 |\n"
            "| Embedding | OpenAI text-embedding-3-small |"
        ),
        "table_caption": ["Table 1: Model routing in this example"],
        "page_idx": 1,
    },
    {
        "type": "text",
        "text": (
            "The default document parser is MinerU; on Python 3.14 the Docling "
            "parser is recommended because MinerU does not support 3.14."
        ),
        "page_idx": 2,
    },
]


async def main():
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    openai_base = os.getenv("OPENAI_BASE_URL")
    dry_run = os.getenv("RAGANYTHING_DRY_RUN") == "1"

    missing = [n for n, v in [("ANTHROPIC_API_KEY", anthropic_key),
                              ("OPENAI_API_KEY", openai_key)] if not v]
    if missing and not dry_run:
        log.error("Missing env var(s): %s", ", ".join(missing))
        log.error("Set them (or use a .env file), or run with RAGANYTHING_DRY_RUN=1 "
                  "to only check wiring.")
        sys.exit(1)

    embedding_func = EmbeddingFunc(
        embedding_dim=EMBED_DIM,
        max_token_size=8192,
        func=partial(openai_embed.func, model=EMBED_MODEL,
                     api_key=openai_key, base_url=openai_base),
    )

    rag = RAGAnything(
        config=RAGAnythingConfig(
            working_dir="./rag_storage_claude",
            enable_image_processing=True,
            enable_table_processing=True,
            enable_equation_processing=True,
        ),
        llm_model_func=build_llm_func(anthropic_key, os.getenv("ANTHROPIC_BASE_URL")),
        vision_model_func=build_vision_func(anthropic_key, os.getenv("ANTHROPIC_BASE_URL")),
        embedding_func=embedding_func,
    )
    log.info("RAGAnything constructed: LLM/vision=%s, embeddings=%s", LLM_MODEL, EMBED_MODEL)

    if dry_run:
        log.info("RAGANYTHING_DRY_RUN=1 — wiring OK, skipping API calls. Done.")
        return

    log.info("Inserting %d content items...", len(SAMPLE_CONTENT))
    await rag.insert_content_list(
        content_list=SAMPLE_CONTENT,
        file_path="model_routing_overview.pdf",
        doc_id="claude-demo-001",
        display_stats=True,
    )

    for q in [
        "Which model serves the LLM and vision calls, and where do embeddings come from?",
        "Why are embeddings not served by Claude?",
        "Which parser should be used on Python 3.14?",
    ]:
        print("\n" + "=" * 78)
        print(f"Q: {q}")
        answer = await rag.aquery(q, mode="hybrid")
        print(answer)


if __name__ == "__main__":
    asyncio.run(main())
