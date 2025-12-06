"""
Embedding Flow for arXiv Papers

This flow retrieves papers from the database, chunks them, generates embeddings,
and stores them in Qdrant vector database. Supports multiple embedding providers
including sentence-transformers, OpenAI, and other cloud-based APIs.
"""

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import mysql.connector
import tiktoken
from prefect import flow, task
from prefect import get_run_logger
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from urllib.parse import urlparse

try:
    from .config import config
except ImportError:
    # Handle case when running as a script
    from config import config

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


def get_db_connection():
    """
    Create and return a MySQL database connection.
    Reads connection details from configuration.
    
    Returns:
        mysql.connector.connection: Database connection object
        
    Raises:
        Exception: If connection cannot be established
    """
    # MySQL connector doesn't support DATABASE_URL directly, so parse it if provided
    if config.DATABASE_URL:
        # Parse DATABASE_URL format: mysql://user:password@host:port/database
        parsed = urlparse(config.DATABASE_URL)
        db_config = {
            "host": parsed.hostname or config.DB_HOST,
            "port": int(parsed.port) if parsed.port else int(config.DB_PORT),
            "database": parsed.path.lstrip('/') if parsed.path else config.DB_NAME,
            "user": parsed.username or config.DB_USER,
            "password": parsed.password or config.DB_PASSWORD,
        }
    else:
        # Fallback to individual environment variables
        db_config = {
            "host": config.DB_HOST,
            "port": int(config.DB_PORT),
            "database": config.DB_NAME,
            "user": config.DB_USER,
            "password": config.DB_PASSWORD,
        }
    
    if not db_config["database"] or not db_config["user"]:
        raise ValueError(
            "Database configuration missing. Set DATABASE_URL or "
            "DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD"
        )
    
    return mysql.connector.connect(**db_config)


@task(name="ensure_schema_up_to_date")
def ensure_schema_up_to_date():
    """
    Ensure the database schema is up to date, particularly the chunked column.
    This is a migration task to handle existing databases.
    """
    logger = get_run_logger()
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Migration: Add chunked column if it doesn't exist
        try:
            cur.execute("""
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'papers'
                AND COLUMN_NAME = 'chunked'
            """)
            result = cur.fetchone()
            if not result:
                logger.info("Adding chunked column to papers table...")
                cur.execute("ALTER TABLE papers ADD COLUMN chunked BOOLEAN DEFAULT FALSE")
                conn.commit()
                logger.info("✓ Successfully added chunked column")
            else:
                logger.debug("chunked column already exists")
        except mysql.connector.Error as e:
            logger.warning(f"Could not check/add chunked column: {e}")
            # Don't fail the whole initialization if migration check fails
        
        # Migration: Add chunked index if it doesn't exist
        try:
            cur.execute("""
                SELECT INDEX_NAME
                FROM INFORMATION_SCHEMA.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'papers'
                AND INDEX_NAME = 'idx_chunked'
            """)
            result = cur.fetchone()
            if not result:
                logger.info("Adding idx_chunked index...")
                cur.execute("CREATE INDEX idx_chunked ON papers(chunked)")
                conn.commit()
                logger.info("✓ Successfully added idx_chunked index")
            else:
                logger.debug("idx_chunked index already exists")
        except mysql.connector.Error as e:
            if e.errno == 1061:  # Duplicate key name
                logger.debug("idx_chunked index already exists, skipping")
            else:
                logger.warning(f"Could not check/add idx_chunked index: {e}")
        
        conn.commit()
        cur.close()
        conn.close()
        logger.info("Schema check completed")
        
    except Exception as e:
        logger.error(f"Error ensuring schema is up to date: {e}")
        raise


def get_qdrant_client() -> QdrantClient:
    """
    Create and return a Qdrant client.
    Supports both local and cloud Qdrant instances.
    
    Returns:
        QdrantClient: Qdrant client instance
    """
    if config.QDRANT_URL:
        # Cloud Qdrant
        return QdrantClient(
            url=config.QDRANT_URL,
            api_key=config.QDRANT_API_KEY if config.QDRANT_API_KEY else None,
        )
    else:
        # Local Qdrant
        return QdrantClient(
            host=config.QDRANT_HOST,
            port=config.QDRANT_PORT,
        )


def get_embedding_model():
    """
    Initialize and return the embedding model based on configuration.
    
    Returns:
        Embedding model instance (varies by provider)
        
    Raises:
        ValueError: If provider is not available or not supported
    """
    provider = config.EMBEDDING_PROVIDER.lower()
    
    if provider == "sentence-transformers":
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ValueError(
                "sentence-transformers not available. Install with: pip install sentence-transformers"
            )
        return SentenceTransformer(config.EMBEDDING_MODEL)
    
    elif provider == "openai":
        if not OPENAI_AVAILABLE:
            raise ValueError(
                "openai not available. Install with: pip install openai"
            )
        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY must be set for OpenAI embeddings")
        return OpenAI(api_key=config.OPENAI_API_KEY)
    
    else:
        raise ValueError(
            f"Unsupported embedding provider: {provider}. "
            "Supported providers: sentence-transformers, openai"
        )


def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    """
    Count the number of tokens in a text string.
    
    Args:
        text: Text to count tokens for
        model: Model name for tokenizer (default: gpt-3.5-turbo)
        
    Returns:
        Number of tokens
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except KeyError:
        # Fallback to cl100k_base encoding if model not found
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))


def chunk_paper_text(
    context_header: str,
    body: str,
    chunk_size_tokens: int = 650,
    overlap_tokens: int = 125
) -> List[Tuple[str, int]]:
    """
    Chunk text into overlapping segments with context header prepended.
    
    Args:
        context_header: Title and abstract to prepend to each chunk
        body: Main text body to chunk
        chunk_size_tokens: Target chunk size in tokens
        overlap_tokens: Overlap between chunks in tokens
        
    Returns:
        List of tuples: (chunk_text, chunk_index)
    """
    if not body or not body.strip():
        return []
    
    chunks = []
    context_tokens = count_tokens(context_header)
    
    # Calculate body chunk size (subtract context size from target)
    body_chunk_size = max(chunk_size_tokens - context_tokens, 100)  # Minimum 100 tokens for body
    
    # Split body into sentences (simple approach)
    sentences = body.split('. ')
    current_chunk = []
    current_tokens = 0
    chunk_index = 0
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        sentence_tokens = count_tokens(sentence)
        
        # If adding this sentence would exceed chunk size, finalize current chunk
        if current_tokens + sentence_tokens > body_chunk_size and current_chunk:
            # Create chunk with context
            chunk_body = '. '.join(current_chunk)
            if not chunk_body.endswith('.'):
                chunk_body += '.'
            
            full_chunk = f"{context_header}\n\n{chunk_body}"
            chunks.append((full_chunk, chunk_index))
            chunk_index += 1
            
            # Start new chunk with overlap
            # Keep last N sentences for overlap
            overlap_sentences = []
            overlap_token_count = 0
            for s in reversed(current_chunk):
                s_tokens = count_tokens(s)
                if overlap_token_count + s_tokens <= overlap_tokens:
                    overlap_sentences.insert(0, s)
                    overlap_token_count += s_tokens
                else:
                    break
            
            current_chunk = overlap_sentences
            current_tokens = overlap_token_count
        
        current_chunk.append(sentence)
        current_tokens += sentence_tokens
    
    # Add final chunk if there's remaining content
    if current_chunk:
        chunk_body = '. '.join(current_chunk)
        if not chunk_body.endswith('.'):
            chunk_body += '.'
        full_chunk = f"{context_header}\n\n{chunk_body}"
        chunks.append((full_chunk, chunk_index))
    
    return chunks


@task(name="initialize_qdrant_collection")
def initialize_qdrant_collection(embedding_dim: int):
    """
    Initialize Qdrant collection if it doesn't exist.
    
    Args:
        embedding_dim: Dimension of embedding vectors
    """
    logger = get_run_logger()
    try:
        client = get_qdrant_client()
        collection_name = config.QDRANT_COLLECTION_NAME
        
        # Check if collection exists
        collections = client.get_collections().collections
        collection_exists = any(c.name == collection_name for c in collections)
        
        if not collection_exists:
            logger.info(f"Creating Qdrant collection: {collection_name}")
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=embedding_dim,
                    distance=Distance.COSINE
                )
            )
            logger.info(f"✓ Created collection {collection_name} with vector size {embedding_dim}")
        else:
            logger.debug(f"Collection {collection_name} already exists")
            
    except Exception as e:
        logger.error(f"Error initializing Qdrant collection: {e}")
        raise


@task(name="get_embedding_dimension")
def get_embedding_dimension() -> int:
    """
    Get the embedding dimension for the configured model.
    
    Returns:
        Embedding dimension (int)
    """
    logger = get_run_logger()
    provider = config.EMBEDDING_PROVIDER.lower()
    
    if provider == "sentence-transformers":
        model = SentenceTransformer(config.EMBEDDING_MODEL)
        # Get dimension by encoding a dummy text
        dummy_embedding = model.encode("test")
        return len(dummy_embedding)
    
    elif provider == "openai":
        # OpenAI embedding dimensions
        model_dimensions = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        return model_dimensions.get(config.OPENAI_EMBEDDING_MODEL, 1536)
    
    else:
        raise ValueError(f"Unknown embedding provider: {provider}")


@task(name="generate_embeddings")
def generate_embeddings(texts: List[str], model) -> List[List[float]]:
    """
    Generate embeddings for a list of texts.
    
    Args:
        texts: List of text strings to embed
        model: Embedding model instance
        
    Returns:
        List of embedding vectors
    """
    logger = get_run_logger()
    provider = config.EMBEDDING_PROVIDER.lower()
    
    try:
        if provider == "sentence-transformers":
            # SentenceTransformers model
            embeddings = model.encode(texts, show_progress_bar=False)
            return embeddings.tolist()
        
        elif provider == "openai":
            # OpenAI client
            response = model.embeddings.create(
                model=config.OPENAI_EMBEDDING_MODEL,
                input=texts
            )
            return [item.embedding for item in response.data]
        
        else:
            raise ValueError(f"Unsupported provider: {provider}")
            
    except Exception as e:
        logger.error(f"Error generating embeddings: {e}")
        raise


@task(name="retrieve_papers_for_chunking")
def retrieve_papers_for_chunking(limit: Optional[int] = None) -> List[Dict]:
    """
    Retrieve papers from database that are processed but not yet chunked.
    
    Args:
        limit: Maximum number of papers to retrieve (None for all)
        
    Returns:
        List of paper dictionaries
    """
    logger = get_run_logger()
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        
        query = """
            SELECT 
                id, arxiv_id, entry_id, title, summary, published,
                categories, primary_category, raw_text, sections, pdf_url
            FROM papers
            WHERE pdf_processed = TRUE 
            AND (chunked = FALSE OR chunked IS NULL)
            AND raw_text IS NOT NULL
            AND raw_text != ''
            ORDER BY created_at ASC
        """
        
        if limit:
            query += f" LIMIT {limit}"
        
        cur.execute(query)
        papers = cur.fetchall()
        
        # Parse JSON fields
        for paper in papers:
            if paper.get('categories'):
                try:
                    paper['categories'] = json.loads(paper['categories']) if isinstance(paper['categories'], str) else paper['categories']
                except:
                    paper['categories'] = []
            else:
                paper['categories'] = []
            
            if paper.get('sections'):
                try:
                    paper['sections'] = json.loads(paper['sections']) if isinstance(paper['sections'], str) else paper['sections']
                except:
                    paper['sections'] = None
        
        cur.close()
        conn.close()
        
        logger.info(f"Retrieved {len(papers)} papers for chunking")
        return papers
        
    except Exception as e:
        logger.error(f"Error retrieving papers: {e}")
        raise


@task(name="chunk_and_embed_paper")
def chunk_and_embed_paper(
    paper: Dict,
    embedding_model,
    embedding_dim: int
) -> List[Dict]:
    """
    Chunk a paper and generate embeddings for each chunk.
    
    Args:
        paper: Paper dictionary from database
        embedding_model: Embedding model instance
        embedding_dim: Embedding dimension
        
    Returns:
        List of chunk dictionaries with embeddings
    """
    logger = get_run_logger()
    
    try:
        paper_id = str(paper['id'])
        title = paper.get('title', '')
        summary = paper.get('summary', '') or ''
        raw_text = paper.get('raw_text', '')
        categories = paper.get('categories', [])
        published = paper.get('published')
        sections = paper.get('sections') or {}
        pdf_url = paper.get('pdf_url', '')
        
        # Create context header
        context_header = f"{title}\n\n{summary}"
        
        # Chunk the text
        chunks = chunk_paper_text(
            context_header=context_header,
            body=raw_text,
            chunk_size_tokens=config.CHUNK_SIZE_TOKENS,
            overlap_tokens=config.CHUNK_OVERLAP_TOKENS
        )
        
        if not chunks:
            logger.warning(f"No chunks created for paper {paper_id}")
            return []
        
        logger.info(f"Created {len(chunks)} chunks for paper {paper_id}")
        
        # Extract chunk texts
        chunk_texts = [chunk[0] for chunk in chunks]
        
        # Generate embeddings
        logger.info(f"Generating embeddings for {len(chunk_texts)} chunks...")
        embeddings = generate_embeddings(chunk_texts, embedding_model)
        
        # Prepare chunk data for Qdrant
        chunk_data = []
        for idx, (chunk_text, chunk_index) in enumerate(chunks):
            # Extract section title if available
            section_title = None
            if sections and isinstance(sections, dict):
                # Try to find section for this chunk (simplified - could be improved)
                section_title = sections.get('title') or sections.get('section_title')
            
            # Format categories as list of strings
            category_list = categories if isinstance(categories, list) else []
            category_strings = [str(cat) for cat in category_list]
            
            # Format published date
            published_date = None
            if published:
                if isinstance(published, datetime):
                    published_date = published.isoformat()
                else:
                    published_date = str(published)
            
            chunk_data.append({
                'id': f"{paper_id}_{chunk_index}",
                'vector': embeddings[idx],
                'payload': {
                    'paper_id': paper_id,
                    'chunk_id': chunk_index,
                    'chunk_text': chunk_text,
                    'section_title': section_title,
                    'categories': category_strings,
                    'published_date': published_date,
                    'paper_url': pdf_url,
                }
            })
        
        return chunk_data
        
    except Exception as e:
        logger.error(f"Error chunking and embedding paper {paper.get('id', 'unknown')}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []


@task(name="store_chunks_in_qdrant")
def store_chunks_in_qdrant(chunks: List[Dict], batch_size: int = 100):
    """
    Store chunks in Qdrant vector database.
    
    Args:
        chunks: List of chunk dictionaries with id, vector, and payload
        batch_size: Number of chunks to insert per batch
    """
    logger = get_run_logger()
    try:
        if not chunks:
            logger.warning("No chunks to store")
            return
        
        client = get_qdrant_client()
        collection_name = config.QDRANT_COLLECTION_NAME
        
        # Convert to Qdrant PointStruct format
        # Qdrant requires integer or UUID IDs, so we hash the string ID to an integer
        points = []
        for chunk in chunks:
            # Convert string ID to integer using hash
            # Use abs() to ensure positive integer and modulo to fit in int64 range
            string_id = chunk['id']
            int_id = abs(hash(string_id)) % (2**63 - 1)  # Fit in int64 range
            
            points.append(
                PointStruct(
                    id=int_id,
                    vector=chunk['vector'],
                    payload={
                        **chunk['payload'],
                        'id': string_id  # Keep original string ID in payload for reference
                    }
                )
            )
        
        # Insert in batches
        total_chunks = len(points)
        for i in range(0, total_chunks, batch_size):
            batch = points[i:i + batch_size]
            client.upsert(
                collection_name=collection_name,
                points=batch
            )
            logger.info(f"Stored batch {i//batch_size + 1} ({len(batch)} chunks)")
        
        logger.info(f"✓ Successfully stored {total_chunks} chunks in Qdrant")
        
    except Exception as e:
        logger.error(f"Error storing chunks in Qdrant: {e}")
        raise


@task(name="mark_paper_as_chunked")
def mark_paper_as_chunked(paper_id: int):
    """
    Mark a paper as chunked in the database.
    
    Args:
        paper_id: Database ID of the paper
    """
    logger = get_run_logger()
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute(
            "UPDATE papers SET chunked = TRUE WHERE id = %s",
            (paper_id,)
        )
        
        conn.commit()
        cur.close()
        conn.close()
        
        logger.debug(f"Marked paper {paper_id} as chunked")
        
    except Exception as e:
        logger.error(f"Error marking paper {paper_id} as chunked: {e}")
        raise


@flow(name="arxiv_paper_embedding", log_prints=True)
def arxiv_paper_embedding_flow(
    limit: Optional[int] = None,
    batch_size: int = 100
):
    """
    Main flow for chunking papers and storing embeddings in Qdrant.
    
    Args:
        limit: Maximum number of papers to process (None for all)
        batch_size: Number of chunks to insert per batch in Qdrant
    """
    logger = get_run_logger()
    
    try:
        # Ensure database schema is up to date (migration for chunked column)
        logger.info("Ensuring database schema is up to date...")
        ensure_schema_up_to_date()
        
        # Initialize embedding model
        logger.info(f"Initializing embedding model: {config.EMBEDDING_PROVIDER}")
        embedding_model = get_embedding_model()
        
        # Get embedding dimension
        logger.info("Getting embedding dimension...")
        embedding_dim = get_embedding_dimension()
        logger.info(f"Embedding dimension: {embedding_dim}")
        
        # Initialize Qdrant collection
        initialize_qdrant_collection(embedding_dim)
        
        # Retrieve papers
        logger.info("Retrieving papers for chunking...")
        papers = retrieve_papers_for_chunking(limit=limit)
        
        if not papers:
            logger.info("No papers to process")
            return
        
        logger.info(f"Processing {len(papers)} papers...")
        
        # Process each paper
        total_chunks = 0
        for paper in papers:
            paper_id = paper['id']
            arxiv_id = paper.get('arxiv_id', 'unknown')
            
            logger.info(f"Processing paper {paper_id} ({arxiv_id})...")
            
            # Chunk and embed
            chunks = chunk_and_embed_paper(
                paper=paper,
                embedding_model=embedding_model,
                embedding_dim=embedding_dim
            )
            
            if chunks:
                # Store in Qdrant
                store_chunks_in_qdrant(chunks, batch_size=batch_size)
                total_chunks += len(chunks)
                
                # Mark as chunked
                mark_paper_as_chunked(paper_id)
                
                logger.info(f"✓ Completed paper {paper_id} ({len(chunks)} chunks)")
            else:
                logger.warning(f"No chunks created for paper {paper_id}, skipping")
        
        logger.info(f"✓ Embedding flow completed. Processed {len(papers)} papers, created {total_chunks} chunks")
        
    except Exception as e:
        logger.error(f"Error in embedding flow: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise


if __name__ == "__main__":
    # Run the flow
    arxiv_paper_embedding_flow()

