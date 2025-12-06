-- MySQL Schema for arXiv Papers
-- This schema is automatically created by the ingestion flow,
-- but provided here for reference or manual setup

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
    chunked BOOLEAN DEFAULT FALSE,
    date_processed TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Indexes for better query performance
-- Note: MySQL doesn't support IF NOT EXISTS for CREATE INDEX in all versions
-- These will error if indexes already exist, which is safe to ignore
CREATE INDEX idx_arxiv_id ON papers(arxiv_id);
CREATE INDEX idx_pdf_processed ON papers(pdf_processed);
CREATE INDEX idx_chunked ON papers(chunked);
CREATE INDEX idx_created_at ON papers(created_at);

-- Example query to get papers ready for chunking/indexing
-- SELECT * FROM papers WHERE pdf_processed = TRUE ORDER BY created_at DESC;

