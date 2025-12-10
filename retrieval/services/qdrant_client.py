"""
Qdrant client service

Handles interactions with Qdrant vector database.
"""

from typing import List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny

from retrieval.config import settings
from retrieval.utils.logger import logger


class QdrantService:
    """Service for Qdrant vector database operations"""

    def __init__(self):
        """Initialize Qdrant client"""
        self.client = self._get_client()
        self.collection_name = settings.QDRANT_COLLECTION_NAME

    def _get_client(self) -> QdrantClient:
        """Get Qdrant client instance"""
        if settings.QDRANT_URL:
            return QdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY if settings.QDRANT_API_KEY else None,
            )
        else:
            return QdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
            )

    def search(
        self,
        query_vector: List[float],
        top_k: Optional[int] = None,
        filter_conditions: Optional[dict] = None,
    ) -> List[dict]:
        """
        Perform a vector semantic search in the Qdrant vector database.

        Args:
            query_vector: The embedding vector for the semantic search.
            top_k: Number of most similar vectors/chunks to return.
            filter_conditions: Optional dictionary to filter results (e.g., by paper_id or categories).

        Returns:
            List of search results as dicts, including similarity scores and metadata.
        """
        try:
            # Prepare Qdrant filter object if any filtering is required
            qdrant_filter = None
            if filter_conditions:
                conditions = []
                if "paper_id" in filter_conditions:
                    # Filter for specific paper_id
                    conditions.append(
                        FieldCondition(
                            key="paper_id",
                            match=MatchValue(value=filter_conditions["paper_id"])
                        )
                    )
                if "categories" in filter_conditions:
                    categories = filter_conditions["categories"]
                    if isinstance(categories, list):
                        # Match any of the listed categories
                        conditions.append(
                            FieldCondition(
                                key="categories",
                                match=MatchAny(any=categories)
                            )
                        )
                if conditions:
                    qdrant_filter = Filter(must=conditions)

            # Use top_k or a reasonable default
            limit = top_k if top_k else 10

            # The main semantic search call: searches by vector similarity.
            results = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit,
                query_filter=qdrant_filter,
                with_payload=True,
                with_vectors=False,
            )

            # Parse and format the response (extracting chunk id, score, and metadata/payload)
            formatted_results = []
            points = results.points if hasattr(results, 'points') else []
            for point in points:
                formatted_results.append({
                    "id": point.id,
                    "score": point.score,
                    "payload": point.payload or {},
                    "vector": getattr(point, 'vector', None),
                })

            # Limit results to top_k if specified
            if top_k is not None:
                formatted_results = formatted_results[:top_k]

            logger.debug(
                f"Vector semantic search found {len(formatted_results)} results (top_k: {top_k})"
            )
            return formatted_results

        except Exception as e:
            logger.error(f"Error during vector semantic search in Qdrant: {e}")
            raise

    def get_chunks_by_paper_id(self, paper_id: str) -> List[dict]:
        """
        Retrieve all chunks for a specific paper.

        Args:
            paper_id: Paper ID to retrieve chunks for

        Returns:
            List of chunks with metadata
        """
        try:
            # Use scroll to get all points with matching paper_id
            results, _ = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="paper_id",
                            match=MatchValue(value=paper_id)
                        )
                    ]
                ),
                limit=1000,  # Adjust if needed
            )
            
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "id": result.id,
                    "payload": result.payload or {},
                    "vector": result.vector if hasattr(result, "vector") else None,
                })
            
            logger.debug(f"Retrieved {len(formatted_results)} chunks for paper {paper_id}")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error retrieving chunks for paper {paper_id}: {e}")
            raise

    def filter_by_categories(self, categories: List[str]) -> Filter:
        """
        Create a filter for specific categories.

        Args:
            categories: List of category strings

        Returns:
            Qdrant Filter object
        """
        return Filter(
            must=[
                FieldCondition(
                    key="categories",
                    match=MatchAny(any=categories)
                )
            ]
        )

