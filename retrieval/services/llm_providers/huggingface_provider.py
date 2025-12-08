"""
HuggingFace LLM Provider

Implementation for local HuggingFace models via transformers library.
"""

from typing import Optional

try:
    from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
    import torch
    HUGGINGFACE_AVAILABLE = True
except ImportError:
    HUGGINGFACE_AVAILABLE = False

from retrieval.services.llm_providers.base import LLMProvider


class HuggingFaceProvider(LLMProvider):
    """HuggingFace provider implementation for local models"""

    def __init__(self, model: str, device: str = "auto", **kwargs):
        """
        Initialize HuggingFace provider.
        
        Args:
            model: HuggingFace model ID (e.g., "meta-llama/Llama-2-7b-chat-hf")
            device: Device to run on ("auto", "cpu", "cuda")
            **kwargs: Additional model configuration
        """
        if not HUGGINGFACE_AVAILABLE:
            raise ImportError(
                "transformers and torch are required for HuggingFace provider. "
                "Install with: pip install transformers torch"
            )
        
        super().__init__(model, **kwargs)
        
        # Determine device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        
        # Load tokenizer and model
        self.tokenizer = AutoTokenizer.from_pretrained(model, **kwargs)
        self.model = AutoModelForCausalLM.from_pretrained(
            model,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            device_map=device if device == "cuda" else None,
            **kwargs
        )
        
        # Create pipeline for text generation
        self.pipeline = pipeline(
            "text-generation",
            model=self.model,
            tokenizer=self.tokenizer,
            device=0 if device == "cuda" else -1,
        )

    def generate(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """Generate text using HuggingFace model"""
        # Combine system message and prompt
        full_prompt = prompt
        if system_message:
            full_prompt = f"{system_message}\n\n{prompt}"
        
        # Prepare generation parameters
        generation_kwargs = {
            "temperature": temperature,
            "do_sample": temperature > 0,
            **kwargs
        }
        
        if max_tokens:
            generation_kwargs["max_new_tokens"] = max_tokens
        
        # Generate
        outputs = self.pipeline(
            full_prompt,
            return_full_text=False,
            **generation_kwargs
        )
        
        # Extract generated text
        if isinstance(outputs, list) and len(outputs) > 0:
            return outputs[0].get("generated_text", "")
        return ""

    def count_tokens(self, text: str) -> int:
        """Count tokens using the model's tokenizer"""
        tokens = self.tokenizer.encode(text, add_special_tokens=False)
        return len(tokens)


