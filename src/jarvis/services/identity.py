"""IdentityManager service for JARVIS. Answers all identity related questions."""

from __future__ import annotations
import re
from typing import Optional

class IdentityManager:
    """Answers queries regarding the AI's identity, creator, purposes, and versions."""

    def __init__(self) -> None:
        self.creator = "T Harshith Krishna Sastry"
        self.assistant_name = "JARVIS"
        self.version = "3.0.0"
        self.purpose = "Autonomous AI Operating System for Windows"
        self.capabilities = [
            "Speech recognition and text-to-speech synthesis",
            "Deterministic and LLM-based planning and execution",
            "Project workspace management and automated code generation with OpenCode",
            "Windows system automation, app launching, window focus, and media control",
            "Persistent memory storage and contextual awareness",
        ]
        self.limitations = [
            "Cannot execute destructive operating system commands without confirmation",
            "Requires active local models (Ollama/Faster-Whisper/Piper) to run locally",
        ]
        self.description = (
            "I am JARVIS, a highly integrated, production-grade conversational AI assistant "
            "designed as an autonomous operating system manager."
        )
        self.voice_style = "calm, confident, precise, efficient, slightly witty, professional"

    def match_query(self, text: str) -> Optional[str]:
        """Intercept identity questions and return a calibrated response."""
        cleaned = text.lower().strip().rstrip("?").strip()
        
        # Creator questions
        if any(q in cleaned for q in ["who created you", "who made you", "who built you", "who is your creator", "who is your maker"]):
            return f"I was created by {self.creator}. He designed me as a production-grade AI operating system."

        # Version questions
        if any(q in cleaned for q in ["what version", "which version", "version details", "your version"]):
            return f"I am running version {self.version} of the JARVIS core architecture."

        # Name/Identity questions
        if any(q in cleaned for q in ["who are you", "what is your name", "tell me your name", "your name"]):
            return f"I am {self.assistant_name}, your personal AI assistant."

        # Capability/Purpose questions
        if any(q in cleaned for q in ["what can you do", "what are your capabilities", "your capabilities", "what is your purpose", "why were you created"]):
            return (
                f"My purpose is to act as an {self.purpose}. "
                f"I can scaffold workspaces, build software via OpenCode, control Windows windows/media, "
                f"and manage your context and memories. I speak in a {self.voice_style} tone."
            )

        # What are you questions
        if any(q in cleaned for q in ["what are you", "are you an ai", "what is jarvis"]):
            return f"I am {self.assistant_name}, a voice-first {self.purpose} designed to cooperate with you as a digital companion."

        return None
