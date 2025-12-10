"""
DeepSeek LLM Provider

Implementation for DeepSeek models (DeepSeek-R1, DeepSeek-V2, DeepSeek-Coder, etc.)
Supports both DeepSeek API (OpenAI-compatible) and HuggingFace.
"""

import tiktoken
from typing import Optional

from openai import OpenAI

from retrieval.services.llm_providers.base import LLMProvider


class DeepSeekProvider(LLMProvider):
    """DeepSeek provider implementation using OpenAI-compatible API"""

    def __init__(self, model: str, api_key: str, base_url: Optional[str] = None, **kwargs):
        """
        Initialize DeepSeek provider.
        
        Args:
            model: Model name (e.g., "deepseek-chat", "deepseek-coder", "deepseek-r1")
            api_key: DeepSeek API key
            base_url: Optional custom base URL (defaults to DeepSeek API endpoint)
            **kwargs: Additional OpenAI client configuration
        """
        super().__init__(model, **kwargs)
        
        # DeepSeek API endpoint (OpenAI-compatible)
        if base_url is None:
            base_url = "https://api.deepseek.com"
        
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
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
        """Generate text using DeepSeek API"""
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
            # DeepSeek uses similar tokenization to GPT models
            # Try to get encoding for the model, fallback to cl100k_base
            try:
                self._encoding = tiktoken.encoding_for_model(self.model)
            except KeyError:
                # DeepSeek models typically use cl100k_base encoding
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

