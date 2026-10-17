from fastapi import FastAPI

from app.api import items as items_mod

app = FastAPI()
app.include_router(items_mod.router, prefix="/v1")


@app.get("/health")
def health():
    return {"ok": True}
