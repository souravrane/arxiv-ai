"""
API routes module
"""

from fastapi import APIRouter

from retrieval.api.routes import search, papers, rag

router = APIRouter()

# Include route modules
router.include_router(search.router, prefix="/search", tags=["search"])
router.include_router(papers.router, prefix="/papers", tags=["papers"])
router.include_router(rag.router, prefix="/rag", tags=["rag"])

