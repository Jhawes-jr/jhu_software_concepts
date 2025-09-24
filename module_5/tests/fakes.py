"""Shared fake objects used across test modules."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Iterator, Sequence


class FakeDBConnection:
    """In-memory DB connection that records inserted applicant rows."""

    def __init__(self) -> None:
        """Initialise the in-memory row store."""
        self.rows: list[dict[str, Any]] = []
        self.seen_urls: set[str] = set()

    def __enter__(self) -> "FakeDBConnection":
        """Return ``self`` for context manager usage."""
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """Support context manager protocol without special cleanup."""
        return None

    def cursor(self) -> "FakeCursor":
        """Provide a new cursor bound to this connection."""
        return FakeCursor(self)


class FakeCursor:
    """Cursor companion for :class:`FakeDBConnection`."""

    def __init__(self, conn: FakeDBConnection) -> None:
        """Store the parent connection reference."""
        self.conn = conn

    def __enter__(self) -> "FakeCursor":
        """Return ``self`` for context manager usage."""
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """Support context manager protocol without special cleanup."""
        return None

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        """Record inserts while ignoring other statements."""
        params = params or {}
        if "INSERT INTO applicants" in sql:
            url = params.get("url")
            if url and url not in self.conn.seen_urls:
                self.conn.seen_urls.add(url)
                self.conn.rows.append(params.copy())

    def fetchone(self) -> Any:
        """Return ``None`` as no query output exists."""
        return None

    def fetchall(self) -> list[Any]:
        """Return an empty list for query result requests."""
        return []


class FakeProcess:
    """Simplified stand-in for :class:."""

    pid_counter = 1000

    def __init__(self, cmd: list[str], spec: dict[str, Any], calls: list[list[str]]) -> None:
        """Record the invocation and configure the fake process."""
        self._cmd = cmd
        self._spec = spec
        calls.append(cmd)
        FakeProcess.pid_counter += 1
        self.pid = FakeProcess.pid_counter
        self.returncode = spec.get("returncode", 0)

    def __enter__(self) -> "FakeProcess":
        """Return ``self`` for context manager usage."""
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """Support context manager protocol without special cleanup."""
        return None

    def communicate(self) -> tuple[str, str]:
        """Return captured stdout/stderr for the fake process."""
        stdout = self._spec.get("stdout", "")
        stderr = self._spec.get("stderr", "")
        callback: Callable[[], tuple[str, str] | str | None] | None = self._spec.get("callback")
        if callback:
            result = callback()
            if isinstance(result, tuple):
                stdout, stderr = result
            elif isinstance(result, str):
                stdout = result
        return stdout, stderr


class QueryCursor:
    """Cursor that yields scripted query results sequentially."""

    def __init__(self, responses: Sequence[Any]) -> None:
        """Store scripted responses for sequential fetches."""
        self._responses = list(responses)
        self._index = 0

    def __enter__(self) -> "QueryCursor":
        """Return ``self`` for context manager usage."""
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """Support context manager protocol without special cleanup."""
        return None

    def execute(self, sql: str, params: Any | None = None) -> None:
        """Ignore execution; responses are predefined."""
        del sql, params

    def _next(self) -> Any:
        if self._index >= len(self._responses):
            raise AssertionError("No more scripted responses available")
        value = self._responses[self._index]
        self._index += 1
        return value

    def fetchone(self) -> Any:
        """Return the next scripted response."""
        return self._next()

    def fetchall(self) -> list[Any]:
        """Return the next scripted response as a list."""
        return list(self._next())


class QueryConnection:
    """Connection that provides :class: instances."""

    def __init__(self, responses: Sequence[Any]) -> None:
        """Store responses for subsequent cursors."""
        self._responses = responses

    def __enter__(self) -> "QueryConnection":
        """Return ``self`` for context manager usage."""
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """Support context manager protocol without special cleanup."""
        return None

    def cursor(self) -> QueryCursor:
        """Create a cursor backed by the stored responses."""
        return QueryCursor(self._responses)


class ScriptCursor:
    """Cursor that returns scripted responses for report tests."""

    def __init__(self, responses: Iterator[Any]) -> None:
        self._responses = responses
        self._current: Any | None = None

    def __enter__(self) -> "ScriptCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: Any | None = None) -> None:
        """Advance to the next scripted response when ``execute`` is invoked."""
        del sql, params
        try:
            self._current = next(self._responses)
        except StopIteration as exc:
            raise AssertionError("No scripted response available for execute call") from exc

    def fetchone(self) -> Any:
        """Return the response produced by the last ``execute`` call."""
        if self._current is None:
            raise AssertionError("fetchone called without prior execute")
        value = self._current
        self._current = None
        return value

    def fetchall(self) -> list[Any]:
        """Return the last response as a list."""
        if self._current is None:
            raise AssertionError("fetchall called without prior execute")
        value = self._current
        self._current = None
        return list(value)


class ScriptConnection:
    """Connection that returns :class:`ScriptCursor` objects."""

    def __init__(self, responses: Iterable[Any]) -> None:
        """Store iterable responses for scripted execution."""
        self._responses = iter(responses)

    def __enter__(self) -> "ScriptConnection":
        """Return ``self`` for context manager usage."""
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """Support context manager protocol without special cleanup."""
        return None

    def cursor(self) -> ScriptCursor:
        """Create a script cursor from the stored responses."""
        return ScriptCursor(self._responses)


class RecordingCursor:
    """Cursor used for verifying insert payloads in loader tests."""

    def __init__(self) -> None:
        """Initialise the list used to capture payloads."""
        self.rows: list[dict[str, Any]] = []

    def __enter__(self) -> "RecordingCursor":
        """Return ``self`` for context manager usage."""
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """Support context manager protocol without special cleanup."""
        return None

    def execute(self, sql: str, params: dict[str, Any]) -> None:
        """Record the payload for later assertions."""
        del sql
        self.rows.append(params.copy())

    def fetchone(self):
        """Return ``None`` for API compatibility."""
        return None

    def fetchall(self):
        """Return an empty list for API compatibility."""
        return []


class RecordingConnection:
    """Connection that provides a :class:`RecordingCursor`."""

    def __init__(self, cursor: RecordingCursor) -> None:
        """Store the cursor instance used for the connection."""
        self.cursor_obj = cursor

    def __enter__(self) -> "RecordingConnection":
        """Return ``self`` for context manager usage."""
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """Support context manager protocol without special cleanup."""
        return None

    def cursor(self) -> RecordingCursor:
        """Return the recording cursor."""
        return self.cursor_obj


__all__ = [
    "FakeDBConnection",
    "FakeCursor",
    "FakeProcess",
    "QueryCursor",
    "QueryConnection",
    "ScriptCursor",
    "ScriptConnection",
    "RecordingCursor",
    "RecordingConnection",
]
