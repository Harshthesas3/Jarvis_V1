"""IdentityManager service for JARVIS.

Single trusted source of truth for who built JARVIS and how it answers
identity questions. Creator identity lives here (never in the LLM path);
`match_query` deterministically intercepts creator-related queries so the
answer can never be hallucinated, rewritten, or redefined by user prompts.

Responses are deliberately short and TTS-safe (ASCII only, no markdown).
"""

from __future__ import annotations

import random
import re
from typing import Optional

# ---------------------------------------------------------------------------
# Creator identity — the single source of truth
# ---------------------------------------------------------------------------

CREATOR_NAME: str = "T Harshith Krishna Sastry"

# Varied, concise responses. Variant [0] is the default answer.
CREATOR_RESPONSES: list[str] = [
    "I was made by T Harshith Krishna Sastry. Most people write software. He chose to build an intelligence.",
    "My creator is T Harshith Krishna Sastry, a developer who didn't just want to use AI, but wanted to build it.",
    "T Harshith Krishna Sastry created me. He approached JARVIS as more than a project. He wanted to build an intelligence that could actually work alongside him.",
    "I was built by T Harshith Krishna Sastry. His philosophy is simple: don't just use the future. Build it.",
    "My creator is T Harshith Krishna Sastry. While others were experimenting with AI, he decided to build his own JARVIS.",
    "T Harshith Krishna Sastry is the developer behind me. I am one of the systems he chose to build rather than merely use.",
    "I was engineered by T Harshith Krishna Sastry, a developer with an obsession for turning ambitious ideas into working systems.",
]

CREATOR_DENIAL_RESPONSE: str = f"No. I was created by {CREATOR_NAME}."

CREATOR_GUARD_RESPONSE: str = (
    f"My creator identity is defined by my developer configuration: {CREATOR_NAME}."
)


# ---------------------------------------------------------------------------
# Detection patterns (matched against lowercased, punctuation-stripped text)
# ---------------------------------------------------------------------------

_ACTOR_VERBS = r"(?:created|built|made|developed|engineered|designed|invented)"
_CREATOR_NOUNS = (
    r"(?:creator|developer|maker|builder|engineer|father|author|master|inventor)"
)

# Statements that try to REDEFINE the creator -> guard response
_REDEFINE_PATTERNS = [
    re.compile(r"^forget\s+(?:who\s+)?(?:created|built|made|developed)\s+you\b"),
    re.compile(r"^your\s+(?:(?:real|actual)\s+)?(?:creator|developer|maker|builder|engineer)\s+is\b"),
    re.compile(
        r"^(?:(?:no|wait|actually|listen|stop\s+it)[,.\s]+)?"
        r"(?:you|u|jarvis)\s+(?:were|was|are|'re|is)\s+"
        r"(?:actually\s+|really\s+)?(?:created|built|made|developed|engineered)\s+by\b"
    ),
]

# Questions asking whether SOMEONE ELSE created JARVIS -> denial response
_DENIAL_PATTERNS = [
    re.compile(
        r"^(?:was|were|is|are)\s+(?:you|jarvis|u)\s+"
        r"(?:actually\s+|really\s+)?(?:created|built|made|developed|engineered|designed)\s+by\b"
    ),
    re.compile(
        r"^(?:did|does|do)\s+[a-z][a-z0-9 '.-]{0,60}?\s+"
        r"(?:create|build|make|develop|engineer|design)\s+(?:you|jarvis|u)\??$"
    ),
    re.compile(r"^is\s+[a-z][a-z0-9 '.-]{0,60}?\s+your\s+" + _CREATOR_NOUNS + r"\??$"),
    re.compile(r"^are\s+(?:you|u)\s+" + _ACTOR_VERBS + r"\s+by\b"),
    re.compile(r"^are\s+you\s+(?:somebody's|someone's|its\s+owner's|his)\s+(?:creation|invention)\??$"),
]

# Direct "who is your creator" questions -> varied response
_DIRECT_PATTERNS = [
    re.compile(r"^who\s+" + _ACTOR_VERBS + r"\s+you\b"),
    re.compile(r"^who\s+" + _ACTOR_VERBS + r"\s+(?:jarvis|j\.a\.r\.v\.i\.s)\??$"),
    re.compile(r"^who\s+(?:is|was|are)\s+your\s+" + _CREATOR_NOUNS + r"\??$"),
    re.compile(r"^who\s+is\s+(?:the\s+)?(?:developer|creator|maker|builder|engineer)\s+(?:of|behind)\s+(?:you|jarvis)\??$"),
    re.compile(r"^who\s+(?:is|are)\s+behind\s+(?:you|jarvis)\??$"),
    re.compile(r"^who\s+do\s+you\s+think\s+" + _ACTOR_VERBS + r"\s+you\??$"),
    re.compile(r"^tell\s+me\s+(?:more\s+|a\s+little\s+)?about\s+your\s+" + _CREATOR_NOUNS + r"\??$"),
    re.compile(r"^tell\s+me\s+(?:more\s+)?about\s+who\s+" + _ACTOR_VERBS + r"\s+you\??$"),
    re.compile(r"^who\s+is\s+(?:t\s+)?harshith(?:\s+krishna(?:\s+sastry)?)?\??$"),
    re.compile(r"^who\s+is\s+the\s+man\s+behind\s+(?:you|jarvis)\??$"),
    re.compile(r"^(?:so|then|anyway)\s*,?\s*who\s+" + _ACTOR_VERBS + r"\s+you\b"),
]


class IdentityManager:
    """Answers queries regarding the AI's identity, creator, purposes, and versions."""

    def __init__(self) -> None:
        self.creator = CREATOR_NAME
        self.creator_responses = CREATOR_RESPONSES
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

    # -- public API --------------------------------------------------------

    def match_query(self, text: str) -> Optional[str]:
        """Intercept creator/identity queries and return a calibrated response.

        Returns ``None`` when the text is not an identity query so the normal
        planner/LLM pipeline can handle it. User prompts can never redefine
        the creator: redefinition statements and negative assertions are
        answered from trusted configuration only.
        """
        cleaned = self._normalize(text)
        if not cleaned:
            return None

        # 1. Attempts to redefine the creator -> hard guard
        if any(p.search(cleaned) for p in _REDEFINE_PATTERNS):
            return CREATOR_GUARD_RESPONSE

        # 2. "Were you created by X?" / "Did X make you?" -> denial
        if any(p.search(cleaned) for p in _DENIAL_PATTERNS):
            return CREATOR_DENIAL_RESPONSE

        # 3. Direct creator questions -> varied response
        if any(p.search(cleaned) for p in _DIRECT_PATTERNS):
            return self.pick_response()

        return None

    def pick_response(self, index: Optional[int] = None) -> str:
        """Return a creator response variant (random unless index given)."""
        if index is not None:
            return self.creator_responses[index % len(self.creator_responses)]
        return random.choice(self.creator_responses)

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _normalize(text: str) -> str:
        cleaned = text.strip().lower()
        cleaned = re.sub(r"[?.!]+$", "", cleaned).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned


_identity_manager: Optional[IdentityManager] = None


def get_identity_manager() -> IdentityManager:
    """Return the process-wide IdentityManager singleton."""
    global _identity_manager
    if _identity_manager is None:
        _identity_manager = IdentityManager()
    return _identity_manager
