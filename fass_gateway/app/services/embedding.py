from __future__ import annotations

import asyncio
from functools import lru_cache

import httpx

from ..settings import settings


@lru_cache(maxsize=1)
def _load_model():
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as e:
        raise RuntimeError("sentence-transformers is required for local embedding") from e
    return SentenceTransformer(settings.embedding_model_path)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if settings.embedding_provider == "local":
        model = await asyncio.to_thread(_load_model)
        vectors = await asyncio.to_thread(model.encode, texts, normalize_embeddings=True)
        return [v.tolist() for v in vectors]

    if settings.embedding_provider == "openai_compat":
        async with httpx.AsyncClient(timeout=120) as client:
            headers = {}
            if settings.llm_api_key:
                headers["Authorization"] = f"Bearer {settings.llm_api_key}"
            model = settings.embedding_model or settings.llm_model or "default"
            base = settings.llm_base_url.rstrip("/")
            resp = await client.post(f"{base}/v1/embeddings", headers=headers, json={"model": model, "input": texts})
            if resp.status_code == 404:
                vectors: list[list[float]] = []
                for t in texts:
                    r2 = await client.post(f"{base}/api/embeddings", headers=headers, json={"model": model, "prompt": t})
                    r2.raise_for_status()
                    vectors.append((r2.json() or {}).get("embedding") or [])
                return vectors
            resp.raise_for_status()
            data = resp.json()
            return [x["embedding"] for x in data.get("data") or []]

    raise RuntimeError(f"unsupported embedding_provider: {settings.embedding_provider}")

