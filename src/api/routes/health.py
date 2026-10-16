"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    """Liveness check — returns ok if the server is up."""
    return {"status": "ok"}
