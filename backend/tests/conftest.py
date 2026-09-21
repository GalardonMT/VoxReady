"""Test fixtures: SQLite database, seeded demo data, ASGI test client."""
import os
from pathlib import Path

import httpx
import pytest_asyncio

_TMP = Path(__file__).parent / ".tmp"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP.as_posix()}/test.db"
os.environ["DEV_AUTH"] = "true"
os.environ["DEV_AUTH_SECRET"] = "test-secret"
os.environ["STORAGE_DIR"] = (_TMP / "storage").as_posix()
os.environ["UPLOAD_SIGNING_SECRET"] = "test-upload-secret"
os.environ["ANALYSIS_STEP_SECONDS"] = "0.02"
os.environ["ENABLE_RETENTION_JOB"] = "false"
os.environ["WEBHOOK_ENDPOINTS"] = ""

from app import db as db_module  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.core.storage import init_storage  # noqa: E402
from app.main import app  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.seed import seed_data  # noqa: E402

VOCERO_EMAIL = "vocero@demo.voxready.io"
ADMIN_EMAIL = "admin@demo.voxready.io"
MASTER_EMAIL = "master@voxready.io"


@pytest_asyncio.fixture
async def client():
    _TMP.mkdir(exist_ok=True)
    get_settings.cache_clear()
    engine = db_module.init_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with db_module.new_session() as session:
        await seed_data(session)
    init_storage(get_settings())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as test_client:
            yield test_client
    await engine.dispose()


async def token_for(client: httpx.AsyncClient, email: str) -> str:
    response = await client.post("/v1/dev/token", json={"email": email})
    assert response.status_code == 200, response.text
    return response.json()["accessToken"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
