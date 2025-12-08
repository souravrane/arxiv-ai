"""
RAG (Retrieval-Augmented Generation) Service

Orchestrates the complete RAG flow:
1. Query simplification
2. Semantic search
3. Response generation
"""

import time
from typing import Dict, List, Optional

from retrieval.services.llm import LLMService
from retrieval.services.query_simplifier import QuerySimplifier
from retrieval.services.embedding import EmbeddingService
from retrieval.services.qdrant_client import QdrantService
from retrieval.config import settings
from retrieval.utils.logger import logger


class RAGService:
    """Service for RAG operations"""

    def __init__(
        self,
        llm_service: Optional[LLMService] = None,
        embedding_service: Optional[EmbeddingService] = None,
        qdrant_service: Optional[QdrantService] = None,
        query_simplifier: Optional[QuerySimplifier] = None,
    ):
        """
        Initialize RAG service.
        
        Args:
            llm_service: Optional LLM service instance
            embedding_service: Optional embedding service instance
            qdrant_service: Optional Qdrant service instance
            query_simplifier: Optional query simplifier instance
        """
        self.llm_service = llm_service or LLMService()
        self.embedding_service = embedding_service or EmbeddingService()
        self.qdrant_service = qdrant_service or QdrantService()
        self.query_simplifier = query_simplifier or QuerySimplifier(llm_service=self.llm_service)
        self.response_prompt_template = self._load_response_prompt()

    def _load_response_prompt(self) -> str:
        """Load RAG response prompt template"""
        try:
            from pathlib import Path
            prompt_path = Path(__file__).parent.parent / "prompts" / "rag_response.txt"
            if prompt_path.exists():
                return prompt_path.read_text()
        except Exception as e:
            logger.warning(f"Could not load response prompt template: {e}")
        
        # Fallback template
        return """You are an AI assistant answering questions about research papers.

Use ONLY the information in the context chunks below. Cite sources using [Paper: {title}]({url}).

Context:
{context_chunks}

Question: {query}

Answer:"""

    def query(
        self,
        query: str,
        top_k: int = 10,
        simplify_query: bool = True,
        filter_categories: Optional[List[str]] = None,
        filter_paper_id: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict:
        """
        Execute RAG query flow.
        
        Args:
            query: Original user query
            top_k: Number of chunks to retrieve
            simplify_query: Whether to simplify the query first
            filter_categories: Optional category filter
            filter_paper_id: Optional paper ID filter
            temperature: LLM temperature override
            max_tokens: Max tokens override
            
        Returns:
            Dictionary with response, sources, and metadata
        """
        start_time = time.time()
        
        try:
            # Step 1: Query Simplification
            simplified_queries = [query]
            simplification_result = None
            
            if simplify_query and settings.QUERY_SIMPLIFICATION_ENABLED:
                logger.info("Simplifying query...")
                simplification_result = self.query_simplifier.simplify(query)
                simplified_queries = simplification_result.get("simplified_queries", [query])
                logger.info(f"Simplified into {len(simplified_queries)} queries: {simplified_queries}")
            
            # Step 2: Generate embeddings and search
            logger.info("Generating embeddings and searching...")
            all_chunks = []
            seen_chunk_ids = set()
            
            for simplified_query in simplified_queries:
                # Generate embedding
                query_embedding = self.embedding_service.generate_embedding(simplified_query)
                
                # Build filter conditions
                filter_conditions = {}
                if filter_categories:
                    filter_conditions["categories"] = filter_categories
                if filter_paper_id:
                    filter_conditions["paper_id"] = filter_paper_id
                
                # Search Qdrant
                search_results = self.qdrant_service.search(
                    query_vector=query_embedding,
                    top_k=top_k,
                    filter_conditions=filter_conditions if filter_conditions else None,
                )
                
                # Deduplicate chunks
                for result in search_results:
                    chunk_id = result.get("id") or result.get("payload", {}).get("id")
                    if chunk_id and chunk_id not in seen_chunk_ids:
                        seen_chunk_ids.add(chunk_id)
                        all_chunks.append(result)
            
            # Sort by score and limit
            all_chunks.sort(key=lambda x: x.get("score", 0), reverse=True)
            all_chunks = all_chunks[:settings.MAX_CHUNKS_FOR_CONTEXT]
            
            logger.info(f"Retrieved {len(all_chunks)} unique chunks")
            
            if not all_chunks:
                return {
                    "response": "I couldn't find any relevant information in the paper database to answer your question.",
                    "sources": [],
                    "simplified_queries": simplified_queries if simplify_query else None,
                    "metadata": {
                        "chunks_retrieved": 0,
                        "processing_time": time.time() - start_time,
                        "llm_provider": settings.LLM_PROVIDER,
                    }
                }
            
            # Step 3: Format context and generate response
            logger.info("Generating response...")
            context_chunks = self._format_chunks_for_context(all_chunks)
            
            # Format prompt
            if "{context_chunks}" in self.response_prompt_template and "{query}" in self.response_prompt_template:
                prompt = self.response_prompt_template.format(
                    context_chunks=context_chunks,
                    query=query
                )
            else:
                prompt = f"{self.response_prompt_template}\n\nContext:\n{context_chunks}\n\nQuestion: {query}"
            
            # Generate response
            response = self.llm_service.generate(
                prompt=prompt,
                temperature=temperature or settings.LLM_TEMPERATURE,
                max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
            )
            
            # Format sources
            sources = self._format_sources(all_chunks)
            
            processing_time = time.time() - start_time
            
            logger.info(f"RAG query completed in {processing_time:.2f}s")
            
            return {
                "response": response,
                "sources": sources,
                "simplified_queries": simplified_queries if simplify_query else None,
                "metadata": {
                    "chunks_retrieved": len(all_chunks),
                    "processing_time": processing_time,
                    "llm_provider": settings.LLM_PROVIDER,
                    "llm_model": settings.LLM_MODEL,
                    "query_type": simplification_result.get("query_type") if simplification_result else None,
                }
            }
            
        except Exception as e:
            logger.error(f"Error in RAG query: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    def _format_chunks_for_context(self, chunks: List[dict]) -> str:
        """
        Format chunks for LLM context.
        
        Args:
            chunks: List of chunk dictionaries from Qdrant
            
        Returns:
            Formatted context string
        """
        formatted_chunks = []
        
        for idx, chunk in enumerate(chunks, 1):
            payload = chunk.get("payload", {})
            chunk_text = payload.get("chunk_text", "")
            paper_id = payload.get("paper_id", "unknown")
            paper_url = payload.get("paper_url", "")
            score = chunk.get("score", 0)
            
            formatted_chunk = f"[Chunk {idx}] (Relevance: {score:.3f})\n"
            formatted_chunk += f"Paper ID: {paper_id}\n"
            if paper_url:
                formatted_chunk += f"URL: {paper_url}\n"
            formatted_chunk += f"Content:\n{chunk_text}\n"
            
            formatted_chunks.append(formatted_chunk)
        
        return "\n---\n\n".join(formatted_chunks)

    def _format_sources(self, chunks: List[dict]) -> List[dict]:
        """
        Format chunks as source citations.
        
        Args:
            chunks: List of chunk dictionaries
            
        Returns:
            List of source dictionaries
        """
        sources = []
        seen_paper_ids = set()
        
        for chunk in chunks:
            payload = chunk.get("payload", {})
            paper_id = payload.get("paper_id", "")
            
            # Only include each paper once
            if paper_id and paper_id not in seen_paper_ids:
                seen_paper_ids.add(paper_id)
                sources.append({
                    "paper_id": paper_id,
                    "paper_url": payload.get("paper_url", ""),
                    "chunk_id": payload.get("chunk_id", ""),
                    "relevance_score": chunk.get("score", 0),
                    "categories": payload.get("categories", []),
                })
        
        return sources

