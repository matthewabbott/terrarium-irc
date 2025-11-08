"""
terrarium-agent HTTP API client.

Simple client for calling the Terrarium Agent HTTP API server.
Replaces Ollama integration with terrarium-agent server.
"""

import time
import requests
from typing import List, Dict, Optional
from requests.exceptions import RequestException, Timeout, ConnectionError


class AgentClientError(Exception):
    """Base exception for agent client errors."""
    pass


class AgentClient:
    """
    Client for Terrarium Agent HTTP API.

    Provides simple interface for generating responses from the agent server.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        timeout: int = 60,
        max_retries: int = 3
    ):
        """
        Initialize agent client.

        Args:
            base_url: Agent server URL (default: http://localhost:8080)
            timeout: Request timeout in seconds (default: 60)
            max_retries: Maximum retry attempts (default: 3)
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries

    async def initialize(self):
        """Initialize client (async for compatibility with old interface)."""
        # No initialization needed for HTTP client
        pass

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 512,
        model: Optional[str] = None
    ) -> str:
        """
        Generate response with conversation history.

        Args:
            messages: Conversation history (OpenAI format)
            temperature: Sampling temperature 0.0-2.0
            max_tokens: Maximum tokens to generate
            model: Model name (auto-detected if omitted)

        Returns:
            Assistant's response text

        Raises:
            AgentClientError: Request failed
        """
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        if model:
            payload["model"] = model

        response_data = await self._request_with_retry(
            "POST",
            "/v1/chat/completions",
            json=payload
        )

        try:
            return response_data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise AgentClientError(f"Invalid response format: {e}")

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 512
    ) -> str:
        """
        Simple generation (compatibility with old Ollama interface).

        Args:
            prompt: User's message
            system_prompt: Optional system prompt
            context: Optional context (will be prepended to prompt)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Assistant's response text
        """
        # Build messages in OpenAI format
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # If context provided, include it with the prompt
        user_content = prompt
        if context:
            user_content = f"{context}\n\n{prompt}"

        messages.append({"role": "user", "content": user_content})

        # Use chat endpoint
        return await self.chat(messages, temperature, max_tokens)

    async def health_check(self) -> bool:
        """
        Check if agent server is healthy.

        Returns:
            True if healthy, False otherwise
        """
        try:
            response = requests.get(
                f"{self.base_url}/health",
                timeout=5
            )
            return response.status_code == 200
        except:
            return False

    async def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> Dict:
        """
        Make HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            **kwargs: Additional arguments for requests

        Returns:
            Response JSON data

        Raises:
            AgentClientError: Request failed
        """
        url = f"{self.base_url}{endpoint}"

        for attempt in range(self.max_retries):
            try:
                response = requests.request(
                    method,
                    url,
                    timeout=self.timeout,
                    **kwargs
                )

                if response.status_code >= 500:
                    # Server error - retry with backoff
                    if attempt < self.max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    else:
                        raise AgentClientError(
                            f"Server error: {response.text}"
                        )

                elif response.status_code >= 400:
                    # Client error - don't retry
                    raise AgentClientError(f"Request error: {response.text}")

                response.raise_for_status()
                return response.json()

            except Timeout:
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                else:
                    raise AgentClientError("Request timed out")

            except ConnectionError:
                raise AgentClientError(f"Cannot connect to {self.base_url}")

            except RequestException as e:
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                else:
                    raise AgentClientError(f"Request failed: {e}")

        raise AgentClientError("Unexpected error")
