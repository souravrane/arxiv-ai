"""
arXiv AI Paper Ingestion Flow using Prefect, MySQL, and Docling

This flow continuously retrieves papers from arXiv API related to artificial intelligence,
parses PDFs using docling, and stores all paper data in MySQL database.
"""

import json
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import arxiv
import mysql.connector
from docling.document_converter import DocumentConverter
from prefect import flow, task
from prefect import get_run_logger

try:
    from .config import config
except ImportError:
    # Handle case when running as a script
    from config import config


def sanitize_text(text: Optional[str]) -> Optional[str]:
    """
    Sanitize text by removing control characters, normalizing whitespace,
    and ensuring valid UTF-8 encoding.
    
    Args:
        text: Text to sanitize (can be None)
        
    Returns:
        Sanitized text or None if input was None
    """
    if not text:
        return text
    
    # Remove control characters except newlines and tabs
    text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    
    # Normalize whitespace (keep newlines but clean up excessive spaces)
    text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces/tabs to single space
    text = re.sub(r'\n{3,}', '\n\n', text)  # Max 2 consecutive newlines
    
    # Ensure UTF-8 encoding (remove invalid characters)
    text = text.encode('utf-8', errors='ignore').decode('utf-8')
    
    # Remove leading/trailing whitespace
    text = text.strip()
    
    return text


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


@task(name="initialize_database_schema")
def initialize_database_schema():
    """
    Initialize the database schema by creating the papers table if it doesn't exist.
    """
    logger = get_run_logger()
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Execute the full SQL (table + indexes)
        # MySQL doesn't support IF NOT EXISTS for CREATE INDEX, so we'll catch those errors
        sql_statements = [s.strip() for s in config.CREATE_TABLE_SQL.split(';') if s.strip()]
        
        for sql in sql_statements:
            try:
                cur.execute(sql)
            except mysql.connector.Error as e:
                # Ignore errors for indexes that already exist (error code 1061)
                # Also ignore table already exists (error code 1050)
                if e.errno == 1061:  # Duplicate key name
                    logger.debug(f"Index already exists, skipping")
                elif e.errno == 1050:  # Table already exists
                    logger.debug(f"Table already exists, skipping")
                else:
                    # Re-raise other errors
                    raise
        
        # Check if table exists and alter raw_text column if needed
        # This migration ensures existing tables are updated to support larger documents
        try:
            cur.execute("""
                SELECT COLUMN_TYPE 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = 'papers' 
                AND COLUMN_NAME = 'raw_text'
            """)
            result = cur.fetchone()
            if result:
                column_type = result[0].upper()
                logger.debug(f"Current raw_text column type: {column_type}")
                # Check if it's TEXT (not MEDIUMTEXT or LONGTEXT)
                if 'TEXT' in column_type and 'MEDIUMTEXT' not in column_type and 'LONGTEXT' not in column_type:
                    logger.info("Altering raw_text column from TEXT to MEDIUMTEXT to support larger documents...")
                    cur.execute("ALTER TABLE papers MODIFY COLUMN raw_text MEDIUMTEXT")
                    conn.commit()
                    logger.info("✓ Successfully altered raw_text column to MEDIUMTEXT")
                else:
                    logger.debug(f"raw_text column is already {column_type}, no migration needed")
            else:
                logger.debug("raw_text column not found (table may not exist yet)")
        except mysql.connector.Error as e:
            logger.warning(f"Could not check/alter raw_text column: {e}")
            # Don't fail the whole initialization if migration check fails
        
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
        logger.info("Database schema initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database schema: {e}")
        raise


@task(name="search_arxiv_ai_papers")
def search_arxiv_ai_papers(max_results: Optional[int] = None) -> List[arxiv.Result]:
    """
    Search arXiv for AI-related papers.
    
    Args:
        max_results: Maximum number of results to return (uses config default if None)
        
    Returns:
        List of arxiv.Result objects
    """
    logger = get_run_logger()
    try:
        if max_results is None:
            max_results = config.MAX_RESULTS_PER_SEARCH
        
        search_query = config.get_search_query()
        logger.info(f"Searching arXiv for AI papers with query: {search_query}")
        search = arxiv.Search(
            query=search_query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending
        )
        results = list(search.results())
        logger.info(f"Found {len(results)} papers")
        return results
    except Exception as e:
        logger.error(f"Error searching arXiv: {e}")
        raise


@task(name="check_paper_exists")
def check_paper_exists(arxiv_id: str) -> bool:
    """
    Check if a paper already exists in the database.
    
    Args:
        arxiv_id: arXiv paper ID
        
    Returns:
        True if paper exists, False otherwise
    """
    logger = get_run_logger()
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM papers WHERE arxiv_id = %s", (arxiv_id,))
        result = cur.fetchone()
        exists = result[0] > 0 if result else False
        cur.close()
        conn.close()
        return exists
    except Exception as e:
        logger.error(f"Error checking if paper exists: {e}")
        # On error, assume paper doesn't exist to allow processing
        return False


@task(name="download_pdf")
def download_pdf(paper: arxiv.Result) -> Optional[str]:
    """
    Download PDF from arXiv and save to storage folder.
    
    Args:
        paper: arxiv.Result object
        
    Returns:
        Path to downloaded PDF file, or None if download fails
    """
    logger = get_run_logger()
    try:
        import requests
        
        paper_id = paper.entry_id.split("/")[-1]
        logger.info(f"Downloading PDF for {paper_id}: {paper.title[:50]}...")
        
        # Create PDF storage directory if it doesn't exist
        pdf_dir = Path(config.PDF_STORAGE_DIR)
        pdf_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename: arxiv_id.pdf
        pdf_filename = f"{paper_id}.pdf"
        pdf_path = pdf_dir / pdf_filename
        
        # Check if PDF already exists
        if pdf_path.exists():
            logger.info(f"PDF already exists at {pdf_path}, skipping download")
            return str(pdf_path)
        
        # Download PDF from arXiv
        response = requests.get(paper.pdf_url, timeout=30)
        response.raise_for_status()
        
        # Save PDF to file
        with open(pdf_path, 'wb') as f:
            f.write(response.content)
        
        file_size = pdf_path.stat().st_size
        logger.info(f"Successfully downloaded PDF to {pdf_path} ({file_size} bytes)")
        return str(pdf_path)
        
    except Exception as e:
        logger.error(f"Error downloading PDF for {paper.entry_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


@task(name="parse_pdf_with_docling")
def parse_pdf_with_docling(pdf_path: str) -> Tuple[Optional[str], Optional[Dict], Optional[Dict], Optional[Dict]]:
    """
    Parse PDF using docling to extract raw text, sections, and references.
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        Tuple of (raw_text, sections_json, references_json, parser_metadata)
        Returns None values if parsing fails
    """
    logger = get_run_logger()
    try:
        # Verify PDF file exists
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            logger.error(f"PDF file not found: {pdf_path}")
            return None, None, None, None
        
        logger.info(f"Parsing PDF from {pdf_path}...")
        logger.info("Initializing docling converter...")
        # Configure converter to extract structured content (sections, references)
        # Note: Some docling versions may require specific configuration
        try:
            # Try with default configuration first
            converter = DocumentConverter()
        except Exception as e:
            logger.warning(f"Error initializing DocumentConverter with defaults: {e}")
            # Fallback: try with minimal configuration
            converter = DocumentConverter()
        
        logger.info("Converting PDF with docling...")
        # Convert PDF file to document (docling requires a file path)
        doc = converter.convert(str(pdf_path))
        
        # Log document structure for debugging
        logger.debug(f"Document type: {type(doc)}")
        if hasattr(doc, 'document'):
            logger.debug(f"Document.document type: {type(doc.document)}")
            logger.debug(f"Document.document attributes: {dir(doc.document)[:20]}")
        
        # Extract raw text - try multiple methods
        raw_text = None
        try:
            if hasattr(doc, 'document') and hasattr(doc.document, 'export_to_markdown'):
                raw_text = doc.document.export_to_markdown()
            elif hasattr(doc, 'document') and hasattr(doc.document, 'export_to_text'):
                raw_text = doc.document.export_to_text()
            elif hasattr(doc, 'document'):
                raw_text = str(doc.document)
            else:
                raw_text = str(doc)
        except Exception as e:
            logger.warning(f"Could not extract raw text using standard methods: {e}")
            raw_text = str(doc) if doc else None
        
        # Extract sections - try multiple methods to get structured document
        sections = []
        doc_dict = {}
        try:
            # Method 1: Try export_to_dict if available
            if hasattr(doc, 'document') and hasattr(doc.document, 'export_to_dict'):
                try:
                    doc_dict = doc.document.export_to_dict()
                    logger.debug("Got doc_dict from doc.document.export_to_dict()")
                except Exception as e:
                    logger.debug(f"export_to_dict() failed: {e}")
            
            # Method 2: Try direct export_to_dict on doc
            if not doc_dict and hasattr(doc, 'export_to_dict'):
                try:
                    doc_dict = doc.export_to_dict()
                    logger.debug("Got doc_dict from doc.export_to_dict()")
                except Exception as e:
                    logger.debug(f"doc.export_to_dict() failed: {e}")
            
            # Method 3: Try accessing document structure directly
            if not doc_dict and hasattr(doc, 'document'):
                try:
                    # Try to convert document to dict manually
                    doc_obj = doc.document
                    if hasattr(doc_obj, '__dict__'):
                        doc_dict = doc_obj.__dict__
                        logger.debug("Got doc_dict from doc.document.__dict__")
                except Exception as e:
                    logger.debug(f"Accessing __dict__ failed: {e}")
            
            # Extract sections from doc_dict
            if isinstance(doc_dict, dict):
                # Try various paths for sections
                sections = doc_dict.get('sections', [])
                if not sections:
                    sections = doc_dict.get('body', {}).get('sections', []) if isinstance(doc_dict.get('body'), dict) else []
                if not sections and 'content' in doc_dict:
                    # Extract sections from content array
                    content = doc_dict.get('content', [])
                    if isinstance(content, list):
                        sections = [
                            item for item in content 
                            if isinstance(item, dict) and (
                                item.get('type') == 'section' or 
                                item.get('type') == 'heading' or
                                'title' in item or
                                'heading' in item
                            )
                        ]
                if not sections and 'body' in doc_dict:
                    body = doc_dict.get('body', {})
                    if isinstance(body, dict):
                        sections = body.get('sections', [])
                        if not sections and 'content' in body:
                            body_content = body.get('content', [])
                            if isinstance(body_content, list):
                                sections = [
                                    item for item in body_content
                                    if isinstance(item, dict) and (
                                        item.get('type') == 'section' or
                                        'title' in item
                                    )
                                ]
            
            # Method 4: Try accessing sections directly from document object
            if not sections and hasattr(doc, 'document'):
                try:
                    doc_obj = doc.document
                    if hasattr(doc_obj, 'sections'):
                        sections = doc_obj.sections
                        logger.debug(f"Got sections directly from doc.document.sections: {len(sections)}")
                    elif hasattr(doc_obj, 'body') and hasattr(doc_obj.body, 'sections'):
                        sections = doc_obj.body.sections
                        logger.debug(f"Got sections from doc.document.body.sections: {len(sections)}")
                except Exception as e:
                    logger.debug(f"Direct section access failed: {e}")
            
            # Convert sections to list of dicts if needed
            if sections and not isinstance(sections, list):
                sections = [sections] if sections else []
            
            # Ensure sections are serializable
            if sections:
                sections = [
                    item if isinstance(item, dict) else {'content': str(item), 'type': 'section'}
                    for item in sections
                ]
            
            logger.info(f"Extracted {len(sections)} sections")
            
        except Exception as e:
            logger.warning(f"Could not extract sections: {e}")
            import traceback
            logger.debug(traceback.format_exc())
        
        # Extract references - try multiple methods
        references = []
        try:
            # Method 1: Try from doc_dict
            if isinstance(doc_dict, dict):
                references = doc_dict.get('references', [])
                if not references:
                    references = doc_dict.get('bibliography', [])
                if not references and 'body' in doc_dict:
                    body = doc_dict.get('body', {})
                    if isinstance(body, dict):
                        references = body.get('references', [])
                        if not references:
                            references = body.get('bibliography', [])
            
            # Method 2: Try direct access from document object
            if not references and hasattr(doc, 'document'):
                try:
                    doc_obj = doc.document
                    if hasattr(doc_obj, 'references'):
                        refs = doc_obj.references
                        if refs:
                            references = refs if isinstance(refs, list) else [refs]
                            logger.debug(f"Got references directly from doc.document.references: {len(references)}")
                    elif hasattr(doc_obj, 'bibliography'):
                        refs = doc_obj.bibliography
                        if refs:
                            references = refs if isinstance(refs, list) else [refs]
                            logger.debug(f"Got references from doc.document.bibliography: {len(references)}")
                except Exception as e:
                    logger.debug(f"Direct reference access failed: {e}")
            
            # Ensure references are serializable
            if references and not isinstance(references, list):
                references = [references] if references else []
            
            if references:
                references = [
                    ref if isinstance(ref, dict) else {'text': str(ref), 'type': 'reference'}
                    for ref in references
                ]
            
            logger.info(f"Extracted {len(references)} references")
            
        except Exception as e:
            logger.warning(f"Could not extract references: {e}")
            import traceback
            logger.debug(traceback.format_exc())
        
        # Get PDF file size
        pdf_file = Path(pdf_path)
        pdf_size = pdf_file.stat().st_size if pdf_file.exists() else 0
        
        # Create parser metadata
        parser_metadata = {
            "parser_version": "docling",
            "parsing_timestamp": datetime.now(timezone.utc).isoformat(),
            "pdf_path": str(pdf_path),
            "pdf_size_bytes": pdf_size,
            "raw_text_length": len(raw_text) if raw_text else 0,
            "num_sections": len(sections) if sections else 0,
            "num_references": len(references) if references else 0,
        }
        
        logger.info(f"Successfully parsed PDF: {len(raw_text) if raw_text else 0} chars, {len(sections)} sections, {len(references)} references")
        
        return raw_text, sections, references, parser_metadata
        
    except Exception as e:
        logger.error(f"Error parsing PDF with docling: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None, None, None, None


@task(name="store_paper_in_db")
def store_paper_in_db(
    paper: arxiv.Result,
    raw_text: Optional[str],
    sections: Optional[Dict],
    references: Optional[Dict],
    parser_metadata: Optional[Dict],
    pdf_processed: bool
) -> bool:
    """
    Store paper data in MySQL database.
    Uses INSERT ... ON DUPLICATE KEY UPDATE for upsert functionality.
    
    Args:
        paper: arxiv.Result object
        raw_text: Parsed raw text from PDF
        sections: Structured sections as JSON
        references: References as JSON
        parser_metadata: Parser metadata as JSON
        pdf_processed: Whether PDF was successfully processed
        
    Returns:
        True if storage successful, False otherwise
    """
    logger = get_run_logger()
    try:
        paper_id = paper.entry_id.split("/")[-1]
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Prepare data
        authors_json = json.dumps([author.name for author in paper.authors])
        categories_json = json.dumps(paper.categories) if paper.categories else None
        sections_json = json.dumps(sections) if sections else None
        references_json = json.dumps(references) if references else None
        parser_metadata_json = json.dumps(parser_metadata) if parser_metadata else None
        
        # Sanitize text fields before storing
        sanitized_title = sanitize_text(paper.title)
        sanitized_summary = sanitize_text(paper.summary)
        sanitized_raw_text = sanitize_text(raw_text)
        
        date_processed = datetime.now(timezone.utc) if pdf_processed else None
        
        # Upsert query (MySQL syntax)
        upsert_sql = """
        INSERT INTO papers (
            arxiv_id, entry_id, title, authors, summary, published, updated,
            categories, primary_category, pdf_url, doi, journal_ref,
            raw_text, sections, `references`, parser_used, parser_metadata,
            pdf_processed, date_processed, created_at, modified_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        ON DUPLICATE KEY UPDATE
            entry_id = VALUES(entry_id),
            title = VALUES(title),
            authors = VALUES(authors),
            summary = VALUES(summary),
            published = VALUES(published),
            updated = VALUES(updated),
            categories = VALUES(categories),
            primary_category = VALUES(primary_category),
            pdf_url = VALUES(pdf_url),
            doi = VALUES(doi),
            journal_ref = VALUES(journal_ref),
            raw_text = VALUES(raw_text),
            sections = VALUES(sections),
            `references` = VALUES(`references`),
            parser_used = VALUES(parser_used),
            parser_metadata = VALUES(parser_metadata),
            pdf_processed = VALUES(pdf_processed),
            date_processed = VALUES(date_processed),
            modified_at = CURRENT_TIMESTAMP
        """
        
        cur.execute(upsert_sql, (
            paper_id,
            paper.entry_id,
            sanitized_title,
            authors_json,
            sanitized_summary,
            paper.published,
            paper.updated,
            categories_json,
            paper.primary_category,
            paper.pdf_url,
            paper.doi if hasattr(paper, "doi") else None,
            paper.journal_ref if hasattr(paper, "journal_ref") else None,
            sanitized_raw_text,
            sections_json,
            references_json,
            "docling" if pdf_processed else None,
            parser_metadata_json,
            pdf_processed,
            date_processed,
        ))
        
        conn.commit()
        cur.close()
        conn.close()
        
        logger.info(f"Successfully stored paper {paper_id} in database (pdf_processed={pdf_processed})")
        return True
        
    except Exception as e:
        logger.error(f"Error storing paper {paper.entry_id} in database: {e}")
        return False


@flow(name="arxiv_ai_paper_ingestion", log_prints=True)
def arxiv_ai_paper_ingestion_flow(
    max_results_per_search: Optional[int] = None,
    delay_seconds: Optional[int] = None
):
    """
    Main Prefect flow that orchestrates arXiv paper ingestion with MySQL and docling.
    
    This flow:
    1. Validates configuration
    2. Initializes database schema
    3. Searches for AI-related papers on arXiv
    4. Checks database for existing papers (skip duplicates)
    5. Downloads PDFs temporarily
    6. Parses PDFs with docling
    7. Stores all data in MySQL
    8. Waits configured seconds before processing next paper
    
    Args:
        max_results_per_search: Maximum number of papers to fetch per search 
                                (uses config.MAX_RESULTS_PER_SEARCH if None)
        delay_seconds: Delay between processing each paper 
                      (uses config.RATE_LIMIT_SECONDS if None)
    """
    logger = get_run_logger()
    logger.info("Starting arXiv AI Paper Ingestion Flow with MySQL and Docling")
    
    # Validate configuration
    try:
        config.validate()
    except ValueError as e:
        logger.error(f"Configuration validation failed: {e}")
        logger.error("Please check your .env file and configuration")
        return
    
    # Use config values if not provided
    if max_results_per_search is None:
        max_results_per_search = config.MAX_RESULTS_PER_SEARCH
    if delay_seconds is None:
        delay_seconds = config.RATE_LIMIT_SECONDS
    
    logger.info(f"Configuration: max_results={max_results_per_search}, rate_limit={delay_seconds}s")
    logger.info(f"arXiv categories: {', '.join(config.ARXIV_CATEGORIES)}")
    
    # Initialize database schema
    try:
        initialize_database_schema()
    except Exception as e:
        logger.error(f"Failed to initialize database schema: {e}")
        logger.error("Please check your database connection and try again")
        return
    
    # Continuously search and process papers
    iteration = 0
    while True:
        try:
            iteration += 1
            logger.info(f"=== Iteration {iteration} ===")
            
            # Search for new papers
            papers = search_arxiv_ai_papers(max_results=max_results_per_search)
            
            if not papers:
                logger.warning("No papers found in search")
                time.sleep(delay_seconds)
                continue
            
            # Process each paper
            for paper in papers:
                try:
                    paper_id = paper.entry_id.split("/")[-1]
                    
                    # Check if already in database
                    if check_paper_exists(paper_id):
                        logger.info(f"Paper {paper_id} already exists in database, skipping")
                        continue
                    
                    logger.info(f"Processing paper: {paper_id} - {paper.title[:60]}...")
                    
                    # Download PDF to storage folder
                    pdf_path = download_pdf(paper)
                    if not pdf_path:
                        logger.warning(f"Failed to download PDF for {paper_id}, storing metadata only")
                        # Store paper with metadata only (pdf_processed=False)
                        store_paper_in_db(paper, None, None, None, None, False)
                        continue
                    
                    # Parse PDF with docling
                    raw_text, sections, references, parser_metadata = parse_pdf_with_docling(pdf_path)
                    
                    # Optionally clean up PDF file after parsing if configured
                    if not config.KEEP_PDFS:
                        try:
                            pdf_file = Path(pdf_path)
                            if pdf_file.exists():
                                pdf_file.unlink()
                                logger.debug(f"Deleted PDF file: {pdf_path}")
                        except Exception as e:
                            logger.warning(f"Failed to delete PDF file {pdf_path}: {e}")
                    
                    # Determine if PDF was successfully processed
                    pdf_processed = raw_text is not None
                    
                    # Store paper in database
                    store_success = store_paper_in_db(
                        paper, raw_text, sections, references, parser_metadata, pdf_processed
                    )
                    
                    if store_success:
                        logger.info(f"Successfully processed and stored paper: {paper_id}")
                    else:
                        logger.warning(f"Failed to store paper {paper_id} in database")
                    
                    # Wait configured seconds before processing next paper
                    logger.info(f"Waiting {delay_seconds} seconds before next paper...")
                    time.sleep(delay_seconds)
                    
                except Exception as e:
                    logger.error(f"Error processing paper {paper.entry_id}: {e}")
                    continue
            
            logger.info(f"Completed iteration {iteration}, waiting {delay_seconds} seconds before next search...")
            time.sleep(delay_seconds)
            
        except KeyboardInterrupt:
            logger.info("Flow interrupted by user")
            break
        except Exception as e:
            logger.error(f"Error in flow iteration: {e}")
            logger.info(f"Waiting {delay_seconds} seconds before retrying...")
            time.sleep(delay_seconds)


if __name__ == "__main__":
    # Run the flow with configuration from environment variables
    arxiv_ai_paper_ingestion_flow()
