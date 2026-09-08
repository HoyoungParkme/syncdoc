"""앱 조립. SYNC-DOM-002 1장 — web·mcp 라우터 마운트. SYNC-INFRA-001 4.1 경로 구분."""

from fastapi import FastAPI

app = FastAPI(title="SyncDoc")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
