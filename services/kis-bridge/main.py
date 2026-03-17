"""
KIS Bridge 서비스 — 한국투자증권 Open API

역할:
  - 한국투자증권 WebSocket으로 한국 주식 실시간 체결 데이터 수신
  - 1분봉 OHLCV로 집계 후 Kafka Topic 'stock.raw.kr'에 발행
  - HTS(영웅문) 불필요 — app_key + app_secret만으로 동작
  - Docker 컨테이너 실행 가능 (Linux 기반)

실행 환경:
  - Docker 또는 Python 직접 실행 모두 가능

환경변수:
  KIS_APP_KEY              한국투자증권 앱키
  KIS_APP_SECRET           한국투자증권 앱시크릿
  KIS_ACCOUNT_NO           계좌번호 (XXXXXXXX-XX 형식, 선택)
  KIS_MOCK                 모의투자 모드 (true/false, 기본 false)
  KAFKA_BOOTSTRAP_SERVERS  Kafka 브로커 주소 (기본 kafka:9092)
  FLUSH_INTERVAL_SECONDS   1분봉 플러시 주기 초 (기본 60)

앱키 발급:
  https://apiportal.koreainvestment.com → 내 앱 → 앱 등록

WebSocket TR:
  H0STCNT0  주식 실시간 체결 (실전)
  H0STCNS0  주식 실시간 체결 (모의)

※ KIS WebSocket 제약:
  - 연결당 최대 40개 종목 구독 → 40개 초과 시 다중 연결
  - 액세스 토큰 유효기간 24시간 → 자동 갱신
"""

import asyncio
import json
import logging
import os
import signal
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta

import aiohttp
import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("kis-bridge")

# ── 환경변수 ─────────────────────────────────────────────────────────────────
KIS_APP_KEY    = os.getenv("KIS_APP_KEY", "")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET", "")
KIS_MOCK       = os.getenv("KIS_MOCK", "false").lower() == "true"
KAFKA_BOOTSTRAP      = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
FLUSH_INTERVAL_SEC   = int(os.getenv("FLUSH_INTERVAL_SECONDS", "60"))
WS_BATCH_SIZE        = 40  # KIS WebSocket 연결당 최대 구독 종목 수

# ── KIS API 엔드포인트 ────────────────────────────────────────────────────────
REST_BASE = "https://openapi.koreainvestment.com:9443"
WS_URL    = (
    "wss://openapiwss.kis.uat.koreainvestment.com:21000"
    if KIS_MOCK else
    "wss://openapi.koreainvestment.com:21000"
)
TR_ID_REALTIME = "H0STCNS0" if KIS_MOCK else "H0STCNT0"  # 주식 실시간 체결

# ── 1분봉 집계 저장소 ─────────────────────────────────────────────────────────
# {ticker_code: {open, high, low, close, volume}}
_candles: dict[str, dict] = defaultdict(dict)

_running = True


def _handle_signal(sig, frame):
    global _running
    logger.info("종료 신호 수신 — 루프 종료 중")
    _running = False


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


# ── KIS 인증 ─────────────────────────────────────────────────────────────────

class KisAuth:
    """액세스 토큰 + WebSocket 접속키 관리 (자동 갱신)."""

    def __init__(self, app_key: str, app_secret: str):
        self.app_key    = app_key
        self.app_secret = app_secret
        self._token:        str      = ""
        self._approval_key: str      = ""
        self._token_expires: datetime = datetime.min

    async def get_access_token(self) -> str:
        """액세스 토큰 반환 (만료 시 자동 갱신)."""
        if datetime.now() < self._token_expires - timedelta(minutes=10):
            return self._token

        url  = f"{REST_BASE}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey":     self.app_key,
            "appsecret":  self.app_secret,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body) as resp:
                data = await resp.json()
                self._token         = data["access_token"]
                expires_in          = int(data.get("expires_in", 86400))
                self._token_expires = datetime.now() + timedelta(seconds=expires_in)
                logger.info(f"액세스 토큰 발급 완료 (만료: {self._token_expires:%H:%M:%S})")
                return self._token

    async def get_approval_key(self) -> str:
        """WebSocket 접속키 반환 (최초 1회 발급)."""
        if self._approval_key:
            return self._approval_key

        url  = f"{REST_BASE}/oauth2/Approval"
        body = {
            "grant_type": "client_credentials",
            "appkey":     self.app_key,
            "secretkey":  self.app_secret,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body) as resp:
                data = await resp.json()
                self._approval_key = data["approval_key"]
                logger.info("WebSocket 접속키 발급 완료")
                return self._approval_key


# ── 틱 처리 ──────────────────────────────────────────────────────────────────

def _process_tick(raw: str) -> None:
    """
    KIS 실시간 체결 데이터 파싱 → 1분봉 집계.
    데이터 형식: '0|H0STCNT0|1|<^구분 필드들>'
    """
    try:
        parts = raw.split("|")
        if len(parts) < 4:
            return
        if parts[1] != TR_ID_REALTIME:
            return

        fields = parts[3].split("^")
        code   = fields[0]                      # 종목코드
        price  = abs(int(fields[2]))            # 현재가
        open_  = abs(int(fields[7]))            # 시가 (당일)
        high   = abs(int(fields[8]))            # 고가 (당일)
        low    = abs(int(fields[9]))            # 저가 (당일)
        vol    = abs(int(fields[12]))           # 체결 거래량 (틱)

        if not price:
            return

        c = _candles[code]
        if not c:
            # 분봉 첫 틱
            c["open"]   = open_ if open_ else price
            c["high"]   = price
            c["low"]    = price
            c["close"]  = price
            c["volume"] = vol
        else:
            c["high"]    = max(c["high"], price)
            c["low"]     = min(c["low"],  price)
            c["close"]   = price
            c["volume"] += vol

    except (IndexError, ValueError) as e:
        logger.debug(f"틱 파싱 오류: {e} | raw={raw[:80]}")


# ── Kafka 발행 ───────────────────────────────────────────────────────────────

def _build_producer():
    from confluent_kafka import Producer
    return Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "message.max.bytes": 10_485_760,
    })


def _flush_candles(producer) -> None:
    """완성된 1분봉을 stock.raw.kr 토픽에 발행 후 집계 초기화."""
    if not _candles:
        return

    minute_str = datetime.now().strftime("%Y-%m-%d %H:%M:00")
    stocks = {
        f"KR:{code}": {
            minute_str: {
                "Open":   c["open"],
                "High":   c["high"],
                "Low":    c["low"],
                "Close":  c["close"],
                "Volume": c["volume"],
            }
        }
        for code, c in _candles.items()
        if c
    }

    if stocks:
        payload = {
            "market":    "kr",
            "timestamp": datetime.now().isoformat(),
            "stocks":    stocks,
        }
        value = json.dumps(payload, default=str).encode("utf-8")
        producer.produce("stock.raw.kr", key="realtime", value=value)
        producer.flush()
        logger.info(f"[stock.raw.kr] {len(stocks)}개 종목 1분봉 발행")

    _candles.clear()


# ── WebSocket 연결 (배치당 40 종목) ──────────────────────────────────────────

def _subscribe_msg(approval_key: str, ticker: str) -> str:
    return json.dumps({
        "header": {
            "approval_key": approval_key,
            "custtype":     "P",
            "tr_type":      "1",        # 1: 등록
            "content-type": "utf-8",
        },
        "body": {
            "input": {
                "tr_id":  TR_ID_REALTIME,
                "tr_key": ticker,
            }
        },
    })


async def _ws_worker(
    auth: KisAuth,
    tickers: list[str],
    worker_id: int,
) -> None:
    """단일 WebSocket 연결 — tickers 목록 구독 + 틱 수신."""
    retry_wait = 5

    while _running:
        try:
            approval_key = await auth.get_approval_key()
            logger.info(f"[WS#{worker_id}] 연결 시작 ({len(tickers)}개 종목)")

            async with websockets.connect(
                WS_URL,
                ping_interval=30,
                ping_timeout=10,
            ) as ws:
                # 종목 구독 등록
                for ticker in tickers:
                    await ws.send(_subscribe_msg(approval_key, ticker))
                logger.info(f"[WS#{worker_id}] {len(tickers)}개 종목 구독 완료")
                retry_wait = 5  # 성공 후 재시도 간격 초기화

                async for message in ws:
                    if not _running:
                        break

                    # KIS PINGPONG 응답 (애플리케이션 레벨)
                    if message == "PINGPONG":
                        await ws.send("PINGPONG")
                        continue

                    # JSON 시스템 메시지 (구독 확인 등) — 무시
                    if message.startswith("{"):
                        continue

                    _process_tick(message)

        except websockets.exceptions.ConnectionClosedError as e:
            logger.warning(f"[WS#{worker_id}] 연결 끊김: {e} — {retry_wait}s 후 재연결")
        except Exception as e:
            logger.error(f"[WS#{worker_id}] 오류: {e} — {retry_wait}s 후 재연결")

        if _running:
            await asyncio.sleep(retry_wait)
            retry_wait = min(retry_wait * 2, 60)  # 최대 60s 대기


# ── 플러시 루프 ───────────────────────────────────────────────────────────────

async def _flush_loop(producer) -> None:
    """매 FLUSH_INTERVAL_SEC마다 1분봉을 Kafka에 발행."""
    while _running:
        await asyncio.sleep(FLUSH_INTERVAL_SEC)
        try:
            _flush_candles(producer)
        except Exception as e:
            logger.error(f"플러시 오류: {e}", exc_info=True)


# ── main ──────────────────────────────────────────────────────────────────────

async def async_main() -> None:
    if not KIS_APP_KEY or not KIS_APP_SECRET:
        logger.error("KIS_APP_KEY, KIS_APP_SECRET 환경변수를 설정하세요.")
        sys.exit(1)

    logger.info(
        f"[kis-bridge] 시작 | 모드={'모의' if KIS_MOCK else '실전'} "
        f"| Kafka: {KAFKA_BOOTSTRAP} | 플러시: {FLUSH_INTERVAL_SEC}s"
    )

    try:
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        from core.stock_categories import get_all_kr_tickers
    except ImportError as e:
        logger.error(f"core 모듈 임포트 실패: {e}")
        sys.exit(1)

    auth     = KisAuth(KIS_APP_KEY, KIS_APP_SECRET)
    producer = _build_producer()

    # 토큰 미리 발급
    await auth.get_access_token()
    await auth.get_approval_key()

    kr_tickers = get_all_kr_tickers()
    logger.info(f"모니터링 종목: {len(kr_tickers)}개")

    # 40개씩 분할 → 다중 WebSocket 연결
    batches = [kr_tickers[i:i + WS_BATCH_SIZE] for i in range(0, len(kr_tickers), WS_BATCH_SIZE)]
    logger.info(f"WebSocket 연결 수: {len(batches)}개 (연결당 최대 {WS_BATCH_SIZE}종목)")

    tasks = [
        asyncio.create_task(_ws_worker(auth, batch, idx))
        for idx, batch in enumerate(batches)
    ]
    tasks.append(asyncio.create_task(_flush_loop(producer)))

    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("[kis-bridge] 종료")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
