"""
Base LLM Provider

Abstract base class for all LLM provider implementations.
"""

from abc import ABC, abstractmethod
from typing import Optional


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    All LLM providers must implement this interface to ensure
    plug-and-play compatibility.
    """

    def __init__(self, model: str, **kwargs):
        """
        Initialize the LLM provider.
        
        Args:
            model: Model name/identifier
            **kwargs: Provider-specific configuration
        """
        self.model = model
        self.config = kwargs

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        Generate text from a prompt.
        
        Args:
            prompt: User prompt/question
            system_message: Optional system message/instructions
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters
            
        Returns:
            Generated text response
        """
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """
        Count the number of tokens in a text string.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Number of tokens
        """
        pass

    def stream(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        """
        Generate text with streaming (optional implementation).
        
        Args:
            prompt: User prompt/question
            system_message: Optional system message/instructions
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters
            
        Yields:
            Text chunks as they are generated
        """
        # Default implementation: return full response as single chunk
        response = self.generate(
            prompt=prompt,
            system_message=system_message,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        yield response


