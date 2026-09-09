from fastapi import FastAPI

from backend.app.routers.scans import router as scans_router

app = FastAPI()
app.include_router(scans_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}