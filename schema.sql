-- PostgreSQL Schema for arXiv Papers
-- This schema is automatically created by the ingestion flow,
-- but provided here for reference or manual setup

CREATE TABLE IF NOT EXISTS papers (
    id BIGSERIAL PRIMARY KEY,
    arxiv_id VARCHAR(50) UNIQUE NOT NULL,
    entry_id VARCHAR(255) NOT NULL,
    title TEXT NOT NULL,
    authors JSONB NOT NULL,
    summary TEXT,
    published TIMESTAMP,
    updated TIMESTAMP,
    categories JSONB,
    primary_category VARCHAR(50),
    pdf_url VARCHAR(500),
    doi VARCHAR(255),
    journal_ref VARCHAR(255),
    raw_text TEXT,
    sections JSONB,
    references JSONB,
    parser_used VARCHAR(50),
    parser_metadata JSONB,
    pdf_processed BOOLEAN DEFAULT FALSE,
    date_processed TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_arxiv_id ON papers(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_pdf_processed ON papers(pdf_processed);
CREATE INDEX IF NOT EXISTS idx_created_at ON papers(created_at);

-- Example query to get papers ready for chunking/indexing
-- SELECT * FROM papers WHERE pdf_processed = TRUE ORDER BY created_at DESC;

