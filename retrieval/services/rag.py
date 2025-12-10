"""
RAG (Retrieval-Augmented Generation) Service

Orchestrates the complete RAG flow:
1. Query simplification
2. Semantic search
3. Response generation
"""

import time
from typing import Dict, List, Optional

import tiktoken

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
        top_k: Optional[int] = None,
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
            
            # Use default top_k if not provided
            effective_top_k = top_k or settings.DEFAULT_TOP_K
            logger.info(f"Using top_k: {effective_top_k}")
            
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
                    top_k=effective_top_k,
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
                        "top_k": effective_top_k,
                    }
                }
            
            # Step 3: Format context and generate response
            logger.info("Generating response...")
            
            # Calculate token budget for context
            # Reserve tokens for: prompt template, query, and response
            max_response_tokens = max_tokens or settings.LLM_MAX_TOKENS
            prompt_template_tokens = 500  # Approximate tokens for prompt template
            query_tokens = self._count_tokens(query)
            response_reserve = int(max_response_tokens * 0.3)  # Reserve 30% for response
            
            # Available tokens for context chunks
            context_token_budget = max_response_tokens - prompt_template_tokens - query_tokens - response_reserve
            context_token_budget = max(context_token_budget, 500)  # Minimum 500 tokens for context
            
            logger.info(f"Token budget: {max_response_tokens} total, {context_token_budget} for context")
            
            context_chunks = self._format_chunks_for_context(
                all_chunks, 
                max_tokens=context_token_budget
            )
            
            # Format prompt
            if "{context_chunks}" in self.response_prompt_template and "{query}" in self.response_prompt_template:
                prompt = self.response_prompt_template.format(
                    context_chunks=context_chunks,
                    query=query
                )
            else:
                prompt = f"{self.response_prompt_template}\n\nContext:\n{context_chunks}\n\nQuestion: {query}"
            
            logger.info(f"Prompt: {prompt}")
            logger.info(f"context_chunks: {context_chunks}")

            response = "This is a test response."
            # Generate response
            # response = self.llm_service.generate(
            #     prompt=prompt,
            #     temperature=temperature or settings.LLM_TEMPERATURE,
            #     max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
            # )
            
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

    def _count_tokens(self, text: str) -> int:
        """
        Count tokens in text using tiktoken.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Number of tokens
        """
        try:
            # Use cl100k_base encoding (used by GPT models and DeepSeek)
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception as e:
            logger.warning(f"Error counting tokens: {e}, using character-based estimate")
            # Fallback: rough estimate (1 token ≈ 4 characters)
            return len(text) // 4

    def _format_chunks_for_context(self, chunks: List[dict], max_tokens: Optional[int] = None) -> str:
        """
        Format chunks for LLM context with text sanitization and token budget management.
        
        Uses re-ranking and filtering strategy:
        - Sorts chunks by relevance score (highest first)
        - Selects chunks that fit within token budget
        - Preserves most relevant information
        
        Args:
            chunks: List of chunk dictionaries from Qdrant (should be pre-sorted by score)
            max_tokens: Maximum tokens allowed for context (None = no limit)
            
        Returns:
            Formatted context string
        """
        # Ensure chunks are sorted by relevance score (highest first)
        sorted_chunks = sorted(chunks, key=lambda x: x.get("score", 0), reverse=True)
        
        formatted_chunks = []
        current_tokens = 0
        formatting_overhead = 100  # Approximate tokens for formatting per chunk
        
        if max_tokens:
            available_tokens = max_tokens - formatting_overhead
            logger.info(f"Token budget for chunks: {available_tokens} tokens")
        else:
            available_tokens = None
            logger.info("No token budget limit, using all chunks")
        
        for idx, chunk in enumerate(sorted_chunks, 1):
            payload = chunk.get("payload", {})
            chunk_text = payload.get("chunk_text", "")
            paper_id = payload.get("paper_id", "unknown")
            paper_url = payload.get("paper_url", "")
            score = chunk.get("score", 0)
            
            # Text is already sanitized when stored in database, so no need to sanitize again
            # Only truncate if too long (safety measure for token budget)
            if chunk_text:
                max_chunk_length = 10000  # Adjust as needed
                if len(chunk_text) > max_chunk_length:
                    chunk_text = chunk_text[:max_chunk_length] + "... [truncated]"
            
            # Extract paper title from chunk_text (it's in the context header at the start)
            # The chunk_text format is: "{title}\n\n{chunk_body}" (summary removed)
            paper_title = "Unknown"
            if chunk_text:
                lines = chunk_text.split('\n')
                if lines:
                    # Title is typically the first non-empty line
                    for line in lines:
                        if line.strip():
                            paper_title = line.strip()
                            break
            
            # Build formatted chunk
            formatted_chunk = f"[Chunk {idx}] (Relevance: {score:.3f})\n"
            formatted_chunk += f"Paper Title: {paper_title}\n"
            formatted_chunk += f"Paper ID: {paper_id}\n"
            if paper_url:
                formatted_chunk += f"Paper URL: {paper_url}\n"
            formatted_chunk += f"Content:\n{chunk_text}\n"
            
            # Check token budget if limit is set
            if max_tokens:
                # Estimate tokens for this formatted chunk
                chunk_tokens = self._count_tokens(formatted_chunk)
                
                # Check if adding this chunk would exceed budget
                if current_tokens + chunk_tokens > available_tokens:
                    logger.info(
                        f"Token budget reached at chunk {idx}/{len(sorted_chunks)}. "
                        f"Using {len(formatted_chunks)} chunks ({current_tokens} tokens)"
                    )
                    break
                
                current_tokens += chunk_tokens
            
            formatted_chunks.append(formatted_chunk)
        
        if not formatted_chunks:
            logger.warning("No chunks could be formatted within token budget")
            return "No relevant chunks available."
        
        result = "\n---\n\n".join(formatted_chunks)
        
        if max_tokens:
            final_tokens = self._count_tokens(result)
            logger.info(f"Formatted {len(formatted_chunks)} chunks using {final_tokens}/{available_tokens} tokens")
        
        return result

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
                # Convert chunk_id to string if it's an integer
                chunk_id = payload.get("chunk_id", "")
                if isinstance(chunk_id, int):
                    chunk_id = str(chunk_id)
                elif not isinstance(chunk_id, str):
                    chunk_id = str(chunk_id) if chunk_id else ""
                
                sources.append({
                    "paper_id": paper_id,
                    "paper_url": payload.get("paper_url", ""),
                    "chunk_id": chunk_id,
                    "relevance_score": chunk.get("score", 0),
                    "categories": payload.get("categories", []),
                })
        
        return sources

