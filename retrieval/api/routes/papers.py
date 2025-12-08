"""
Paper metadata endpoints

Handles retrieval of paper metadata and details.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


class PaperMetadata(BaseModel):
    """Paper metadata model"""

    id: int
    arxiv_id: str
    title: str
    authors: list[str]
    summary: str
    published: str | None
    categories: list[str]
    pdf_url: str
    paper_url: str | None = None


class PaperDetail(PaperMetadata):
    """Extended paper detail model"""

    sections: dict | None = None
    references: dict | None = None
    raw_text: str | None = None


@router.get("/{paper_id}", response_model=PaperDetail)
async def get_paper(paper_id: str):
    """
    Get detailed information about a specific paper.

    Retrieves full paper metadata from MySQL database.
    """
    # TODO: Implement paper retrieval
    raise HTTPException(status_code=501, detail="Paper retrieval not yet implemented")


@router.get("/{paper_id}/chunks")
async def get_paper_chunks(paper_id: str):
    """
    Get all chunks for a specific paper.

    Retrieves all vector chunks associated with a paper from Qdrant.
    """
    # TODO: Implement chunk retrieval
    raise HTTPException(status_code=501, detail="Chunk retrieval not yet implemented")


@router.get("/", response_model=list[PaperMetadata])
async def list_papers(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    category: str | None = Query(default=None),
):
    """
    List papers with pagination and optional filtering.

    Returns a paginated list of papers from the database.
    """
    # TODO: Implement paper listing
    raise HTTPException(status_code=501, detail="Paper listing not yet implemented")

