"""
Anthropic LLM Provider

Implementation for Anthropic Claude models (optional provider)
"""

import tiktoken
from typing import Optional

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from retrieval.services.llm_providers.base import LLMProvider


class AnthropicProvider(LLMProvider):
    """Anthropic provider implementation for Claude models"""

    def __init__(self, model: str, api_key: str, **kwargs):
        """
        Initialize Anthropic provider.
        
        Args:
            model: Model name (e.g., "claude-3-opus", "claude-3-sonnet", "claude-3-haiku")
            api_key: Anthropic API key
            **kwargs: Additional Anthropic client configuration
        """
        if not ANTHROPIC_AVAILABLE:
            raise ImportError(
                "anthropic is required for Anthropic provider. "
                "Install with: pip install anthropic"
            )
        
        super().__init__(model, **kwargs)
        self.client = Anthropic(api_key=api_key, **kwargs)
        self._encoding = None

    def generate(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """Generate text using Anthropic API"""
        # Anthropic uses max_tokens as required parameter
        if max_tokens is None:
            max_tokens = 4096  # Default for Claude
        
        message = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_message if system_message else "",
            messages=[
                {"role": "user", "content": prompt}
            ],
            **kwargs
        )
        
        # Extract text from response
        if message.content and len(message.content) > 0:
            return message.content[0].text
        return ""

    def count_tokens(self, text: str) -> int:
        """Count tokens using Anthropic's tokenizer"""
        if self._encoding is None:
            # Anthropic uses cl100k_base encoding
            self._encoding = tiktoken.get_encoding("cl100k_base")
        
        return len(self._encoding.encode(text))


