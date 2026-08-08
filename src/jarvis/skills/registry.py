"""Skill registry for managing and executing skills."""

from __future__ import annotations

import time
import traceback
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol
from dataclasses import dataclass, field
from enum import Enum

from jarvis.skills.interfaces import SkillInterface, SkillResult


class SkillStatus(Enum):
    """Skill execution status."""
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class SkillExecutionResult:
    """Result of skill execution."""
    success: bool
    status: SkillStatus
    reason: str
    execution_time: float
    logs: List[str] = field(default_factory=list)
    data: Any = None


class SkillRegistry:
    """Registry for managing skills and their execution."""

    def __init__(self):
        self._skills: Dict[str, SkillInterface] = {}
        self._execution_history: List[SkillExecutionResult] = []

    def register_skill(self, name: str, skill: SkillInterface) -> bool:
        """
        Register a skill with the registry.

        Args:
            name: Unique name for the skill
            skill: Skill instance to register

        Returns:
            True if registration successful, False if skill name already exists
        """
        if name in self._skills:
            return False

        self._skills[name] = skill
        return True

    def unregister_skill(self, name: str) -> bool:
        """
        Unregister a skill from the registry.

        Args:
            name: Name of the skill to remove

        Returns:
            True if skill was removed, False if not found
        """
        if name in self._skills:
            del self._skills[name]
            return True
        return False

    def get_skill(self, name: str) -> Optional[SkillInterface]:
        """
        Get a skill by name.

        Args:
            name: Name of the skill to retrieve

        Returns:
            Skill instance if found, None otherwise
        """
        return self._skills.get(name)

    def list_skills(self) -> List[str]:
        """
        List all registered skill names.

        Returns:
            List of skill names
        """
        return list(self._skills.keys())

    def execute_skill(self, name: str, **kwargs) -> SkillExecutionResult:
        """
        Execute a skill by name.

        Args:
            name: Name of the skill to execute
            **kwargs: Arguments to pass to the skill

        Returns:
            SkillExecutionResult with execution details
        """
        start_time = time.time()

        # Get the skill
        skill = self.get_skill(name)
        if skill is None:
            return SkillExecutionResult(
                success=False,
                status=SkillStatus.FAILURE,
                reason=f"Skill '{name}' not found",
                execution_time=time.time() - start_time,
                logs=[f"Skill '{name}' not found in registry"]
            )

        # Execute the skill
        try:
            result = skill.execute(**kwargs)
            execution_time = time.time() - start_time

            # Ensure result has required fields
            if not isinstance(result, dict):
                result = {"result": result}

            # Normalize result to match our expected format
            normalized_result = SkillExecutionResult(
                success=result.get("success", False),
                status=SkillStatus.SUCCESS if result.get("success", False) else SkillStatus.FAILURE,
                reason=result.get("reason", "Skill executed"),
                execution_time=execution_time,
                logs=result.get("logs", []),
                data=result.get("data")
            )

            # Add to execution history
            self._execution_history.append(normalized_result)

            return normalized_result

        except Exception as e:
            execution_time = time.time() - start_time
            error_result = SkillExecutionResult(
                success=False,
                status=SkillStatus.FAILURE,
                reason=f"Skill execution failed: {str(e)}",
                execution_time=execution_time,
                logs=[f"Exception: {str(e)}", f"Traceback: {traceback.format_exc()}"]
            )

            self._execution_history.append(error_result)
            return error_result

    def get_execution_history(self, limit: Optional[int] = None) -> List[SkillExecutionResult]:
        """
        Get execution history.

        Args:
            limit: Maximum number of results to return (None for all)

        Returns:
            List of execution results
        """
        if limit is None:
            return self._execution_history.copy()
        return self._execution_history[-limit:]

    def clear_history(self) -> None:
        """Clear execution history."""
        self._execution_history.clear()
