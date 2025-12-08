"""
Query Simplification Service

Simplifies complex queries into searchable sub-queries using LLM inference.
"""

import json
from typing import List, Dict, Optional

from retrieval.services.llm import LLMService
from retrieval.config import settings
from retrieval.utils.logger import logger


class QuerySimplifier:
    """Service for simplifying complex queries"""

    def __init__(self, llm_service: Optional[LLMService] = None):
        """
        Initialize query simplifier.
        
        Args:
            llm_service: Optional LLM service instance (creates new if not provided)
        """
        self.llm_service = llm_service or LLMService()
        self.prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        """Load query simplification prompt template"""
        try:
            from pathlib import Path
            prompt_path = Path(__file__).parent.parent / "prompts" / "query_simplification.txt"
            if prompt_path.exists():
                return prompt_path.read_text()
        except Exception as e:
            logger.warning(f"Could not load prompt template: {e}")
        
        # Fallback to inline template
        return """You are a query simplification assistant. Break down complex queries into simpler searchable queries.

For multi-hop questions, create multiple sub-queries. For single-hop questions, create 1-2 simplified queries.

Return JSON format:
{
  "simplified_queries": ["query1", "query2", ...],
  "query_type": "single-hop" or "multi-hop",
  "reasoning": "optional explanation"
}

Query to simplify: {query}"""

    def simplify(self, query: str) -> Dict:
        """
        Simplify a query into searchable sub-queries.
        
        Args:
            query: Original user query
            
        Returns:
            Dictionary with:
                - simplified_queries: List of simplified queries
                - query_type: "single-hop" or "multi-hop"
                - reasoning: Optional explanation
        """
        try:
            # Format prompt
            if "{query}" in self.prompt_template:
                prompt = self.prompt_template.format(query=query)
            else:
                prompt = f"{self.prompt_template}\n\nQuery to simplify: {query}"
            
            # Generate simplification
            response = self.llm_service.generate(
                prompt=prompt,
                temperature=0.3,  # Lower temperature for more consistent output
                max_tokens=500,
            )
            
            # Parse JSON response
            result = self._parse_response(response)
            
            # Validate result
            if not result.get("simplified_queries"):
                logger.warning("No simplified queries returned, using original query")
                return {
                    "simplified_queries": [query],
                    "query_type": "single-hop",
                    "reasoning": "Fallback to original query"
                }
            
            logger.info(
                f"Simplified query into {len(result['simplified_queries'])} sub-queries "
                f"(type: {result.get('query_type', 'unknown')})"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error simplifying query: {e}")
            # Fallback to original query
            return {
                "simplified_queries": [query],
                "query_type": "single-hop",
                "reasoning": f"Error during simplification: {str(e)}"
            }

    def _parse_response(self, response: str) -> Dict:
        """
        Parse LLM response into structured format.
        
        Args:
            response: Raw LLM response
            
        Returns:
            Parsed dictionary
        """
        # Try to extract JSON from response
        response = response.strip()
        
        # Remove markdown code blocks if present
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON object from text
            import re
            json_match = re.search(r'\{[^{}]*"simplified_queries"[^{}]*\}', response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    pass
            
            # Last resort: try to extract queries from text
            logger.warning("Could not parse JSON, attempting text extraction")
            queries = []
            for line in response.split("\n"):
                line = line.strip()
                if line and (line.startswith("-") or line.startswith("•") or line.startswith("*")):
                    query = line.lstrip("-•*").strip()
                    if query:
                        queries.append(query)
            
            if queries:
                return {
                    "simplified_queries": queries,
                    "query_type": "multi-hop" if len(queries) > 1 else "single-hop",
                    "reasoning": "Extracted from text response"
                }
            
            # Ultimate fallback
            raise ValueError("Could not parse response into structured format")


