"""
LM Studio LLM Provider

Implementation for local models via LM Studio (OpenAI-compatible API)
"""

import tiktoken
from typing import Optional

from openai import OpenAI

from retrieval.services.llm_providers.base import LLMProvider


class LMStudioProvider(LLMProvider):
    """LM Studio provider implementation (OpenAI-compatible)"""

    def __init__(self, model: str, base_url: str = "http://localhost:1234/v1", **kwargs):
        """
        Initialize LM Studio provider.
        
        Args:
            model: Model name (as configured in LM Studio)
            base_url: LM Studio API base URL (default: http://localhost:1234/v1)
            **kwargs: Additional OpenAI client configuration
        """
        super().__init__(model, **kwargs)
        self.base_url = base_url
        # LM Studio uses OpenAI-compatible API
        self.client = OpenAI(
            base_url=base_url,
            api_key="lm-studio",  # LM Studio doesn't require real API key
            **kwargs
        )
        self._encoding = None

    def generate(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """Generate text using LM Studio API (OpenAI-compatible)"""
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
        """Count tokens using tiktoken (cl100k_base encoding)"""
        if self._encoding is None:
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


