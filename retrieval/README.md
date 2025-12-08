# Retrieval API

FastAPI backend for semantic search and retrieval of arXiv papers.

## Overview

This API provides endpoints for:
- Semantic search using vector embeddings
- Paper metadata retrieval
- Chunk retrieval and management
- Hybrid search capabilities

## Project Structure

```
retrieval/
├── __init__.py
├── main.py                 # FastAPI application entry point
├── config.py              # Configuration management
├── api/
│   ├── __init__.py        # API router setup
│   └── routes/
│       ├── __init__.py
│       ├── search.py      # Search endpoints
│       └── papers.py      # Paper metadata endpoints
├── services/
│   ├── __init__.py
│   ├── embedding.py       # Embedding generation service
│   ├── qdrant_client.py   # Qdrant vector DB service
│   └── database.py        # MySQL database service
├── models/
│   └── __init__.py        # Pydantic models
└── utils/
    ├── __init__.py
    └── logger.py          # Logging configuration
```

## Setup

### Installation

Dependencies are included in the main `requirements.txt`. Install with:

```bash
pip install -r requirements.txt
```

### Configuration

The API uses the same environment variables as the ingestion pipeline. See the main [README.md](../README.md) and [`.env.example`](../.env.example) for configuration details.

**API-specific variables** (included in `.env.example`):
- `API_HOST`: Server host (default: 0.0.0.0)
- `API_PORT`: Server port (default: 8000)
- `DEBUG`: Enable debug mode (default: false)
- `CORS_ORIGINS`: Comma-separated list of allowed CORS origins
- `DEFAULT_TOP_K`: Default number of search results (default: 10)
- `MAX_TOP_K`: Maximum number of search results (default: 100)

### Running the Server

**Development mode:**
```bash
python -m retrieval.main
```

**Production mode:**
```bash
uvicorn retrieval.main:app --host 0.0.0.0 --port 8000
```

**With auto-reload:**
```bash
uvicorn retrieval.main:app --reload
```

## API Endpoints

### Search

- `POST /api/v1/search/` - Semantic search for papers
- `POST /api/v1/search/hybrid` - Hybrid search (semantic + keyword)
- `GET /api/v1/search/similar/{paper_id}` - Find similar papers

### Papers

- `GET /api/v1/papers/` - List papers with pagination
- `GET /api/v1/papers/{paper_id}` - Get paper details
- `GET /api/v1/papers/{paper_id}/chunks` - Get all chunks for a paper

### Health

- `GET /` - Root endpoint
- `GET /health` - Health check

## API Documentation

Once the server is running, access interactive API documentation at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Implementation Status

This is a scaffold structure. The following components need implementation:

- [ ] Embedding service (sentence-transformers/OpenAI integration)
- [ ] Qdrant search functionality
- [ ] Database service for paper metadata
- [ ] Search endpoint implementation
- [ ] Paper retrieval endpoints
- [ ] Error handling and validation
- [ ] Caching layer (optional)
- [ ] Rate limiting (optional)

## Next Steps

1. Implement embedding service to generate query embeddings
2. Implement Qdrant service for vector search
3. Implement database service for metadata retrieval
4. Connect services in API route handlers
5. Add comprehensive error handling
6. Add request/response validation
7. Add logging and monitoring

