"""
OpenAI LLM Provider

Implementation for OpenAI GPT models (GPT-3.5, GPT-4, etc.)
"""

import tiktoken
from typing import Optional

from openai import OpenAI

from retrieval.services.llm_providers.base import LLMProvider


class OpenAIProvider(LLMProvider):
    """OpenAI provider implementation"""

    def __init__(self, model: str, api_key: str, **kwargs):
        """
        Initialize OpenAI provider.
        
        Args:
            model: Model name (e.g., "gpt-4", "gpt-3.5-turbo")
            api_key: OpenAI API key
            **kwargs: Additional OpenAI client configuration
        """
        super().__init__(model, **kwargs)
        self.client = OpenAI(api_key=api_key, **kwargs)
        self._encoding = None

    def generate(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """Generate text using OpenAI API"""
        messages = []
        
        if system_message:
            messages.append({"role": "system", "content": system_message})
        
        messages.append({"role": "user", "content": prompt})
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        return response.choices[0].message.content

    def count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken"""
        if self._encoding is None:
            # Try to get encoding for the model, fallback to cl100k_base
            try:
                self._encoding = tiktoken.encoding_for_model(self.model)
            except KeyError:
                self._encoding = tiktoken.get_encoding("cl100k_base")
        
        return len(self._encoding.encode(text))

    def stream(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        """Generate text with streaming"""
        messages = []
        
        if system_message:
            messages.append({"role": "system", "content": system_message})
        
        messages.append({"role": "user", "content": prompt})
        
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs
        )
        
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


