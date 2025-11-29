"""
arXiv AI Paper Ingestion Flow using Prefect

This flow continuously retrieves papers from arXiv API related to artificial intelligence,
downloads PDFs, and stores them locally with metadata.
"""

import json
import os
import time
from pathlib import Path
from typing import List, Optional

import arxiv
from prefect import flow, task
from prefect import get_run_logger


# Configuration
PAPERS_DIR = Path("./papers")
METADATA_DIR = PAPERS_DIR / "metadata"
TRACKING_FILE = PAPERS_DIR / "downloaded_papers.json"

# Ensure directories exist
PAPERS_DIR.mkdir(exist_ok=True)
METADATA_DIR.mkdir(exist_ok=True)

# arXiv search query for AI-related papers
AI_CATEGORIES = [
    "cat:cs.AI",  # Artificial Intelligence
    "cat:cs.LG",  # Machine Learning
    "cat:cs.CV",  # Computer Vision
    "cat:cs.CL",  # Computation and Language
    "cat:cs.NE",  # Neural and Evolutionary Computing
]
SEARCH_QUERY = " OR ".join(AI_CATEGORIES)


@task(name="search_arxiv_ai_papers")
def search_arxiv_ai_papers(max_results: int = 10) -> List[arxiv.Result]:
    """
    Search arXiv for AI-related papers.
    
    Args:
        max_results: Maximum number of results to return
        
    Returns:
        List of arxiv.Result objects
    """
    logger = get_run_logger()
    try:
        logger.info(f"Searching arXiv for AI papers with query: {SEARCH_QUERY}")
        search = arxiv.Search(
            query=SEARCH_QUERY,
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


@task(name="load_downloaded_papers")
def load_downloaded_papers() -> set:
    """
    Load the set of already downloaded paper IDs from tracking file.
    
    Returns:
        Set of paper IDs (strings)
    """
    logger = get_run_logger()
    try:
        if TRACKING_FILE.exists():
            with open(TRACKING_FILE, "r", encoding="utf-8") as f:
                downloaded = json.load(f)
                logger.info(f"Loaded {len(downloaded)} downloaded paper IDs")
                return set(downloaded)
        else:
            logger.info("No tracking file found, starting fresh")
            return set()
    except Exception as e:
        logger.error(f"Error loading downloaded papers: {e}")
        return set()


@task(name="is_paper_downloaded")
def is_paper_downloaded(paper_id: str, downloaded_ids: set) -> bool:
    """
    Check if a paper has already been downloaded.
    
    Args:
        paper_id: arXiv paper ID
        downloaded_ids: Set of downloaded paper IDs
        
    Returns:
        True if paper is already downloaded, False otherwise
    """
    return paper_id in downloaded_ids


@task(name="download_pdf")
def download_pdf(paper: arxiv.Result) -> bool:
    """
    Download PDF from arXiv and save to local directory.
    
    Args:
        paper: arxiv.Result object
        
    Returns:
        True if download successful, False otherwise
    """
    logger = get_run_logger()
    try:
        paper_id = paper.entry_id.split("/")[-1]
        pdf_path = PAPERS_DIR / f"{paper_id}.pdf"
        
        if pdf_path.exists():
            logger.info(f"PDF already exists for {paper_id}, skipping download")
            return True
        
        logger.info(f"Downloading PDF for {paper_id}: {paper.title[:50]}...")
        paper.download_pdf(dirpath=str(PAPERS_DIR), filename=f"{paper_id}.pdf")
        logger.info(f"Successfully downloaded PDF: {pdf_path}")
        return True
    except Exception as e:
        logger.error(f"Error downloading PDF for {paper.entry_id}: {e}")
        return False


@task(name="save_metadata")
def save_metadata(paper: arxiv.Result) -> bool:
    """
    Extract and save paper metadata as JSON file.
    
    Args:
        paper: arxiv.Result object
        
    Returns:
        True if save successful, False otherwise
    """
    logger = get_run_logger()
    try:
        paper_id = paper.entry_id.split("/")[-1]
        metadata_path = METADATA_DIR / f"{paper_id}.json"
        
        # Extract metadata
        metadata = {
            "arxiv_id": paper_id,
            "entry_id": paper.entry_id,
            "title": paper.title,
            "authors": [author.name for author in paper.authors],
            "summary": paper.summary,
            "published": paper.published.isoformat() if paper.published else None,
            "updated": paper.updated.isoformat() if paper.updated else None,
            "categories": paper.categories,
            "primary_category": paper.primary_category,
            "pdf_url": paper.pdf_url,
            "doi": paper.doi if hasattr(paper, "doi") else None,
            "journal_ref": paper.journal_ref if hasattr(paper, "journal_ref") else None,
        }
        
        # Save to JSON file
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved metadata: {metadata_path}")
        return True
    except Exception as e:
        logger.error(f"Error saving metadata for {paper.entry_id}: {e}")
        return False


@task(name="update_tracking_file")
def update_tracking_file(paper_id: str, downloaded_ids: set) -> set:
    """
    Update the tracking file with a new paper ID.
    
    Args:
        paper_id: arXiv paper ID to add
        downloaded_ids: Current set of downloaded paper IDs
        
    Returns:
        Updated set of downloaded paper IDs
    """
    logger = get_run_logger()
    try:
        downloaded_ids.add(paper_id)
        
        # Save to file
        with open(TRACKING_FILE, "w", encoding="utf-8") as f:
            json.dump(list(downloaded_ids), f, indent=2)
        
        logger.info(f"Updated tracking file with paper ID: {paper_id}")
        return downloaded_ids
    except Exception as e:
        logger.error(f"Error updating tracking file: {e}")
        return downloaded_ids


@flow(name="arxiv_ai_paper_ingestion", log_prints=True)
def arxiv_ai_paper_ingestion_flow(max_results_per_search: int = 10, delay_seconds: int = 4):
    """
    Main Prefect flow that orchestrates arXiv paper ingestion.
    
    This flow:
    1. Searches for AI-related papers on arXiv
    2. Filters out already downloaded papers
    3. Downloads PDFs and saves metadata
    4. Updates tracking file
    5. Waits 4 seconds before processing next paper
    
    Args:
        max_results_per_search: Maximum number of papers to fetch per search
        delay_seconds: Delay between processing each paper (default: 4 seconds)
    """
    logger = get_run_logger()
    logger.info("Starting arXiv AI Paper Ingestion Flow")
    
    # Load already downloaded papers
    downloaded_ids = load_downloaded_papers()
    
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
                    
                    # Check if already downloaded
                    if is_paper_downloaded(paper_id, downloaded_ids):
                        logger.info(f"Paper {paper_id} already downloaded, skipping")
                        continue
                    
                    logger.info(f"Processing paper: {paper_id} - {paper.title[:60]}...")
                    
                    # Download PDF
                    pdf_success = download_pdf(paper)
                    if not pdf_success:
                        logger.warning(f"Failed to download PDF for {paper_id}, skipping")
                        continue
                    
                    # Save metadata
                    metadata_success = save_metadata(paper)
                    if not metadata_success:
                        logger.warning(f"Failed to save metadata for {paper_id}")
                    
                    # Update tracking file
                    downloaded_ids = update_tracking_file(paper_id, downloaded_ids)
                    
                    logger.info(f"Successfully processed paper: {paper_id}")
                    
                    # Wait 4 seconds before processing next paper
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
    # Run the flow
    arxiv_ai_paper_ingestion_flow(max_results_per_search=10, delay_seconds=4)

