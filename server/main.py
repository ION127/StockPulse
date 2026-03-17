"""FastAPI 메인 앱 - REST API + WebSocket + 스케줄러"""

import os
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from server.db.connection import init_db, AsyncSessionLocal
from server.routers import anomalies, sectors, jobs
from server.services.pipeline import run_pipeline

logger = logging.getLogger(__name__)


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


async def scheduled_analysis():
    try:
        async with AsyncSessionLocal() as db:
            result = await run_pipeline(
                db=db, broadcast=ws_manager.broadcast,
                threshold_pct=float(os.getenv("ANOMALY_THRESHOLD_PERCENT", "8.0")),
                threshold_z=float(os.getenv("ANOMALY_ZSCORE_THRESHOLD", "3.0")),
            )
        logger.info(f"스케줄 분석 완료: {result}")
    except Exception as e:
        logger.error(f"스케줄 분석 오류: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scheduler = None
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        interval = int(os.getenv("SCHEDULE_INTERVAL_MINUTES", "60"))
        scheduler = AsyncIOScheduler()
        scheduler.add_job(scheduled_analysis, "interval", minutes=interval,
                          next_run_time=datetime.now())
        scheduler.start()
        logger.info(f"스케줄러 시작: {interval}분마다")
    except ImportError:
        logger.warning("apscheduler 없음")
    yield
    if scheduler:
        scheduler.shutdown()


app = FastAPI(
    title="주식 이상값 AI 분석기",
    description="실시간 주가 이상값 감지 및 AI 원인 분석 (한국어/영어)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

app.include_router(anomalies.router)
app.include_router(sectors.router)
app.include_router(jobs.router)


@app.websocket("/ws/live")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "time": datetime.now().isoformat(),
            "ws_connections": len(ws_manager._connections)}
