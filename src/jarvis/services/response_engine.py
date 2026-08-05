"""DynamicResponseEngine for JARVIS. Determines expected response complexity and length rules based on intent/input query."""

from __future__ import annotations
import re
from typing import Dict, Any

class DynamicResponseEngine:
    """Classifies user queries to dictate the formatting and length constraints of the output."""

    def __init__(self) -> None:
        pass

    def estimate_complexity(self, text: str) -> Dict[str, Any]:
        """Analyzes text and returns instructions/constraints for response length."""
        cleaned = text.lower().strip()

        # 1. Greetings
        if any(g in cleaned for g in ["hello", "hi", "hey", "greetings", "good morning", "good afternoon"]):
            return {
                "profile": "greeting",
                "instruction": "Greeting profile: Respond in exactly one sentence. Keep it extremely short and polite.",
                "max_sentences": 1,
            }

        # 2. Programming / Coding requests
        if any(c in cleaned for c in ["write code", "code for", "build a", "implement", "function to", "write a script", "coding", "develop"]):
            return {
                "profile": "programming",
                "instruction": "Coding profile: Provide only a brief summary of the action, then state that OpenCode will perform the implementation.",
                "max_sentences": 2,
            }

        # 3. Explicit detail requests
        if any(d in cleaned for d in ["explain in detail", "detailed explanation", "describe in detail", "in-depth", "tell me more about"]):
            return {
                "profile": "detailed",
                "instruction": "Detailed profile: You may provide a long, detailed, and structured explanation since the user explicitly requested it.",
                "max_sentences": 20,
            }

        # 4. Definitions
        if any(def_word in cleaned for def_word in ["what is", "define", "definition of", "what does"]):
            return {
                "profile": "definition",
                "instruction": "Definition profile: Keep the definition concise, between 2 to 4 sentences. Explain the core concept directly.",
                "max_sentences": 4,
            }

        # 5. Simple factual / general questions
        if any(q in cleaned for q in ["how many", "who is", "where is", "when did", "is it"]):
            return {
                "profile": "factual",
                "instruction": "Simple factual profile: Answer the question directly and concisely in exactly 2 sentences.",
                "max_sentences": 2,
            }

        # Default fallback
        return {
            "profile": "default",
            "instruction": "Conversation profile: Keep your response short, precise, and natural (1-3 sentences).",
            "max_sentences": 3,
        }
