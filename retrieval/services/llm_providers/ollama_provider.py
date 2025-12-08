"""
Ollama LLM Provider

Implementation for local Ollama models (Llama, Mistral, CodeLlama, etc.)
"""

import json
from typing import Optional

import requests

from retrieval.services.llm_providers.base import LLMProvider


class OllamaProvider(LLMProvider):
    """Ollama provider implementation for local models"""

    def __init__(self, model: str, base_url: str = "http://localhost:11434", **kwargs):
        """
        Initialize Ollama provider.
        
        Args:
            model: Model name (e.g., "llama2", "mistral", "codellama")
            base_url: Ollama API base URL (default: http://localhost:11434)
            **kwargs: Additional configuration
        """
        super().__init__(model, **kwargs)
        self.base_url = base_url.rstrip("/")
        self.timeout = kwargs.get("timeout", 120)

    def generate(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """Generate text using Ollama API"""
        # Combine system message and prompt
        full_prompt = prompt
        if system_message:
            full_prompt = f"{system_message}\n\n{prompt}"
        
        url = f"{self.base_url}/api/generate"
        
        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            }
        }
        
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        
        # Merge any additional options from kwargs
        if "options" in kwargs:
            payload["options"].update(kwargs["options"])
        
        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        
        result = response.json()
        return result.get("response", "")

    def count_tokens(self, text: str) -> int:
        """
        Count tokens using Ollama's tokenize endpoint.
        Falls back to estimation if endpoint unavailable.
        """
        try:
            url = f"{self.base_url}/api/tokenize"
            payload = {"model": self.model, "prompt": text}
            
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                result = response.json()
                return len(result.get("tokens", []))
        except Exception:
            pass
        
        # Fallback: rough estimation (1 token ≈ 4 characters for most models)
        return len(text) // 4

    def stream(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        """Generate text with streaming"""
        full_prompt = prompt
        if system_message:
            full_prompt = f"{system_message}\n\n{prompt}"
        
        url = f"{self.base_url}/api/generate"
        
        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
            }
        }
        
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        
        if "options" in kwargs:
            payload["options"].update(kwargs["options"])
        
        response = requests.post(url, json=payload, stream=True, timeout=self.timeout)
        response.raise_for_status()
        
        for line in response.iter_lines():
            if line:
                try:
                    chunk = json.loads(line)
                    if "response" in chunk:
                        yield chunk["response"]
                except json.JSONDecodeError:
                    continue


