from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from booking_agent.bookings.catalog import Business, describe_hours
from booking_agent.rag.embeddings import cosine, embed, tokenize
from booking_agent.rag.store import ChromaVectorStore, PgVectorStore, VectorStore


@dataclass(frozen=True)
class FaqItem:
    id: str
    title: str
    tags: tuple[str, ...]
    questions: tuple[str, ...]
    answer: str

    def embed_text(self) -> str:
        return " ".join((self.title, " ".join(self.tags), " ".join(self.questions), self.answer))


class KnowledgeBase:
    def __init__(
        self,
        items: list[FaqItem],
        store: VectorStore,
        dims: int,
        threshold: float,
    ) -> None:
        self._items = {item.id: item for item in items}
        self._store = store
        self._dims = dims
        self._threshold = threshold
        self.chunk_count = len(items)
        self._vectors: dict[str, list[float]] = {}

    def index(self) -> None:
        items = list(self._items.values())
        vectors = [embed(item.embed_text(), self._dims) for item in items]
        self._vectors = {item.id: vector for item, vector in zip(items, vectors, strict=True)}
        self._store.upsert(
            ids=[item.id for item in items],
            documents=[item.answer for item in items],
            embeddings=vectors,
            metadatas=[{"title": item.title, "tags": ",".join(item.tags)} for item in items],
        )

    def search(self, query: str) -> dict[str, Any]:
        query_vector = embed(query, self._dims)
        hits = self._store.query(query_vector, k=max(8, len(self._items)))
        tokens = set(tokenize(query))
        ranked: list[tuple[float, int, str]] = []
        for hit in hits:
            tags = [tag for tag in hit.metadata.get("tags", "").split(",") if tag]
            overlap = len(tokens & set(tags))
            if hit.id in self._vectors:
                similarity = cosine(query_vector, self._vectors[hit.id])
            else:
                similarity = hit.cosine
            ranked.append((similarity + 0.2 * overlap, overlap, hit.id))
        ranked.sort(reverse=True)
        if not ranked:
            return {"ok": True, "matched": False, "results": []}
        score, overlap, item_id = ranked[0]
        if overlap == 0 and score < self._threshold:
            return {"ok": True, "matched": False, "results": []}
        item = self._items[item_id]
        return {
            "ok": True,
            "matched": True,
            "results": [
                {
                    "id": item.id,
                    "title": item.title,
                    "answer": item.answer,
                    "score": round(score, 3),
                }
            ],
        }


def load_faq(knowledge_dir: Path, business: Business) -> list[FaqItem]:
    raw = yaml.safe_load((knowledge_dir / "faq.yaml").read_text(encoding="utf-8"))
    items = [
        FaqItem(
            id=row["id"],
            title=row["title"],
            tags=tuple(row["tags"]),
            questions=tuple(row["questions"]),
            answer=" ".join(row["answer"].split()),
        )
        for row in raw["items"]
    ]
    items.append(
        FaqItem(
            id="hours",
            title="Hours",
            tags=("hours", "open", "opening", "schedule"),
            questions=(
                "What are your hours?",
                "When are you open?",
                "When do you close?",
            ),
            answer=describe_hours(business),
        )
    )
    return items


def build_knowledge(
    knowledge_dir: Path,
    business: Business,
    backend: str,
    chroma_path: str,
    database_url: str,
    dims: int,
    threshold: float,
) -> KnowledgeBase:
    items = load_faq(knowledge_dir, business)
    store: VectorStore
    if backend == "chroma":
        store = ChromaVectorStore(chroma_path)
    elif backend == "pgvector":
        store = PgVectorStore(database_url, dims)
    else:
        raise ValueError(f"unknown vector backend: {backend}")
    return KnowledgeBase(items, store, dims, threshold)
