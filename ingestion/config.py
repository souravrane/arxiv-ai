"""
Configuration module for arXiv paper ingestion flow.

Loads configuration from environment variables and provides typed access
to all configuration values.
"""

import os
from typing import List

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration class for arXiv paper ingestion."""
    
    # Database Configuration
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: str = os.getenv("DB_PORT", "3306")
    DB_NAME: str = os.getenv("DB_NAME", "")
    DB_USER: str = os.getenv("DB_USER", "")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    
    # arXiv Configuration
    ARXIV_CATEGORIES: List[str] = [
        cat.strip() 
        for cat in os.getenv("ARXIV_CATEGORIES", "cs.AI,cs.LG,cs.CV,cs.CL,cs.NE").split(",")
        if cat.strip()
    ]
    
    # Rate Limiting
    RATE_LIMIT_SECONDS: int = int(os.getenv("RATE_LIMIT_SECONDS", "4"))
    
    # Search Configuration
    MAX_RESULTS_PER_SEARCH: int = int(os.getenv("MAX_RESULTS_PER_SEARCH", "10"))
    
    # Database Schema SQL (MySQL compatible)
    CREATE_TABLE_SQL: str = """
    CREATE TABLE IF NOT EXISTS papers (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        arxiv_id VARCHAR(50) UNIQUE NOT NULL,
        entry_id VARCHAR(255) NOT NULL,
        title TEXT NOT NULL,
        authors JSON NOT NULL,
        summary TEXT,
        published TIMESTAMP NULL,
        updated TIMESTAMP NULL,
        categories JSON,
        primary_category VARCHAR(50),
        pdf_url VARCHAR(500),
        doi VARCHAR(255),
        journal_ref VARCHAR(255),
        raw_text MEDIUMTEXT,
        sections JSON,
        `references` JSON,
        parser_used VARCHAR(50),
        parser_metadata JSON,
        pdf_processed BOOLEAN DEFAULT FALSE,
        date_processed TIMESTAMP NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    );

    CREATE INDEX idx_arxiv_id ON papers(arxiv_id);
    CREATE INDEX idx_pdf_processed ON papers(pdf_processed);
    CREATE INDEX idx_created_at ON papers(created_at);
    """
    
    @classmethod
    def get_search_query(cls) -> str:
        """
        Build arXiv search query from configured categories.
        
        Returns:
            Formatted search query string
        """
        # Format categories as "cat:cs.AI OR cat:cs.LG" etc.
        formatted_categories = [f"cat:{cat}" for cat in cls.ARXIV_CATEGORIES]
        return " OR ".join(formatted_categories)
    
    @classmethod
    def validate(cls) -> None:
        """
        Validate that required configuration values are set.
        
        Raises:
            ValueError: If required configuration is missing
        """
        # Check database configuration
        if not cls.DATABASE_URL and not (cls.DB_NAME and cls.DB_USER):
            raise ValueError(
                "Database configuration missing. Set DATABASE_URL or "
                "DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD"
            )
        
        # Check arXiv categories
        if not cls.ARXIV_CATEGORIES:
            raise ValueError("ARXIV_CATEGORIES must contain at least one category")
        
        # Validate rate limit
        if cls.RATE_LIMIT_SECONDS < 1:
            raise ValueError("RATE_LIMIT_SECONDS must be at least 1")
        
        # Validate max results
        if cls.MAX_RESULTS_PER_SEARCH < 1:
            raise ValueError("MAX_RESULTS_PER_SEARCH must be at least 1")


# Create a singleton instance
config = Config()

