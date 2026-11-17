from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class VectorHit:
    id: str
    document: str
    metadata: dict[str, str]
    cosine: float


class VectorStore(Protocol):
    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, str]],
    ) -> None: ...

    def query(self, embedding: list[float], k: int) -> list[VectorHit]: ...


class ChromaVectorStore:
    def __init__(self, path: str) -> None:
        import os

        os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
        import chromadb
        from chromadb.config import Settings

        self._client = chromadb.PersistentClient(
            path=path,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name="faq",
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, str]],
    ) -> None:
        self._collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,  # type: ignore[arg-type]
            metadatas=metadatas,  # type: ignore[arg-type]
        )

    def query(self, embedding: list[float], k: int) -> list[VectorHit]:
        if self._collection.count() == 0:
            return []
        raw = self._collection.query(
            query_embeddings=[embedding],  # type: ignore[arg-type]
            n_results=min(k, self._collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        result: dict[str, Any] = raw  # type: ignore[assignment]
        hits: list[VectorHit] = []
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        for item_id, document, metadata, distance in zip(
            ids, documents, metadatas, distances, strict=True
        ):
            meta = {str(key): str(value) for key, value in (metadata or {}).items()}
            hits.append(
                VectorHit(
                    id=str(item_id),
                    document=str(document),
                    metadata=meta,
                    cosine=1.0 - float(distance),
                )
            )
        return hits


class PgVectorStore:
    """Postgres + pgvector. Used when VECTOR_BACKEND=pgvector."""

    def __init__(self, database_url: str, dims: int) -> None:
        self._dsn = _psycopg_dsn(database_url)
        self._dims = dims
        self._ready = False

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, str]],
    ) -> None:
        self._ensure()
        import psycopg

        with psycopg.connect(self._dsn) as conn:
            _register(conn)
            for item_id, document, embedding, metadata in zip(
                ids, documents, embeddings, metadatas, strict=True
            ):
                tags = metadata.get("tags", "")
                title = metadata.get("title", "")
                conn.execute(
                    """
                    INSERT INTO faq_chunks (id, document, title, tags, embedding)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET document = EXCLUDED.document,
                        title = EXCLUDED.title,
                        tags = EXCLUDED.tags,
                        embedding = EXCLUDED.embedding
                    """,
                    (item_id, document, title, tags, embedding),
                )

    def query(self, embedding: list[float], k: int) -> list[VectorHit]:
        self._ensure()
        import psycopg

        with psycopg.connect(self._dsn) as conn:
            _register(conn)
            rows = conn.execute(
                """
                SELECT id, document, title, tags,
                       1 - (embedding <=> %s) AS cosine
                FROM faq_chunks
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                (embedding, embedding, k),
            ).fetchall()
        return [
            VectorHit(
                id=row[0],
                document=row[1],
                metadata={"title": row[2], "tags": row[3]},
                cosine=float(row[4]),
            )
            for row in rows
        ]

    def _ensure(self) -> None:
        if self._ready:
            return
        import psycopg

        with psycopg.connect(self._dsn) as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS faq_chunks (
                    id text PRIMARY KEY,
                    document text NOT NULL,
                    title text NOT NULL,
                    tags text NOT NULL,
                    embedding vector({self._dims}) NOT NULL
                )
                """
            )
        self._ready = True


def _psycopg_dsn(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg://"):
        return "postgresql://" + database_url.removeprefix("postgresql+psycopg://")
    if database_url.startswith("postgres://") or database_url.startswith("postgresql://"):
        return database_url
    raise ValueError("pgvector backend needs a postgresql DATABASE_URL")


def _register(conn: Any) -> None:
    from pgvector.psycopg import register_vector

    register_vector(conn)
