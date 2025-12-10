"""
RAG endpoints

Handles RAG (Retrieval-Augmented Generation) queries.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional

from retrieval.services.rag import RAGService
from retrieval.services.query_simplifier import QuerySimplifier
from retrieval.config import settings
from retrieval.utils.logger import logger

router = APIRouter()

# Initialize RAG service (singleton pattern)
_rag_service: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """Get or create RAG service instance"""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service


class RAGRequest(BaseModel):
    """RAG query request model"""

    query: str = Field(..., description="User query/question")
    top_k: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Number of chunks to retrieve"
    )
    simplify_query: bool = Field(
        default=True,
        description="Enable query simplification"
    )
    filter_categories: Optional[List[str]] = Field(
        default=None,
        description="Filter by arXiv categories"
    )
    filter_paper_id: Optional[str] = Field(
        default=None,
        description="Filter by specific paper ID"
    )
    temperature: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="LLM temperature override"
    )
    max_tokens: Optional[int] = Field(
        default=None,
        ge=1,
        description="Maximum response tokens"
    )
    llm_provider: Optional[str] = Field(
        default=None,
        description="Override default LLM provider"
    )


class Source(BaseModel):
    """Source citation model"""

    paper_id: str
    paper_url: str
    chunk_id: str
    relevance_score: float
    categories: List[str]


class RAGResponse(BaseModel):
    """RAG query response model"""

    response: str = Field(..., description="Generated answer")
    sources: List[Source] = Field(..., description="Source citations")
    simplified_queries: Optional[List[str]] = Field(
        default=None,
        description="Simplified queries used for search"
    )
    metadata: dict = Field(..., description="Additional metadata")


@router.post("/query", response_model=RAGResponse)
async def rag_query(request: RAGRequest):
    """
    Execute RAG query flow.
    
    This endpoint:
    1. Simplifies the query (if enabled) using LLM inference
    2. Searches Qdrant for relevant chunks using semantic search
    3. Generates a response using the original query and retrieved chunks
    
    Args:
        request: RAG query request
        
    Returns:
        RAG response with answer, sources, and metadata
    """
    try:
        rag_service = get_rag_service()
        
        # Override LLM provider if specified (and not empty)
        # Only override if a valid provider name is provided
        if request.llm_provider:
            provider_value = request.llm_provider.strip() if isinstance(request.llm_provider, str) else str(request.llm_provider)
            if provider_value:  # Only proceed if not empty after stripping
                logger.info(f"Overriding LLM provider to: {provider_value}")
                from retrieval.services.llm import LLMService
                llm_service = LLMService(provider=provider_value)
                rag_service = RAGService(
                    llm_service=llm_service,
                    embedding_service=rag_service.embedding_service,
                    qdrant_service=rag_service.qdrant_service,
                    query_simplifier=QuerySimplifier(llm_service=llm_service),
                )
            else:
                logger.debug("llm_provider was provided but empty, using default")
        else:
            logger.debug(f"Using default LLM provider: {settings.LLM_PROVIDER}")
        
        result = rag_service.query(
            query=request.query,
            top_k=request.top_k,
            simplify_query=request.simplify_query,
            filter_categories=request.filter_categories,
            filter_paper_id=request.filter_paper_id,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        
        return RAGResponse(**result)
        
    except Exception as e:
        logger.error(f"Error in RAG query endpoint: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"RAG query failed: {str(e)}")


@router.get("/health")
async def rag_health():
    """Health check for RAG service"""
    try:
        rag_service = get_rag_service()
        # Try to access services to verify they're initialized
        _ = rag_service.llm_service
        _ = rag_service.embedding_service
        _ = rag_service.qdrant_service
        return {"status": "healthy", "llm_provider": settings.LLM_PROVIDER}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

