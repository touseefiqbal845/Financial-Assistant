import hashlib
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from financial_assistant.persistence.tables import DocumentChunk
from financial_assistant.ports.model import Embedder


def parse_document(path: Path, root: Path) -> list[tuple[int, str]]:
    resolved, allowed = path.resolve(), root.resolve()
    if not resolved.is_relative_to(allowed) or resolved.suffix.lower() not in {
        ".md",
        ".txt",
        ".pdf",
    }:
        raise ValueError("Unsupported file or path outside the ingestion root.")
    if resolved.stat().st_size > 2_000_000:
        raise ValueError("Document exceeds the ingestion size limit.")
    if resolved.suffix.lower() == ".pdf":
        reader = PdfReader(resolved)
        if reader.is_encrypted or len(reader.pages) > 100:
            raise ValueError("Encrypted or oversized PDF is not supported.")
        pages = [(index, page.extract_text() or "") for index, page in enumerate(reader.pages, 1)]
    else:
        pages = [(1, resolved.read_text(encoding="utf-8"))]
    if sum(len(content) for _, content in pages) > 100_000:
        raise ValueError("Extracted document exceeds the text limit.")
    return pages


def chunks(pages: list[tuple[int, str]]) -> list[tuple[int, str]]:
    result = []
    for page, content in pages:
        normalized = " ".join(content.split())
        for start in range(0, len(normalized), 1200):
            result.append((page, normalized[start : start + 1400]))
    if not result or len(result) > 80:
        raise ValueError("Document must contain between one and eighty chunks.")
    return result


class Ingestion:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], embedder: Embedder, model: str):
        self.sessions, self.embedder, self.model = sessions, embedder, model

    async def ingest(
        self,
        *,
        tenant_id: str,
        entity: str,
        document_id: str,
        source: str,
        period: str,
        pages: list[tuple[int, str]],
    ) -> int:
        pieces = chunks(pages)
        version = hashlib.sha256(repr((pieces, self.model, 1536)).encode()).hexdigest()
        async with self.sessions() as session:
            existing = (
                await session.scalars(
                    select(DocumentChunk).where(
                        DocumentChunk.tenant_id == tenant_id,
                        DocumentChunk.entity == entity,
                        DocumentChunk.document_id == document_id,
                    )
                )
            ).all()
            if (
                existing
                and all(row.version == version for row in existing)
                and len(existing) == len(pieces)
            ):
                return 0
        vectors = []
        for offset in range(0, len(pieces), 16):
            vectors.extend(
                await self.embedder.embed([text for _, text in pieces[offset : offset + 16]])
            )
        async with self.sessions.begin() as session:
            if session.bind is not None and session.bind.dialect.name == "postgresql":
                from sqlalchemy import text

                await session.execute(
                    text(
                        "SELECT set_config('app.tenant_id', :tenant, true), set_config('app.entity_id', :entity, true)"
                    ),
                    {"tenant": tenant_id, "entity": entity},
                )
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                    {"key": f"{tenant_id}:{entity}:{document_id}"},
                )
            await session.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.tenant_id == tenant_id,
                    DocumentChunk.entity == entity,
                    DocumentChunk.document_id == document_id,
                )
            )
            for index, ((page, content), vector) in enumerate(zip(pieces, vectors, strict=True)):
                if len(vector) != 1536:
                    raise ValueError("Embedding dimensions do not match the schema.")
                identity = hashlib.sha256(
                    f"{tenant_id}:{entity}:{document_id}:{version}:{index}".encode()
                ).hexdigest()
                session.add(
                    DocumentChunk(
                        id=identity,
                        tenant_id=tenant_id,
                        entity=entity,
                        document_id=document_id,
                        chunk_index=index,
                        period=period,
                        source=source,
                        page=page,
                        content=content,
                        version=version,
                        embedding_model=self.model,
                        embedding=vector,
                    )
                )
        return len(pieces)
