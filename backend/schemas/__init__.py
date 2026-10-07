try:
    from .session import TurnInterval, FinishSessionRequest, WorkerTriggerPayload
except ImportError:
    from schemas.session import TurnInterval, FinishSessionRequest, WorkerTriggerPayload

__all__ = ["TurnInterval", "FinishSessionRequest", "WorkerTriggerPayload"]
