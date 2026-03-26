"""FastAPI 메인 앱 - REST API + WebSocket + 스케줄러 + Kafka Consumer (Phase 3)"""

import asyncio
import json
import logging
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

from db.connection import init_db, AsyncSessionLocal
from routers import anomalies, sectors, jobs, stocks, auth, user, performance, predictions
from services.pipeline import run_pipeline
from services.performance_tracker import run_performance_check
from services.weekly_report import run_weekly_report, run_monthly_report

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "")


# ── WebSocket 연결 관리 ───────────────────────────────────────────────────

class WebSocketManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self._connections.remove(ws)

    async def broadcast(self, message: dict):
        if not self._connections:
            return
        text = json.dumps(message, ensure_ascii=False, default=str)
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)


ws_manager = WebSocketManager()


# ── Phase 1/2: APScheduler 파이프라인 (Kafka 없을 때 fallback) ────────────

async def scheduled_analysis():
    try:
        async with AsyncSessionLocal() as db:
            result = await run_pipeline(
                db=db,
                broadcast=ws_manager.broadcast,
                threshold_pct=float(os.getenv("ANOMALY_THRESHOLD_PERCENT", "3.0")),
                threshold_z=float(os.getenv("ANOMALY_ZSCORE_THRESHOLD", "2.0")),
                kr_threshold_pct=float(os.getenv("ANOMALY_KR_THRESHOLD_PERCENT", "4.0")),
            )
        logger.info(f"스케줄 분석 완료: {result}")
    except Exception as e:
        logger.error(f"스케줄 분석 오류: {e}")


# ── Phase 3: Kafka Consumer (analysis.completed → DB 저장 + WS 브로드캐스트) ──

async def _save_and_broadcast(data: dict, loop: asyncio.AbstractEventLoop):
    """analysis.completed 메시지를 DB에 저장하고 WS로 브로드캐스트."""
    from db.repository import AnomalyRepository

    try:
        async with AsyncSessionLocal() as db:
            repo = AnomalyRepository(db)
            saved = await repo.save_anomaly({
                "ticker":              data["ticker"],
                "anomaly_date":        data.get("date"),
                "bar_timestamp":       data.get("bar_timestamp"),
                "return_pct":          data["return_pct"],
                "zscore":              data.get("zscore"),
                "close_price":         data.get("close_price"),
                "volume":              data.get("volume"),
                "direction":           data["direction"],
                "is_etf":              data.get("is_etf", False),
                "event_type":          data.get("event_type", "INDIVIDUAL"),
                "sector":              data.get("sector"),
                "sector_peer_count":   data.get("sector_peer_count"),
                "moving_sector_count": data.get("moving_sector_count"),
            })
            # 아직 분석이 저장되지 않은 경우에만 저장
            if not saved.analysis and data.get("analysis_ko"):
                await repo.save_analysis(
                    saved.id,
                    data.get("analysis_ko", ""),
                    data.get("analysis_en", ""),
                    data.get("news_en", []),
                    data.get("news_kr", []),
                )
            # 시그널 성과 추적 레코드 생성 (신규 anomaly인 경우에만)
            if saved.detected_at:
                try:
                    await repo.create_signal_performance(
                        anomaly_id=saved.id,
                        ticker=saved.ticker,
                        direction=saved.direction,
                        detected_price=saved.close_price,
                        detected_at=saved.detected_at,
                    )
                except Exception:
                    pass  # 이미 존재하면 (UNIQUE constraint) 무시

        await ws_manager.broadcast({
            "type":       "anomaly",
            "ticker":     data["ticker"],
            "return_pct": data["return_pct"],
            "direction":  data["direction"],
            "sector":     data.get("sector", ""),
            "event_type": data.get("event_type", "INDIVIDUAL"),
        })

    except Exception as e:
        logger.error(f"Kafka → DB/WS 처리 오류: {e}", exc_info=True)


def _run_kafka_consumer(loop: asyncio.AbstractEventLoop, stop_event: threading.Event):
    """별도 스레드에서 Kafka Consumer 실행 — analysis.completed 구독."""
    try:
        from confluent_kafka import Consumer, KafkaError
    except ImportError:
        logger.warning("confluent-kafka 미설치 — Kafka consumer 비활성")
        return

    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id":          "api-consumer-group",
        "auto.offset.reset": "latest",   # API는 새 메시지만 처리
    })
    consumer.subscribe(["analysis.completed"])
    logger.info("[Kafka] api-consumer 시작: analysis.completed 구독")

    try:
        while not stop_event.is_set():
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    logger.error(f"Kafka 오류: {msg.error()}")
                continue

            try:
                data = json.loads(msg.value())
                future = asyncio.run_coroutine_threadsafe(
                    _save_and_broadcast(data, loop), loop
                )
                future.result(timeout=30)
            except Exception as e:
                logger.error(f"Kafka 메시지 처리 오류: {e}", exc_info=True)

    finally:
        consumer.close()
        logger.info("[Kafka] api-consumer 종료")


# ── FastAPI lifespan ─────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    scheduler = None
    kafka_thread = None
    kafka_stop = threading.Event()

    # APScheduler (Phase 1/2 fallback — Kafka 없을 때도 동작)
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        interval = int(os.getenv("SCHEDULE_INTERVAL_MINUTES", "60"))
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            scheduled_analysis, "interval",
            minutes=interval, next_run_time=datetime.now(),
        )
        # 성과 추적기: 5분마다 측정 대기 레코드 처리
        scheduler.add_job(
            run_performance_check, "interval",
            minutes=5,
        )
        # 주간 리포트: 매주 월요일 09:00 KST (= 00:00 UTC)
        scheduler.add_job(
            run_weekly_report, "cron",
            day_of_week="mon", hour=0, minute=0,
        )
        # 월간 리포트: 매월 1일 09:00 KST
        scheduler.add_job(
            run_monthly_report, "cron",
            day=1, hour=0, minute=0,
        )
        scheduler.start()
        logger.info(f"스케줄러 시작: 분석={interval}분마다, 성과추적=5분마다, 주간/월간리포트")
    except ImportError:
        logger.warning("apscheduler 없음")

    # Kafka Consumer 스레드 (Phase 3 — KAFKA_BOOTSTRAP_SERVERS 설정 시 활성)
    if KAFKA_BOOTSTRAP:
        loop = asyncio.get_event_loop()
        kafka_thread = threading.Thread(
            target=_run_kafka_consumer,
            args=(loop, kafka_stop),
            daemon=True,
            name="kafka-consumer",
        )
        kafka_thread.start()
        logger.info(f"Kafka consumer 스레드 시작: {KAFKA_BOOTSTRAP}")
    else:
        logger.info("KAFKA_BOOTSTRAP_SERVERS 미설정 → Kafka consumer 비활성 (Phase 1/2 모드)")

    yield

    kafka_stop.set()
    if kafka_thread:
        kafka_thread.join(timeout=5)
    if scheduler:
        scheduler.shutdown()


# ── FastAPI 앱 ────────────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

app = FastAPI(
    title="주식 이상값 AI 분석기",
    description="실시간 주가 이상값 감지 및 AI 원인 분석 (한국어/영어)",
    version="2.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PUT"],
    allow_headers=["Content-Type", "Authorization"],
)

# Prometheus 계측 (설치되어 있을 때만 활성)
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app)
    logger.info("Prometheus /metrics 엔드포인트 활성")
except ImportError:
    logger.warning("prometheus-fastapi-instrumentator 미설치 — /metrics 비활성")

app.include_router(auth.router)
app.include_router(user.router)
app.include_router(anomalies.router)
app.include_router(sectors.router)
app.include_router(jobs.router)
app.include_router(stocks.router)
app.include_router(performance.router)
app.include_router(predictions.router)

# jobs 라우터에 ws_manager.broadcast 주입 (순환 임포트 없이)
from routers.jobs import set_broadcast  # noqa: E402
set_broadcast(ws_manager.broadcast)

# /api/v1/ → /api/v2/ 경로 별칭 (프론트엔드 v2 호환)
from fastapi.routing import APIRoute  # noqa: E402
for _route in list(app.routes):
    if isinstance(_route, APIRoute) and "/api/v1/" in _route.path:
        _v2_path = _route.path.replace("/api/v1/", "/api/v2/", 1)
        app.add_api_route(
            _v2_path,
            _route.endpoint,
            methods=list(_route.methods),
            response_model=_route.response_model,
            tags=_route.tags,
        )


@app.websocket("/ws/live")
async def websocket_endpoint(ws: WebSocket):
    # 토큰이 있으면 검증, 없으면 익명으로 연결 허용 (공개 데이터)
    token = ws.query_params.get("token")
    if token:
        from services.auth_service import _decode_token
        try:
            _decode_token(token, "access")
        except Exception:
            await ws.close(code=1008)  # Policy Violation
            return
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


@app.get("/health", tags=["System"])
async def health():
    checks: dict[str, str] = {}

    # DB 연결 확인
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(__import__("sqlalchemy").text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = f"error: {e}"

    # Kafka 확인
    checks["kafka"] = "enabled" if KAFKA_BOOTSTRAP else "disabled"

    overall = "healthy" if all(v in ("ok", "enabled", "disabled") for v in checks.values()) else "unhealthy"

    return {
        "status":         overall,
        "time":           datetime.now().isoformat(),
        "ws_connections": len(ws_manager._connections),
        "checks":         checks,
    }
