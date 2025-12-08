# arXiv AI Paper Ingestion & Embedding System

An automated pipeline for ingesting arXiv research papers, parsing PDFs, chunking content, and generating vector embeddings for semantic search and retrieval.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Database Schema](#database-schema)
- [Setup Instructions](#setup-instructions)
- [Configuration](#configuration)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Data Flow](#data-flow)
- [Troubleshooting](#troubleshooting)

## Overview

This project provides an end-to-end solution for processing arXiv research papers:

1. **Ingestion**: Automatically fetches papers from arXiv API based on configured categories
2. **PDF Parsing**: Extracts text, sections, and references from PDF documents using advanced parsing
3. **Chunking**: Intelligently chunks paper content with context preservation
4. **Embedding**: Generates vector embeddings for semantic search
5. **Storage**: Stores structured data in MySQL and vectors in Qdrant

The system is designed to be scalable, configurable, and supports multiple embedding providers for flexibility.

## Architecture

```
┌─────────────┐
│  arXiv API  │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│     Ingestion Flow (Prefect)        │
│  ┌───────────────────────────────┐  │
│  │ 1. Search arXiv Papers        │  │
│  │ 2. Download PDFs              │  │
│  │ 3. Parse with Docling         │  │
│  │ 4. Extract Text/Sections/Refs │  │
│  └───────────────────────────────┘  │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│      MySQL Database                  │
│  ┌───────────────────────────────┐  │
│  │  papers table                 │  │
│  │  - Metadata                   │  │
│  │  - Raw text (MEDIUMTEXT)      │  │
│  │  - Sections (JSON)            │  │
│  │  - References (JSON)          │  │
│  │  - Status flags               │  │
│  └───────────────────────────────┘  │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│   Embedding Flow (Prefect)          │
│  ┌───────────────────────────────┐  │
│  │ 1. Retrieve Papers            │  │
│  │ 2. Chunk Text                 │  │
│  │ 3. Generate Embeddings         │  │
│  │ 4. Store in Qdrant            │  │
│  └───────────────────────────────┘  │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│      Qdrant Vector DB               │
│  ┌───────────────────────────────┐  │
│  │  paper_chunks collection      │  │
│  │  - Vector embeddings           │  │
│  │  - Chunk text                  │  │
│  │  - Metadata payload            │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

## Technology Stack

### Ingestion Pipeline

**File**: [`ingestion/arxiv_ingestion_flow.py`](ingestion/arxiv_ingestion_flow.py)

| Component         | Technology | Version | Purpose                                                                                       |
| ----------------- | ---------- | ------- | --------------------------------------------------------------------------------------------- |
| **Orchestration** | Prefect    | 2.14.0+ | Workflow management, task scheduling, and monitoring                                          |
| **Data Source**   | arXiv API  | 2.1.0+  | Python library for accessing arXiv paper metadata and PDFs                                    |
| **PDF Parsing**   | Docling    | 1.0.0+  | Advanced document converter that extracts structured text, sections, and references from PDFs |
| **Database**      | MySQL      | 8.0+    | Relational database for storing paper metadata, raw text, and structured content              |
| **Rate Limiting** | Custom     | -       | Configurable delay between API calls (default: 4 seconds) to respect arXiv's rate limits      |
| **HTTP Client**   | requests   | 2.31.0+ | Downloading PDF files from arXiv                                                              |

**Key Features:**

- Automatic schema initialization and migration
- Duplicate detection to avoid reprocessing
- Error handling and retry logic
- Structured extraction of sections and references
- Support for large documents (MEDIUMTEXT for raw_text)

### Embedding Pipeline

**File**: [`ingestion/embedding_flow.py`](ingestion/embedding_flow.py)

#### Chunking Strategy

| Aspect             | Implementation                       | Details                                                                                |
| ------------------ | ------------------------------------ | -------------------------------------------------------------------------------------- |
| **Method**         | Sentence-based chunking with overlap | Splits text at sentence boundaries for natural breaks                                  |
| **Context Header** | Title + Abstract prepended           | Every chunk includes `[title]\n\n[abstract]\n\n[chunk_body]` to preserve paper context |
| **Target Size**    | 500-800 tokens per chunk             | Default: 650 tokens (configurable via `CHUNK_SIZE_TOKENS`)                             |
| **Overlap**        | 100-150 tokens between chunks        | Default: 125 tokens (configurable via `CHUNK_OVERLAP_TOKENS`)                          |
| **Token Counting** | tiktoken library                     | Uses `cl100k_base` encoding for accurate token measurement                             |
| **Chunk Format**   | Context-aware                        | `{title}\n\n{summary}\n\n{chunk_body}`                                                 |

**Why This Strategy?**

- **Context Preservation**: Prepending title/abstract to each chunk helps embeddings understand the overall paper context, improving semantic search quality
- **Token-based**: Using tokens instead of characters ensures compatibility with LLM tokenizers and better size control
- **Overlap**: Prevents loss of context at chunk boundaries, especially important for technical content that may span multiple chunks

#### Embedding Generation

| Component                | Technology                                                                 | Details                                         |
| ------------------------ | -------------------------------------------------------------------------- | ----------------------------------------------- |
| **Default Provider**     | sentence-transformers                                                      | Local, no API costs, fast inference             |
| **Default Model**        | `all-MiniLM-L6-v2`                                                         | 384 dimensions, optimized for speed and quality |
| **Alternative Provider** | OpenAI                                                                     | Cloud-based, requires API key                   |
| **OpenAI Models**        | `text-embedding-3-small` (1536 dim) or `text-embedding-3-large` (3072 dim) | Higher quality, larger dimensions               |
| **Token Counting**       | tiktoken                                                                   | Accurate token measurement for chunking         |

**Supported Providers:**

- **sentence-transformers**: Local execution, supports any HuggingFace model
- **OpenAI**: Cloud-based, supports latest embedding models

#### Vector Database

| Component           | Technology                   | Details                                                                              |
| ------------------- | ---------------------------- | ------------------------------------------------------------------------------------ |
| **Database**        | Qdrant                       | High-performance vector database with built-in UI                                    |
| **Collection**      | `paper_chunks`               | Default collection name (configurable)                                               |
| **Distance Metric** | Cosine Similarity            | Standard for semantic search                                                         |
| **Storage**         | Local (default) or Cloud     | Supports both local Docker deployment and Qdrant Cloud                               |
| **Payload Fields**  | Metadata stored with vectors | paper_id, chunk_id, chunk_text, section_title, categories, published_date, paper_url |

**Why Qdrant?**

- High performance for vector search
- Built-in web UI for inspection and debugging
- Support for metadata filtering
- Production-ready with cloud options
- Active community and good documentation

## Database Schema

**File**: [`schema.sql`](schema.sql)

### MySQL `papers` Table

```sql
CREATE TABLE papers (
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
    raw_text MEDIUMTEXT,              -- Supports up to 16MB
    sections JSON,                    -- Structured sections
    `references` JSON,                -- Paper references
    parser_used VARCHAR(50),
    parser_metadata JSON,
    pdf_processed BOOLEAN DEFAULT FALSE,
    chunked BOOLEAN DEFAULT FALSE,    -- Tracks embedding status
    date_processed TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

**Key Indexes:**

- `idx_arxiv_id`: Fast lookup by arXiv ID
- `idx_pdf_processed`: Filter papers ready for chunking
- `idx_chunked`: Filter papers ready for embedding
- `idx_created_at`: Time-based queries

**Status Flags:**

- `pdf_processed`: Indicates PDF has been successfully parsed
- `chunked`: Indicates paper has been chunked and embedded

## Setup Instructions

### Prerequisites

- Python 3.8 or higher
- MySQL 8.0 or higher
- Docker (for Qdrant, optional if using cloud)
- Git

### 1. Clone the Repository

```bash
git clone <repository-url>
cd arxiv-ai
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

**Key Dependencies:**

- `prefect>=2.14.0`: Workflow orchestration
- `arxiv>=2.1.0`: arXiv API client
- `mysql-connector-python>=8.0.0`: MySQL database connector
- `docling>=1.0.0`: PDF parsing
- `qdrant-client>=1.7.0`: Qdrant vector database client
- `sentence-transformers>=2.2.0`: Local embedding generation
- `openai>=1.0.0`: OpenAI embedding support (optional)
- `tiktoken>=0.5.0`: Token counting for chunking

### 3. Set Up MySQL Database

See [MYSQL_SETUP.md](MYSQL_SETUP.md) for detailed MySQL setup instructions.

**Quick Setup:**

```bash
# Create database
mysql -u root -p -e "CREATE DATABASE arxiv_db;"

# The schema will be auto-created by the ingestion flow
# Or manually run:
mysql -u root -p arxiv_db < schema.sql
```

### 4. Set Up Qdrant

**Option A: Docker (Recommended)**

```bash
docker run -p 6333:6333 -p 6334:6334 \
  -v $(pwd)/qdrant_storage:/qdrant/storage:z \
  qdrant/qdrant
```

**Option B: Homebrew (macOS)**

```bash
brew install qdrant
brew services start qdrant
```

**Verify Qdrant is running:**

```bash
curl http://localhost:6333/health
# Should return: {"status":"ok"}
```

**Access Qdrant UI:**

- Dashboard: http://localhost:6333/dashboard
- Main UI: http://localhost:6333

### 5. Configure Environment Variables

Create a `.env` file in the project root by copying the example:

```bash
cp .env.example .env
```

Then edit `.env` and update with your actual configuration values. See [`.env.example`](.env.example) for all available configuration options including:

- Database configuration (MySQL)
- arXiv API settings
- Embedding provider configuration (sentence-transformers or OpenAI)
- Qdrant vector database settings
- Chunking parameters
- Retrieval API settings

## Configuration

### Environment Variables

| Variable                 | Default                                | Description                                                     |
| ------------------------ | -------------------------------------- | --------------------------------------------------------------- |
| `DATABASE_URL`           | -                                      | MySQL connection string (alternative to individual DB\_\* vars) |
| `DB_HOST`                | localhost                              | MySQL host                                                      |
| `DB_PORT`                | 3306                                   | MySQL port                                                      |
| `DB_NAME`                | -                                      | MySQL database name                                             |
| `DB_USER`                | -                                      | MySQL username                                                  |
| `DB_PASSWORD`            | -                                      | MySQL password                                                  |
| `ARXIV_CATEGORIES`       | cs.AI,cs.LG,cs.CV,cs.CL,cs.NE          | Comma-separated arXiv categories                                |
| `RATE_LIMIT_SECONDS`     | 4                                      | Delay between arXiv API calls                                   |
| `MAX_RESULTS_PER_SEARCH` | 10                                     | Maximum papers per search query                                 |
| `EMBEDDING_PROVIDER`     | sentence-transformers                  | Embedding provider (sentence-transformers or openai)            |
| `EMBEDDING_MODEL`        | sentence-transformers/all-MiniLM-L6-v2 | Embedding model name                                            |
| `OPENAI_API_KEY`         | -                                      | OpenAI API key (required for OpenAI provider)                   |
| `OPENAI_EMBEDDING_MODEL` | text-embedding-3-small                 | OpenAI embedding model                                          |
| `QDRANT_HOST`            | localhost                              | Qdrant host                                                     |
| `QDRANT_PORT`            | 6333                                   | Qdrant port                                                     |
| `QDRANT_URL`             | -                                      | Qdrant cloud URL (alternative to HOST/PORT)                     |
| `QDRANT_API_KEY`         | -                                      | Qdrant cloud API key                                            |
| `QDRANT_COLLECTION_NAME` | paper_chunks                           | Qdrant collection name                                          |
| `CHUNK_SIZE_TOKENS`      | 650                                    | Target chunk size in tokens                                     |
| `CHUNK_OVERLAP_TOKENS`   | 125                                    | Overlap between chunks in tokens                                |

## Usage

### Running the Ingestion Flow

**Direct execution:**

```bash
python -m ingestion.arxiv_ingestion_flow
```

**With Prefect:**

```bash
# Start Prefect server (optional, for UI)
prefect server start

# Run the flow
prefect deployment build ingestion/arxiv_ingestion_flow.py:arxiv_ai_paper_ingestion_flow -n ingestion-deployment
prefect deployment apply ingestion-deployment.yaml
prefect deployment run arxiv_ai_paper_ingestion_flow/ingestion-deployment
```

**Flow Parameters:**

- `max_results_per_search`: Override default max results
- `delay_seconds`: Override default rate limit delay

### Running the Embedding Flow

**Direct execution:**

```bash
python -m ingestion.embedding_flow
```

**With Prefect:**

```bash
prefect deployment build ingestion/embedding_flow.py:arxiv_paper_embedding_flow -n embedding-deployment
prefect deployment apply embedding-deployment.yaml
prefect deployment run arxiv_paper_embedding_flow/embedding-deployment
```

**Flow Parameters:**

- `limit`: Maximum number of papers to process (None for all)
- `batch_size`: Number of chunks to insert per batch (default: 100)

### Monitoring

- **Prefect UI**: http://localhost:4200 (if Prefect server is running)
- **Qdrant UI**: http://localhost:6333/dashboard
- **MySQL**: Use your preferred MySQL client

## Project Structure

```
arxiv-ai/
├── ingestion/
│   ├── __init__.py
│   ├── arxiv_ingestion_flow.py    # Main ingestion pipeline
│   ├── embedding_flow.py           # Embedding and chunking pipeline
│   └── config.py                   # Configuration management
├── schema.sql                      # MySQL database schema
├── requirements.txt                # Python dependencies
├── MYSQL_SETUP.md                  # MySQL setup guide
├── test_db_connection.py           # Database connection test
└── README.md                       # This file
```

**Key Files:**

- [`ingestion/arxiv_ingestion_flow.py`](ingestion/arxiv_ingestion_flow.py): Orchestrates paper fetching, PDF downloading, parsing, and database storage
- [`ingestion/embedding_flow.py`](ingestion/embedding_flow.py): Handles chunking, embedding generation, and vector storage
- [`ingestion/config.py`](ingestion/config.py): Centralized configuration management
- [`schema.sql`](schema.sql): Database schema definition

## Data Flow

### Step-by-Step Process

1. **Ingestion Flow Starts**

   - Searches arXiv API for papers matching configured categories
   - Filters out already processed papers (by arxiv_id)

2. **PDF Processing**

   - Downloads PDF from arXiv
   - Parses PDF using Docling to extract:
     - Raw text content
     - Structured sections
     - References
   - Stores metadata and content in MySQL
   - Sets `pdf_processed = TRUE`

3. **Embedding Flow Starts**

   - Queries MySQL for papers where `pdf_processed = TRUE` and `chunked = FALSE`
   - For each paper:
     - Creates context header: `{title}\n\n{summary}`
     - Chunks `raw_text` using sentence-based strategy
     - Prepends context header to each chunk
     - Generates embeddings for all chunks
     - Stores chunks in Qdrant with metadata
   - Sets `chunked = TRUE` in MySQL

4. **Vector Storage**
   - Each chunk stored in Qdrant with:
     - Vector embedding
     - Chunk text (with context header)
     - Metadata: paper_id, chunk_id, section_title, categories, published_date, paper_url

### State Transitions

```
Paper States:
┌─────────────┐
│  New Paper  │
└──────┬──────┘
       │
       ▼
┌─────────────────┐      ┌──────────────────┐
│ pdf_processed   │─────▶│  chunked         │
│ = FALSE         │      │  = TRUE          │
└─────────────────┘      └──────────────────┘
       │
       │ (After PDF parsing)
       ▼
┌─────────────────┐
│ pdf_processed   │
│ = TRUE          │
└─────────────────┘
       │
       │ (After embedding)
       ▼
┌─────────────────┐
│ chunked = TRUE   │
└─────────────────┘
```

## Troubleshooting

### Common Issues

**1. MySQL Connection Errors**

- Verify MySQL is running: `brew services list` (macOS) or `systemctl status mysql` (Linux)
- Check connection credentials in `.env`
- Test connection: `python test_db_connection.py`

**2. Qdrant Connection Errors**

- Verify Qdrant is running: `curl http://localhost:6333/health`
- Check ports 6333 and 6334 are not in use
- For Docker: Ensure port mapping is correct

**3. PDF Parsing Failures**

- Some PDFs may be corrupted or have unusual formats
- Check logs for specific error messages
- Docling handles most cases, but edge cases may fail

**4. Embedding Generation Errors**

- For sentence-transformers: Ensure model is downloaded (first run may take time)
- For OpenAI: Verify API key is set and valid
- Check available disk space for model storage

**5. Chunking Issues**

- Very short papers may not generate chunks
- Check `raw_text` is not NULL or empty
- Verify token counting is working (check logs)

**6. Schema Migration Issues**

- The flow automatically migrates schema
- If issues occur, manually run `schema.sql`
- Check MySQL user has ALTER TABLE permissions

### Getting Help

- Check Prefect logs for detailed error messages
- Use Qdrant UI to inspect stored vectors
- Query MySQL directly to check paper status
- Review configuration in `ingestion/config.py`

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]
