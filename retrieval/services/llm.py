"""
LLM Service

Factory service for creating and managing LLM providers.
Supports plug-and-play provider switching via configuration.
"""

from typing import Optional

from retrieval.config import settings
from retrieval.services.llm_providers.base import LLMProvider
from retrieval.services.llm_providers.openai_provider import OpenAIProvider
from retrieval.services.llm_providers.ollama_provider import OllamaProvider
from retrieval.services.llm_providers.huggingface_provider import HuggingFaceProvider
from retrieval.services.llm_providers.lmstudio_provider import LMStudioProvider

try:
    from retrieval.services.llm_providers.anthropic_provider import AnthropicProvider
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class LLMService:
    """Service for LLM operations with plug-and-play provider support"""

    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize LLM service.
        
        Args:
            provider: LLM provider name (defaults to config)
            model: Model name (defaults to config)
        """
        # Use provider from argument if provided and not empty, otherwise use config default
        if provider and provider.strip():
            self.provider_name = provider.strip()
        else:
            self.provider_name = settings.LLM_PROVIDER
        
        # Use model from argument if provided and not empty, otherwise use config default
        if model and model.strip():
            self.model = model.strip()
        else:
            self.model = settings.LLM_MODEL
            
        self.llm_provider = self._create_provider()

    def _create_provider(self) -> LLMProvider:
        """
        Create LLM provider instance based on configuration.
        
        Returns:
            LLMProvider instance
            
        Raises:
            ValueError: If provider is not supported or misconfigured
        """
        # Validate provider name
        if not self.provider_name or not isinstance(self.provider_name, str):
            raise ValueError(
                f"Invalid provider name: {repr(self.provider_name)}. "
                f"Expected a string, got {type(self.provider_name).__name__}"
            )
        
        provider = self.provider_name.lower().strip()

        if provider == "openai":
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY must be set for OpenAI provider")
            return OpenAIProvider(
                model=self.model,
                api_key=settings.OPENAI_API_KEY,
            )

        elif provider == "ollama":
            base_url = settings.LLM_BASE_URL or "http://localhost:11434"
            return OllamaProvider(
                model=self.model,
                base_url=base_url,
            )

        elif provider == "huggingface":
            device = getattr(settings, "LLM_DEVICE", "auto")
            return HuggingFaceProvider(
                model=self.model,
                device=device,
            )

        elif provider == "lmstudio":
            base_url = settings.LLM_BASE_URL or "http://localhost:1234/v1"
            return LMStudioProvider(
                model=self.model,
                base_url=base_url,
            )

        elif provider == "anthropic":
            if not ANTHROPIC_AVAILABLE:
                raise ValueError(
                    "Anthropic provider not available. Install with: pip install anthropic"
                )
            if not settings.ANTHROPIC_API_KEY:
                raise ValueError("ANTHROPIC_API_KEY must be set for Anthropic provider")
            return AnthropicProvider(
                model=self.model,
                api_key=settings.ANTHROPIC_API_KEY,
            )

        else:
            raise ValueError(
                f"Unsupported LLM provider: {provider}. "
                "Supported providers: openai, ollama, huggingface, lmstudio, anthropic"
            )

    def generate(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        Generate text using the configured LLM provider.
        
        Args:
            prompt: User prompt/question
            system_message: Optional system message
            temperature: Sampling temperature (defaults to config)
            max_tokens: Maximum tokens (defaults to config)
            **kwargs: Provider-specific parameters
            
        Returns:
            Generated text response
        """
        if temperature is None:
            temperature = settings.LLM_TEMPERATURE
        if max_tokens is None:
            max_tokens = settings.LLM_MAX_TOKENS

        return self.llm_provider.generate(
            prompt=prompt,
            system_message=system_message,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Number of tokens
        """
        return self.llm_provider.count_tokens(text)

    def stream(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        """
        Generate text with streaming.
        
        Args:
            prompt: User prompt/question
            system_message: Optional system message
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            **kwargs: Provider-specific parameters
            
        Yields:
            Text chunks as they are generated
        """
        if temperature is None:
            temperature = settings.LLM_TEMPERATURE
        if max_tokens is None:
            max_tokens = settings.LLM_MAX_TOKENS

        yield from self.llm_provider.stream(
            prompt=prompt,
            system_message=system_message,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )


