"""LLM client for Ollama."""

import asyncio
from typing import Optional


class LLMClient:
    """Ollama LLM client."""

    def __init__(
        self,
        model: str = "qwen2.5:7b",
        api_url: str = "http://localhost:11434",
        temperature: float = 0.7,
        max_tokens: int = 1000
    ):
        """
        Initialize LLM client.

        Args:
            model: Model name (e.g., 'qwen2.5:7b')
            api_url: Ollama API endpoint
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
        """
        self.model = model
        self.api_url = api_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = None

    async def initialize(self):
        """Initialize Ollama client."""
        try:
            import ollama
            self._client = ollama.AsyncClient(host=self.api_url)
        except ImportError:
            raise ImportError("ollama package not installed. Run: pip install ollama")

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[str] = None
    ) -> str:
        """
        Generate text from the LLM.

        Args:
            prompt: User prompt/question
            system_prompt: System prompt (optional)
            context: Additional context (optional)

        Returns:
            Generated text
        """
        if not self._client:
            await self.initialize()

        # Build the full prompt
        full_prompt = prompt
        if context:
            full_prompt = f"Context:\n{context}\n\nQuestion: {prompt}"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": full_prompt})

        try:
            response = await self._client.chat(
                model=self.model,
                messages=messages,
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens
                }
            )
            return response['message']['content']
        except Exception as e:
            return f"Error generating response: {str(e)}"

    async def check_health(self) -> bool:
        """Check if Ollama is healthy."""
        try:
            if not self._client:
                await self.initialize()
            await self._client.list()
            return True
        except Exception:
            return False
