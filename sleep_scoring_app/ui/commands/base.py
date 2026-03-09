"""Command pattern base classes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque


class Command(ABC):
    """Abstract command with execute and undo."""

    @abstractmethod
    def execute(self) -> None:
        """Execute the command."""
        ...

    @abstractmethod
    def undo(self) -> None:
        """Undo the command."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description for UI."""
        return self.__class__.__name__


class CommandHistory:
    """Manages command history for undo/redo."""

    def __init__(self, max_history: int = 50) -> None:
        self._undo_stack: deque[Command] = deque(maxlen=max_history)
        self._redo_stack: deque[Command] = deque(maxlen=max_history)

    def execute(self, command: Command) -> None:
        """Execute command and add to history."""
        command.execute()
        self._undo_stack.append(command)
        self._redo_stack.clear()  # Clear redo on new action

    def undo(self) -> bool:
        """Undo last command. Returns True if undone."""
        if not self._undo_stack:
            return False
        command = self._undo_stack.pop()
        command.undo()
        self._redo_stack.append(command)
        return True

    def redo(self) -> bool:
        """Redo last undone command. Returns True if redone."""
        if not self._redo_stack:
            return False
        command = self._redo_stack.pop()
        command.execute()
        self._undo_stack.append(command)
        return True

    def can_undo(self) -> bool:
        """Check if undo is possible."""
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        """Check if redo is possible."""
        return len(self._redo_stack) > 0

    def clear(self) -> None:
        """Clear all history."""
        self._undo_stack.clear()
        self._redo_stack.clear()
