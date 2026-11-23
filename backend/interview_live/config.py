"""Centralized configuration and difficulty follow-up policy for interview_live."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FollowUpPolicy:
    difficulty: str
    enabled: bool
    max_per_base_question: int
    pressure_level: str

    def to_payload(self) -> dict:
        return {
            "difficulty": self.difficulty,
            "enabled": self.enabled,
            "maxPerBaseQuestion": self.max_per_base_question,
            "pressureLevel": self.pressure_level,
        }


_DIFFICULTY_POLICIES: dict[str, FollowUpPolicy] = {
    "basic": FollowUpPolicy(
        difficulty="basic",
        enabled=False,
        max_per_base_question=0,
        pressure_level="none",
    ),
    "intermediate": FollowUpPolicy(
        difficulty="intermediate",
        enabled=True,
        max_per_base_question=1,
        pressure_level="moderate",
    ),
    "hard": FollowUpPolicy(
        difficulty="hard",
        enabled=True,
        max_per_base_question=1,
        pressure_level="high_red_line_focus",
    ),
}

_DIFFICULTY_ALIASES: dict[str, str] = {
    "basic": "basic",
    "facil": "basic",
    "fácil": "basic",
    "easy": "basic",
    "bajo": "basic",
    "intermediate": "intermediate",
    "intermedio": "intermediate",
    "medio": "intermediate",
    "medium": "intermediate",
    "hard": "hard",
    "dificil": "hard",
    "difícil": "hard",
    "alto": "hard",
}


def normalize_difficulty(raw_difficulty: str | None) -> str:
    if not raw_difficulty:
        return "intermediate"
    key = str(raw_difficulty).strip().lower()
    return _DIFFICULTY_ALIASES.get(key, "intermediate")


def get_follow_up_policy(raw_difficulty: str | None) -> FollowUpPolicy:
    canonical = normalize_difficulty(raw_difficulty)
    return _DIFFICULTY_POLICIES[canonical]


@dataclass(frozen=True)
class InterviewLiveSettings:
    gemini_api_key: str
    gemini_followup_model: str
    gemini_timeout_sec: float
    nvidia_api_key: str
    nvidia_riva_server: str
    nvidia_function_id: str
    nvidia_language_code: str
    max_audio_bytes: int
    bg_concurrency: int
    context_cache_ttl_sec: int
    context_cache_max_entries: int
    tmp_dir: Path


def get_settings() -> InterviewLiveSettings:
    tmp_root = os.getenv("INTERVIEW_LIVE_TMP_DIR") or str(
        Path(tempfile.gettempdir()) / "voxready_interview_live"
    )
    return InterviewLiveSettings(
        gemini_api_key=(os.getenv("GEMINI_API_KEY") or "").strip(),
        gemini_followup_model=(
            os.getenv("GEMINI_FOLLOWUP_MODEL")
            or os.getenv("GEMINI_FAST_MODEL")
            or "gemini-3.5-flash-lite"
        ).strip(),
        gemini_timeout_sec=float(os.getenv("GEMINI_FOLLOWUP_TIMEOUT_SEC", "12.0")),
        nvidia_api_key=(os.getenv("NVIDIA_API_KEY") or "").strip(),
        nvidia_riva_server=(
            os.getenv("NVIDIA_RIVA_SERVER") or "grpc.nvcf.nvidia.com:443"
        ).strip(),
        nvidia_function_id=(
            os.getenv("NVIDIA_FUNCTION_ID") or "71203149-d3b7-4460-8231-1be2543a1fca"
        ).strip(),
        nvidia_language_code=(os.getenv("NVIDIA_LANGUAGE_CODE") or "es-US").strip(),
        max_audio_bytes=int(
            os.getenv("INTERVIEW_LIVE_MAX_AUDIO_BYTES", str(15 * 1024 * 1024))
        ),
        bg_concurrency=max(1, int(os.getenv("INTERVIEW_LIVE_BG_CONCURRENCY", "2"))),
        context_cache_ttl_sec=max(
            60, int(os.getenv("INTERVIEW_LIVE_CONTEXT_TTL_SEC", "1800"))
        ),
        context_cache_max_entries=max(
            32, int(os.getenv("INTERVIEW_LIVE_CONTEXT_MAX_ENTRIES", "512"))
        ),
        tmp_dir=Path(tmp_root),
    )
