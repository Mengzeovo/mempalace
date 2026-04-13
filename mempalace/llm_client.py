"""
llm_client.py — OpenAI-compatible API client for MemPalace LLM features.

Used only during `mempalace init --llm`. The mine/search pipeline never
imports this module, so the optional `openai` dependency does not affect
the core local-first workflow.

Install the optional dependency:
    pip install mempalace[llm]
"""

import json
import re
import time
from typing import Any

from .config import MempalaceConfig


class LLMConfigError(Exception):
    """Raised when LLM configuration is missing or invalid."""


class LLMCallError(Exception):
    """Raised when an LLM API call fails after all retries."""


class LLMClient:
    """Thin wrapper around an OpenAI-compatible chat completion endpoint.

    Reads configuration from MempalaceConfig.llm_config (which itself
    merges ~/.mempalace/config.json and environment variables).

    Example config.json entry::

        {
          "llm": {
            "api_key": "sk-xxx",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat"
          }
        }

    Environment variable overrides (highest priority):
        MEMPALACE_LLM_API_KEY
        MEMPALACE_LLM_BASE_URL
        MEMPALACE_LLM_MODEL
    """

    _MAX_RETRIES = 2
    _RETRY_DELAY = 2.0  # seconds between retries

    def __init__(self, config: MempalaceConfig | None = None):
        if config is None:
            config = MempalaceConfig()
        llm_cfg = config.llm_config

        self._api_key: str = llm_cfg.get("api_key", "")
        self._base_url: str = llm_cfg.get("base_url", "https://api.openai.com/v1")
        self._model: str = llm_cfg.get("model", "gpt-4o-mini")

        if not self._api_key:
            raise LLMConfigError(
                "LLM API key is not configured.\n"
                "Add it to ~/.mempalace/config.json:\n"
                '  {"llm": {"api_key": "sk-xxx", "base_url": "...", "model": "..."}}\n'
                "Or set the environment variable: MEMPALACE_LLM_API_KEY=sk-xxx"
            )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Send a chat completion request and return the assistant's text.

        Retries up to _MAX_RETRIES times on transient errors.

        Args:
            messages: List of role/content dicts, e.g.
                      [{"role": "user", "content": "Hello"}]

        Returns:
            The assistant message content as a string.

        Raises:
            LLMCallError: If all retries fail.
        """
        try:
            import openai  # noqa: PLC0415
        except ImportError:
            raise ImportError(
                "The 'openai' package is required for --llm mode.\n"
                "Install it with:  pip install mempalace[llm]"
            ) from None

        client = openai.OpenAI(api_key=self._api_key, base_url=self._base_url)

        last_exc: Exception | None = None
        for attempt in range(1, self._MAX_RETRIES + 2):  # 1, 2, 3
            try:
                response = client.chat.completions.create(
                    model=self._model,
                    messages=messages,  # type: ignore[arg-type]
                    timeout=60,
                )
                return response.choices[0].message.content or ""
            except Exception as exc:
                last_exc = exc
                if attempt <= self._MAX_RETRIES:
                    print(
                        f"  [LLM] Attempt {attempt} failed: {exc}. "
                        f"Retrying in {self._RETRY_DELAY}s..."
                    )
                    time.sleep(self._RETRY_DELAY)

        raise LLMCallError(
            f"LLM call failed after {self._MAX_RETRIES + 1} attempts. "
            f"Last error: {last_exc}\n"
            "Tip: run `mempalace init <dir>` (without --llm) to use local detection."
        ) from last_exc

    def parse_json_response(self, text: str) -> dict[str, Any]:
        """Parse a JSON object from an LLM response string.

        Two-stage fallback:
          1. Try ``json.loads(text.strip())`` directly.
          2. Use regex to extract the first ``{...}`` block and parse it.

        Args:
            text: Raw string returned by the LLM.

        Returns:
            Parsed dict.

        Raises:
            ValueError: If no valid JSON object could be extracted.
        """
        text = text.strip()

        # Stage 1: direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Stage 2: extract first {...} block (handles markdown code fences etc.)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # Both stages failed
        preview = text[:200] + ("..." if len(text) > 200 else "")
        raise ValueError(
            f"Could not extract valid JSON from LLM response.\n"
            f"Response preview: {preview!r}"
        )
