from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class Stage(Enum):
    """파이프라인 단계. 각 단계의 label은 UI 표시용 한국어."""
    INGEST = ("ingest", "문서 읽기")
    EXTRACT = ("extract", "참고문헌·인용 추출")
    VERIFY_METADATA = ("verify_metadata", "메타데이터 검증")
    FETCH_SOURCES = ("fetch_sources", "원문 확보")
    VERIFY_CONTENT = ("verify_content", "내용 검증")
    AGGREGATE = ("aggregate", "리포트 생성")

    def __init__(self, key: str, label: str):
        self.key = key
        self.label = label


@dataclass(frozen=True)
class ProgressEvent:
    stage: Stage
    current: int
    total: int
    message: str = ""


class ProgressReporter:
    """파이프라인이 호출하는 얇은 reporter. callback이 None이면 no-op."""

    def __init__(self, callback: Optional[Callable[[ProgressEvent], None]] = None):
        self._callback = callback
        self._current_totals: dict[Stage, int] = {}

    def _emit(self, event: ProgressEvent) -> None:
        if self._callback is not None:
            try:
                self._callback(event)
            except Exception:
                # UI 오류가 파이프라인을 중단시키지 않도록 swallow
                pass

    def start(self, stage: Stage, total: int, message: str = "") -> None:
        self._current_totals[stage] = total
        self._emit(ProgressEvent(stage=stage, current=0, total=total, message=message))

    def update(self, stage: Stage, current: int, message: str = "") -> None:
        total = self._current_totals.get(stage, 0)
        self._emit(ProgressEvent(stage=stage, current=current, total=total, message=message))

    def finish(self, stage: Stage, message: str = "") -> None:
        total = self._current_totals.get(stage, 0)
        self._emit(ProgressEvent(stage=stage, current=total, total=total, message=message))
