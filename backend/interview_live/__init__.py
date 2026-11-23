"""Modular monolith package for real-time turn-based interviews and follow-ups."""

from .config import FollowUpPolicy, InterviewLiveSettings, get_follow_up_policy, get_settings
from .migration import SESSION_TURN_DDL, ensure_session_turn_schema
from .router import create_interview_live_router

__all__ = [
    "FollowUpPolicy",
    "InterviewLiveSettings",
    "SESSION_TURN_DDL",
    "create_interview_live_router",
    "ensure_session_turn_schema",
    "get_follow_up_policy",
    "get_settings",
]
