"""A small async client for the Ollama chat API, plus lenient JSON parsing of model replies."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """The LLM could not be reached or did not return anything usable."""


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        num_ctx: int = 8192,
        transport: Optional[httpx.AsyncBaseTransport] = None,  # e.g. httpx.MockTransport in tests
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx
        self._transport = transport

    async def chat_json(self, system: str, user: str, *, temperature: float, timeout: float) -> Any:
        """Run one chat turn in JSON mode and return the parsed reply (``None`` if unparseable)."""
        reply = await self._post(
            "/api/chat",
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "format": "json",
                # Keep num_ctx the same for every call: changing it makes Ollama reload the model.
                "options": {"temperature": temperature, "num_ctx": self.num_ctx},
            },
            timeout,
        )
        content = (reply.get("message") or {}).get("content", "")
        data = parse_json(content)
        if data is None:
            log.warning("The LLM reply is not valid JSON: %.200r", content)
        return data

    async def unload(self) -> None:
        """Ask Ollama to free the model's memory right away. Failures are logged, not raised."""
        try:
            await self._post("/api/generate", {"model": self.model, "keep_alive": 0}, 30.0)
        except LLMError as exc:
            log.warning("Could not unload %s: %s", self.model, exc)
        else:
            log.info("Unloaded %s from Ollama", self.model)

    async def _post(self, path: str, payload: dict, timeout: float) -> dict:
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
                response = await client.post(self.base_url + path, json=payload)
        except httpx.ConnectError as exc:
            raise LLMError(
                f"Cannot reach Ollama at {self.base_url}. Is `ollama serve` running?"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMError(f"Ollama did not answer within {timeout:.0f} s.") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Request to Ollama failed: {exc}") from exc
        if response.status_code != 200:
            raise LLMError(f"Ollama returned HTTP {response.status_code}: {_error_text(response)}")
        try:
            return response.json()
        except ValueError as exc:
            raise LLMError("Ollama returned a response that is not JSON.") from exc


def _error_text(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text
    if isinstance(data, dict) and data.get("error"):
        return str(data["error"])
    return response.text


def parse_json(text: str) -> Any:
    """Parse JSON from an LLM reply, tolerating code fences and chatter around the object.

    Returns ``None`` when nothing parseable is found.
    """
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None
