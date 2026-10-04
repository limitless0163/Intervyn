"""Assemble the API routes and their access policies."""

from fastapi import APIRouter, Depends

from ..dependencies.auth import require_internal_secret
from .routes import coach, kb, prep, score, session, traces

router = APIRouter()

# Keep the internal-secret gate on write/compute routes. Session reads have a
# capability guard of their own, and trace views remain read-only.
guarded = [Depends(require_internal_secret)]
router.include_router(prep.router, dependencies=guarded)
router.include_router(score.router, dependencies=guarded)
router.include_router(coach.router, dependencies=guarded)
router.include_router(kb.router, dependencies=guarded)
router.include_router(session.router)
router.include_router(traces.router)
