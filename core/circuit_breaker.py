"""
Circuit Breaker 패턴 구현

외부 API(Gemini, NewsAPI, Slack 등) 장애 시 연쇄 실패를 차단.

상태 전이:
  CLOSED  → OPEN      : 연속 failure_threshold회 실패
  OPEN    → HALF_OPEN : recovery_timeout초 경과 후 자동 전환
  HALF_OPEN → CLOSED  : 테스트 호출 성공
  HALF_OPEN → OPEN    : 테스트 호출 실패

사용 예:
    cb = CircuitBreaker("gemini", failure_threshold=5, recovery_timeout=60)
    try:
        result = cb.call(my_api_func, arg1, arg2)
    except CircuitOpenError:
        # 서킷 열림 — 즉시 fallback 처리
"""

import logging
import threading
import time
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED    = "CLOSED"     # 정상 운영
    OPEN      = "OPEN"       # 차단 (외부 호출 금지)
    HALF_OPEN = "HALF_OPEN"  # 복구 테스트 중


class CircuitOpenError(Exception):
    """서킷이 OPEN 상태일 때 발생 — caller가 즉시 fallback 처리해야 함."""
    pass


class CircuitBreaker:
    """
    스레드 안전 Circuit Breaker.

    Args:
        name:              식별 이름 (로그용)
        failure_threshold: CLOSED → OPEN 전환까지 허용 연속 실패 횟수 (기본 5)
        recovery_timeout:  OPEN → HALF_OPEN 전환까지 대기 초 (기본 60)
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ):
        self.name              = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout  = recovery_timeout

        self._state           = CircuitState.CLOSED
        self._failure_count   = 0
        self._last_failure_at = 0.0
        self._lock            = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if (
                self._state == CircuitState.OPEN
                and time.time() - self._last_failure_at >= self.recovery_timeout
            ):
                self._state = CircuitState.HALF_OPEN
                logger.info(f"[CB:{self.name}] OPEN → HALF_OPEN (복구 테스트 시작)")
            return self._state

    def call(self, func, *args, **kwargs):
        """
        func를 실행. 서킷이 OPEN이면 CircuitOpenError 발생.
        성공 시 CLOSED, 실패 시 OPEN 상태로 전환.
        """
        current_state = self.state
        if current_state == CircuitState.OPEN:
            raise CircuitOpenError(
                f"Circuit '{self.name}' is OPEN — 외부 호출 차단 중 "
                f"({self.recovery_timeout}초 후 재시도)"
            )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except CircuitOpenError:
            raise
        except Exception:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info(f"[CB:{self.name}] HALF_OPEN → CLOSED (복구 성공)")
            self._state = CircuitState.CLOSED
            self._failure_count = 0

    def _on_failure(self) -> None:
        with self._lock:
            self._failure_count  += 1
            self._last_failure_at = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(f"[CB:{self.name}] HALF_OPEN → OPEN (복구 실패)")
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.error(
                    f"[CB:{self.name}] CLOSED → OPEN "
                    f"({self._failure_count}회 연속 실패 — "
                    f"{self.recovery_timeout:.0f}초 후 HALF_OPEN으로 전환)"
                )
