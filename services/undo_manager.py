"""Snapshot-based undo history for the Track Editor.

The editor has many heterogeneous QGraphicsItem subclasses.  A compact project
snapshot is therefore a reliable common undo format: every item already knows
how to serialize itself, and the registry already knows how to reconstruct it.
"""

from __future__ import annotations

from copy import deepcopy


class SnapshotUndoManager:
    """Store full project snapshots for user-visible editing operations."""

    def __init__(self, max_steps: int = 60):
        self.max_steps = max(1, int(max_steps))
        self._undo_stack: list[tuple[str, dict]] = []
        self._pending: tuple[str, dict] | None = None

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def next_undo_label(self) -> str:
        if not self._undo_stack:
            return ""
        return self._undo_stack[-1][0]

    def clear(self):
        self._undo_stack.clear()
        self._pending = None

    def begin(self, label: str, before_data: dict):
        """Begin one edit transaction.

        Nested begin calls are ignored so a high-level action such as Duplicate
        can call lower-level helpers without producing multiple undo entries.
        """
        if self._pending is not None:
            return
        self._pending = (str(label or "Edit"), deepcopy(before_data))

    def commit(self, after_data: dict) -> bool:
        """Commit the pending transaction only if project data changed."""
        if self._pending is None:
            return False

        label, before_data = self._pending
        self._pending = None

        if before_data == after_data:
            return False

        self._undo_stack.append((label, before_data))
        if len(self._undo_stack) > self.max_steps:
            del self._undo_stack[0 : len(self._undo_stack) - self.max_steps]
        return True

    def cancel(self):
        self._pending = None

    def pop_undo(self) -> tuple[str, dict] | None:
        """Return the previous project snapshot, newest first."""
        self._pending = None
        if not self._undo_stack:
            return None
        label, snapshot = self._undo_stack.pop()
        return label, deepcopy(snapshot)
