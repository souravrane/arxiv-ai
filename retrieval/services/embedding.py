"""
Embedding service

Handles embedding generation for queries and documents.
"""

from typing import List

from retrieval.config import settings
from retrieval.utils.logger import logger

# Try importing embedding providers
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class EmbeddingService:
    """Service for generating embeddings"""

    def __init__(self):
        """Initialize embedding service"""
        self.provider = settings.EMBEDDING_PROVIDER.lower()
        self.model = None
        self._initialize_model()

    def _initialize_model(self):
        """Initialize the embedding model based on provider"""
        if self.provider == "sentence-transformers":
            if not SENTENCE_TRANSFORMERS_AVAILABLE:
                raise ValueError(
                    "sentence-transformers not available. Install with: pip install sentence-transformers"
                )
            logger.info(f"Loading sentence-transformers model: {settings.EMBEDDING_MODEL}")
            self.model = SentenceTransformer(settings.EMBEDDING_MODEL)
            logger.info("Embedding model loaded successfully")
        
        elif self.provider == "openai":
            if not OPENAI_AVAILABLE:
                raise ValueError(
                    "openai not available. Install with: pip install openai"
                )
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY must be set for OpenAI embeddings")
            self.model = OpenAI(api_key=settings.OPENAI_API_KEY)
            logger.info("OpenAI embedding client initialized")
        
        else:
            raise ValueError(
                f"Unsupported embedding provider: {self.provider}. "
                "Supported providers: sentence-transformers, openai"
            )

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Input text to embed

        Returns:
            Embedding vector
        """
        embeddings = self.generate_embeddings([text])
        return embeddings[0] if embeddings else []

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        try:
            if self.provider == "sentence-transformers":
                # SentenceTransformers model
                embeddings = self.model.encode(texts, show_progress_bar=False)
                return embeddings.tolist()
            
            elif self.provider == "openai":
                # OpenAI client
                response = self.model.embeddings.create(
                    model=settings.OPENAI_EMBEDDING_MODEL,
                    input=texts
                )
                return [item.embedding for item in response.data]
            
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")
                
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            raise

