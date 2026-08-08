"""Skill execution interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class SkillInterface(ABC):
    """Base interface for all skills."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the skill name."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Get the skill description."""

    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the skill and return a structured result dict."""


SkillResult = Dict[str, Any]
