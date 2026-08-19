"""
Research assistant: sends the structured AIContext + user question to the
Anthropic API. Reads AI_API_KEY from the environment; never hardcoded.

If AI_API_KEY is not set, `ask()` raises AIUnavailableError rather than
returning a canned or fabricated answer — the API layer turns that into a
clear "AI assistant not configured" response to the client.
"""
from __future__ import annotations

import os

from backend.ai.context import SYSTEM_PROMPT, AIContext, render_context_block


class AIUnavailableError(RuntimeError):
    pass


class ResearchAssistant:
    def __init__(self, model: str = "claude-sonnet-4-6") -> None:
        self.api_key = os.environ.get("AI_API_KEY", "").strip()
        self.model = model

    def ask(self, context: AIContext, question: str) -> str:
        if not self.api_key:
            raise AIUnavailableError(
                "AI_API_KEY is not set. Configure it in your .env file to enable "
                "the AI research assistant."
            )
        try:
            import anthropic
        except ImportError as exc:
            raise AIUnavailableError(
                "The 'anthropic' package is not installed. Run: pip install anthropic"
            ) from exc

        client = anthropic.Anthropic(api_key=self.api_key)
        context_block = render_context_block(context)

        response = client.messages.create(
            model=self.model,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"CONTEXT:\n{context_block}\n\nQUESTION:\n{question}",
                }
            ],
        )
        return "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
