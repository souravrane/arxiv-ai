"""
Configuration management for retrieval API

Loads configuration from environment variables.
"""

import os
from typing import List, Optional

from dotenv import load_dotenv

try:
    from pydantic_settings import BaseSettings
    from pydantic import field_validator
except ImportError:
    # Fallback for older pydantic versions
    from pydantic import BaseSettings, validator as field_validator

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings"""

    # Server Configuration
    HOST: str = os.getenv("API_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("API_PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # CORS Configuration (stored as string, parsed to list)
    CORS_ORIGINS_STR: str = os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:8080"
    )
    
    @property
    def CORS_ORIGINS(self) -> List[str]:
        """Parse CORS_ORIGINS from comma-separated string"""
        return [origin.strip() for origin in self.CORS_ORIGINS_STR.split(",") if origin.strip()]

    # Qdrant Configuration
    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))
    QDRANT_URL: str = os.getenv("QDRANT_URL", "")
    QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY", "")
    QDRANT_COLLECTION_NAME: str = os.getenv("QDRANT_COLLECTION_NAME", "paper_chunks")

    # Embedding Configuration
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "sentence-transformers")
    EMBEDDING_MODEL: str = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_EMBEDDING_MODEL: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    # Database Configuration (for metadata retrieval)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: str = os.getenv("DB_PORT", "3306")
    DB_NAME: str = os.getenv("DB_NAME", "")
    DB_USER: str = os.getenv("DB_USER", "")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")

    # Search Configuration
    DEFAULT_TOP_K: int = int(os.getenv("DEFAULT_TOP_K", "10"))
    MAX_TOP_K: int = int(os.getenv("MAX_TOP_K", "100"))

    # LLM Configuration
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "deepseek")  # openai, ollama, huggingface, lmstudio, anthropic, deepseek
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat")  # Provider-specific model name (gpt-3.5-turbo, gpt-4, deepseek-chat, deepseek-coder, deepseek-r1)
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "")  # For local providers (Ollama, LM Studio) or custom DeepSeek endpoint
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")  # Generic API key (falls back to provider-specific)
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "2000"))
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "120"))
    LLM_DEVICE: str = os.getenv("LLM_DEVICE", "auto")  # For HuggingFace: auto, cpu, cuda
    
    # Anthropic Configuration (optional)
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    
    # DeepSeek Configuration (optional, falls back to LLM_API_KEY)
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")

    # RAG Configuration
    QUERY_SIMPLIFICATION_ENABLED: bool = os.getenv("QUERY_SIMPLIFICATION_ENABLED", "true").lower() == "true"
    MAX_CHUNKS_FOR_CONTEXT: int = int(os.getenv("MAX_CHUNKS_FOR_CONTEXT", "10"))

    class Config:
        case_sensitive = True


settings = Settings()

