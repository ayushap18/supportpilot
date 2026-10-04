import asyncio
import json

from sqlalchemy import func, select
from supportpilot.provider import Provider
from supportpilot.retrieval import ChunkRow, Retrieval
from supportpilot.storage import Database


def test_idempotent_ingestion_updates_and_version_filters(settings, tmp_path):
    async def run():
        db = Database(settings.database_url)
        db.initialize()
        provider = Provider(settings)
        retrieval = Retrieval(db, settings, provider)
        await retrieval.ingest()
        await retrieval.ingest()
        with db.session() as session:
            assert session.scalar(select(func.count()).select_from(ChunkRow)) == 11
        results = await retrieval.search("401 MISSING_BEARER X-API-Key", "demo", "v2")
        assert "auth-v2" in {item.id.split(":")[1] for item in results}
        assert all(item.product_version in {"v2", "any"} for item in results)
        assert await retrieval.search("authentication", "other", "v2") == []
        documents = json.loads((settings.data_dir / "documents.json").read_text())
        documents[0]["body"] = "New revised overview"
        documents[0]["revision"] = "2"
        settings.data_dir = tmp_path
        (tmp_path / "documents.json").write_text(json.dumps(documents))
        await retrieval.ingest()
        with db.session() as session:
            row = session.scalar(select(ChunkRow).where(ChunkRow.document_id == "overview"))
            assert row.revision == "2" and row.body == "New revised overview"
            assert session.scalar(select(func.count()).select_from(ChunkRow)) == 11
        db.engine.dispose()

    asyncio.run(run())
