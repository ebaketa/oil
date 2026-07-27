"""Process-local stop signals for active continuous measurement streams."""

from threading import Event, Lock


class ContinuousSessionRegistry:
    """Register stream owners and provide interruptible stop events."""

    _sessions: dict[str, tuple[int, Event]] = {}
    _lock = Lock()

    @classmethod
    def start(cls, session_id: str, user_id: int) -> Event:
        """Register a new session, rejecting duplicate identifiers."""
        with cls._lock:
            if session_id in cls._sessions:
                raise ValueError("Continuous measurement session already exists.")
            stop_event = Event()
            cls._sessions[session_id] = (user_id, stop_event)
            return stop_event

    @classmethod
    def stop(cls, session_id: str, user_id: int) -> bool:
        """Signal an owned session to stop."""
        with cls._lock:
            session = cls._sessions.get(session_id)
            if session is None or session[0] != user_id:
                return False
            session[1].set()
            return True

    @classmethod
    def finish(cls, session_id: str) -> None:
        """Remove a completed session from the registry."""
        with cls._lock:
            cls._sessions.pop(session_id, None)
