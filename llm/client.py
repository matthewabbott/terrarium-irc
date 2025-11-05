"""LLM client abstraction supporting Ollama and vLLM."""

import os
from typing import Optional, List, Dict
import asyncio


class LLMClient:
    """Unified LLM client supporting multiple backends."""

    def __init__(
        self,
        backend: str = "ollama",
        model: str = "qwen2.5:7b",
        api_url: str = "http://localhost:11434",
        temperature: float = 0.7,
        max_tokens: int = 1000
    ):
        """
        Initialize LLM client.

        Args:
            backend: 'ollama' or 'vllm'
            model: Model name/identifier
            api_url: API endpoint URL
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
        """
        self.backend = backend.lower()
        self.model = model
        self.api_url = api_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = None

    async def initialize(self):
        """Initialize the appropriate client."""
        if self.backend == "ollama":
            try:
                import ollama
                self._client = ollama.AsyncClient(host=self.api_url)
            except ImportError:
                raise ImportError("ollama package not installed. Run: pip install ollama")
        elif self.backend == "vllm":
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    base_url=self.api_url,
                    api_key="EMPTY"  # vLLM doesn't require API key
                )
            except ImportError:
                raise ImportError("openai package not installed. Run: pip install openai")
        else:
            raise ValueError(f"Unknown backend: {self.backend}")

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

        try:
            if self.backend == "ollama":
                return await self._generate_ollama(full_prompt, system_prompt)
            elif self.backend == "vllm":
                return await self._generate_vllm(full_prompt, system_prompt)
        except Exception as e:
            return f"Error generating response: {str(e)}"

    async def _generate_ollama(self, prompt: str, system_prompt: Optional[str]) -> str:
        """Generate using Ollama."""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

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
            # Fallback to generate API if chat fails
            try:
                response = await self._client.generate(
                    model=self.model,
                    prompt=prompt,
                    system=system_prompt,
                    options={
                        "temperature": self.temperature,
                        "num_predict": self.max_tokens
                    }
                )
                return response['response']
            except Exception as e2:
                raise Exception(f"Ollama generation failed: {str(e2)}")

    async def _generate_vllm(self, prompt: str, system_prompt: Optional[str]) -> str:
        """Generate using vLLM (OpenAI-compatible API)."""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )

        return response.choices[0].message.content

    async def stream_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[str] = None
    ):
        """
        Stream generate text from the LLM.

        Args:
            prompt: User prompt/question
            system_prompt: System prompt (optional)
            context: Additional context (optional)

        Yields:
            Text chunks as they're generated
        """
        if not self._client:
            await self.initialize()

        full_prompt = prompt
        if context:
            full_prompt = f"Context:\n{context}\n\nQuestion: {prompt}"

        if self.backend == "ollama":
            async for chunk in self._stream_ollama(full_prompt, system_prompt):
                yield chunk
        elif self.backend == "vllm":
            async for chunk in self._stream_vllm(full_prompt, system_prompt):
                yield chunk

    async def _stream_ollama(self, prompt: str, system_prompt: Optional[str]):
        """Stream generation using Ollama."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            stream = await self._client.chat(
                model=self.model,
                messages=messages,
                stream=True,
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens
                }
            )
            async for chunk in stream:
                if 'message' in chunk and 'content' in chunk['message']:
                    yield chunk['message']['content']
        except Exception as e:
            yield f"Error: {str(e)}"

    async def _stream_vllm(self, prompt: str, system_prompt: Optional[str]):
        """Stream generation using vLLM."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        stream = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def check_health(self) -> bool:
        """Check if the LLM backend is healthy."""
        try:
            if not self._client:
                await self.initialize()

            if self.backend == "ollama":
                # Try to list models as health check
                await self._client.list()
                return True
            elif self.backend == "vllm":
                # Try a simple generation
                await self._generate_vllm("test", None)
                return True
        except Exception:
            return False
        return False
