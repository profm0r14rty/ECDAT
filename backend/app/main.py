import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.routers.scans import router as scans_router

app = FastAPI()

_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
_cors_origins = _DEV_ORIGINS
_custom_origins = os.environ.get("CORS_ORIGINS")
if _custom_origins:
    _cors_origins = [
        origin.strip() for origin in _custom_origins.split(",") if origin.strip()
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scans_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}