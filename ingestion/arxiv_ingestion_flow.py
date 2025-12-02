"""
arXiv AI Paper Ingestion Flow using Prefect, PostgreSQL, and Docling

This flow continuously retrieves papers from arXiv API related to artificial intelligence,
parses PDFs using docling, and stores all paper data in PostgreSQL database.
"""

import json
import time
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Optional, Tuple

import arxiv
import psycopg2
from docling.document_converter import DocumentConverter
from prefect import flow, task
from prefect import get_run_logger

from ingestion.config import config


def get_db_connection():
    """
    Create and return a PostgreSQL database connection.
    Reads connection details from configuration.
    
    Returns:
        psycopg2.connection: Database connection object
        
    Raises:
        Exception: If connection cannot be established
    """
    # Try DATABASE_URL first
    if config.DATABASE_URL:
        return psycopg2.connect(config.DATABASE_URL)
    
    # Fallback to individual environment variables
    db_config = {
        "host": config.DB_HOST,
        "port": config.DB_PORT,
        "database": config.DB_NAME,
        "user": config.DB_USER,
        "password": config.DB_PASSWORD,
    }
    
    if not db_config["database"] or not db_config["user"]:
        raise ValueError(
            "Database configuration missing. Set DATABASE_URL or "
            "DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD"
        )
    
    return psycopg2.connect(**db_config)


@task(name="initialize_database_schema")
def initialize_database_schema():
    """
    Initialize the database schema by creating the papers table if it doesn't exist.
    """
    logger = get_run_logger()
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(config.CREATE_TABLE_SQL)
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
        cur.execute("SELECT EXISTS(SELECT 1 FROM papers WHERE arxiv_id = %s)", (arxiv_id,))
        exists = cur.fetchone()[0]
        cur.close()
        conn.close()
        return exists
    except Exception as e:
        logger.error(f"Error checking if paper exists: {e}")
        # On error, assume paper doesn't exist to allow processing
        return False


@task(name="download_pdf_temp")
def download_pdf_temp(paper: arxiv.Result) -> Optional[bytes]:
    """
    Download PDF from arXiv temporarily (in-memory) for parsing.
    
    Args:
        paper: arxiv.Result object
        
    Returns:
        PDF content as bytes, or None if download fails
    """
    logger = get_run_logger()
    try:
        import requests
        paper_id = paper.entry_id.split("/")[-1]
        logger.info(f"Downloading PDF for {paper_id}: {paper.title[:50]}...")
        
        # Download PDF from arXiv
        response = requests.get(paper.pdf_url, timeout=30)
        response.raise_for_status()
        
        pdf_bytes = response.content
        logger.info(f"Successfully downloaded PDF ({len(pdf_bytes)} bytes) for {paper_id}")
        return pdf_bytes
    except Exception as e:
        logger.error(f"Error downloading PDF for {paper.entry_id}: {e}")
        return None


@task(name="parse_pdf_with_docling")
def parse_pdf_with_docling(pdf_bytes: bytes) -> Tuple[Optional[str], Optional[Dict], Optional[Dict], Optional[Dict]]:
    """
    Parse PDF using docling to extract raw text, sections, and references.
    
    Args:
        pdf_bytes: PDF content as bytes
        
    Returns:
        Tuple of (raw_text, sections_json, references_json, parser_metadata)
        Returns None values if parsing fails
    """
    logger = get_run_logger()
    try:
        logger.info("Initializing docling converter...")
        converter = DocumentConverter()
        
        logger.info("Parsing PDF with docling...")
        # Convert PDF bytes to document
        doc = converter.convert(BytesIO(pdf_bytes))
        
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
        
        # Extract sections - try to get structured document
        sections = []
        doc_dict = {}
        try:
            if hasattr(doc, 'document') and hasattr(doc.document, 'export_to_dict'):
                doc_dict = doc.document.export_to_dict()
            elif hasattr(doc, 'export_to_dict'):
                doc_dict = doc.export_to_dict()
            
            if isinstance(doc_dict, dict):
                # Extract sections from document structure
                sections = doc_dict.get('sections', [])
                if not sections and 'content' in doc_dict:
                    # Try to extract from content
                    content = doc_dict.get('content', [])
                    sections = [item for item in content if isinstance(item, dict) and 'type' in item]
                elif not sections and 'body' in doc_dict:
                    # Try body structure
                    body = doc_dict.get('body', {})
                    if isinstance(body, dict):
                        sections = body.get('sections', [])
        except Exception as e:
            logger.warning(f"Could not extract sections: {e}")
        
        # Extract references - look for citations/references in the document
        references = []
        try:
            if hasattr(doc, 'document') and hasattr(doc.document, 'references'):
                references = doc.document.references
            elif isinstance(doc_dict, dict):
                references = doc_dict.get('references', [])
                if not references and 'bibliography' in doc_dict:
                    references = doc_dict.get('bibliography', [])
        except Exception as e:
            logger.warning(f"Could not extract references: {e}")
        
        # Create parser metadata
        parser_metadata = {
            "parser_version": "docling",
            "parsing_timestamp": datetime.utcnow().isoformat(),
            "pdf_size_bytes": len(pdf_bytes),
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
    Store paper data in PostgreSQL database.
    Uses INSERT ... ON CONFLICT for upsert functionality.
    
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
        
        date_processed = datetime.utcnow() if pdf_processed else None
        
        # Upsert query
        upsert_sql = """
        INSERT INTO papers (
            arxiv_id, entry_id, title, authors, summary, published, updated,
            categories, primary_category, pdf_url, doi, journal_ref,
            raw_text, sections, references, parser_used, parser_metadata,
            pdf_processed, date_processed, created_at, modified_at
        ) VALUES (
            %s, %s, %s, %s::jsonb, %s, %s, %s,
            %s::jsonb, %s, %s, %s, %s,
            %s, %s::jsonb, %s::jsonb, %s, %s::jsonb,
            %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        ON CONFLICT (arxiv_id) DO UPDATE SET
            entry_id = EXCLUDED.entry_id,
            title = EXCLUDED.title,
            authors = EXCLUDED.authors,
            summary = EXCLUDED.summary,
            published = EXCLUDED.published,
            updated = EXCLUDED.updated,
            categories = EXCLUDED.categories,
            primary_category = EXCLUDED.primary_category,
            pdf_url = EXCLUDED.pdf_url,
            doi = EXCLUDED.doi,
            journal_ref = EXCLUDED.journal_ref,
            raw_text = EXCLUDED.raw_text,
            sections = EXCLUDED.sections,
            references = EXCLUDED.references,
            parser_used = EXCLUDED.parser_used,
            parser_metadata = EXCLUDED.parser_metadata,
            pdf_processed = EXCLUDED.pdf_processed,
            date_processed = EXCLUDED.date_processed,
            modified_at = CURRENT_TIMESTAMP
        """
        
        cur.execute(upsert_sql, (
            paper_id,
            paper.entry_id,
            paper.title,
            authors_json,
            paper.summary,
            paper.published,
            paper.updated,
            categories_json,
            paper.primary_category,
            paper.pdf_url,
            paper.doi if hasattr(paper, "doi") else None,
            paper.journal_ref if hasattr(paper, "journal_ref") else None,
            raw_text,
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
    Main Prefect flow that orchestrates arXiv paper ingestion with PostgreSQL and docling.
    
    This flow:
    1. Validates configuration
    2. Initializes database schema
    3. Searches for AI-related papers on arXiv
    4. Checks database for existing papers (skip duplicates)
    5. Downloads PDFs temporarily
    6. Parses PDFs with docling
    7. Stores all data in PostgreSQL
    8. Waits configured seconds before processing next paper
    
    Args:
        max_results_per_search: Maximum number of papers to fetch per search 
                                (uses config.MAX_RESULTS_PER_SEARCH if None)
        delay_seconds: Delay between processing each paper 
                      (uses config.RATE_LIMIT_SECONDS if None)
    """
    logger = get_run_logger()
    logger.info("Starting arXiv AI Paper Ingestion Flow with PostgreSQL and Docling")
    
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
                    
                    # Download PDF temporarily
                    pdf_bytes = download_pdf_temp(paper)
                    if not pdf_bytes:
                        logger.warning(f"Failed to download PDF for {paper_id}, storing metadata only")
                        # Store paper with metadata only (pdf_processed=False)
                        store_paper_in_db(paper, None, None, None, None, False)
                        continue
                    
                    # Parse PDF with docling
                    raw_text, sections, references, parser_metadata = parse_pdf_with_docling(pdf_bytes)
                    
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
