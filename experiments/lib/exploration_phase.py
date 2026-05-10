"""Phase F.1 — Cold-start exploration round-robin.

신규 회원은 *positivity 영역*(시도해 본 시간대) 데이터가 0건이라 forward simulation
후보가 없다. 첫 4주는 *exploration phase*로 둬서 *주 단위로 다른 시간대*를 권장하고
데이터를 균등 수집한다. 5주차부터 *exploitation*으로 전환되어 본격 추천이 활성화.

이 흐름의 가치는 *positivity 제약을 자연스럽게 충족*시킨다는 점 — exploration 4주
후에는 회원이 4 시간대 슬롯을 모두 *최소 한 번씩* 시도해 본 상태가 된다.
"""
from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd


EXPLORATION_WEEKS = 4

# 운동 종료 시각 기준 슬롯 (Phase A.2의 저녁 세분화와 일관)
EXPLORATION_SLOTS = [
    ("morning",       8, 12),
    ("afternoon",    12, 18),
    ("evening_18_20", 18, 20),
    ("evening_20_22", 20, 22),
]


def weeks_active(train_master: pd.DataFrame) -> int:
    """train_master에서 가장 빠른 일자부터 오늘까지 *완전 주 수*를 계산."""
    if train_master is None or train_master.empty:
        return 0
    first_date = pd.to_datetime(train_master["date"]).min()
    today = pd.Timestamp.now().normalize()
    return max(0, (today - first_date).days // 7)


def recommendation_mode(
    train_master: pd.DataFrame,
    exploration_weeks: int = EXPLORATION_WEEKS,
) -> Tuple[str, Optional[Tuple[str, int, int]]]:
    """현재 회원의 추천 모드를 결정.

    Returns:
        ('exploration', (label, start_hour, end_hour)) — exploration_weeks 미만 주차의 round-robin 슬롯
        ('exploitation', None)                          — 그 이후, forward simulation 활성

    회원이 cold-start 단계임은 트레이너 카드에 명시해 추천이 *데이터 수집용*임을
    드러내야 한다 (오해 방지).
    """
    weeks = weeks_active(train_master)
    if weeks < exploration_weeks:
        slot = EXPLORATION_SLOTS[weeks % len(EXPLORATION_SLOTS)]
        return "exploration", slot
    return "exploitation", None


def explanation_text(mode: str, slot: Optional[Tuple[str, int, int]]) -> str:
    """트레이너 카드에 표시할 한 줄 설명. UI 측에서 직접 사용."""
    if mode == "exploration" and slot is not None:
        label, start, end = slot
        return (f"이번 주 권장 시간대: {label} ({start:02d}:00-{end:02d}:00). "
                f"신규 회원 cold-start 단계 — 추천이 아닌 *균등 시도* 중.")
    return "Forward simulation 추천 활성 — PSQI 합산 최소 슬롯 도출 중."
