"""POST /api/v1/analyze/trigger 라우터"""

import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, HTTPException

from db.connection import AsyncSessionLocal
from schemas.anomaly import JobResponse
from services.pipeline import run_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/analyze", tags=["Jobs"])

_jobs: dict[str, dict] = {}


@router.post("/trigger", response_model=JobResponse)
async def trigger_analysis(background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {"job_id": job_id, "status": "queued",
                     "started_at": None, "completed_at": None,
                     "anomaly_count": None, "message": None}
    background_tasks.add_task(_run_job, job_id)
    return JobResponse(**_jobs[job_id])


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="잡을 찾을 수 없음")
    return JobResponse(**_jobs[job_id])


async def _run_job(job_id: str):
    from main import ws_manager  # 순환 import 방지
    _jobs[job_id]["status"] = "running"
    _jobs[job_id]["started_at"] = datetime.now()
    try:
        async with AsyncSessionLocal() as db:
            result = await run_pipeline(db=db, broadcast=ws_manager.broadcast)
        _jobs[job_id].update({"status": "done", "completed_at": datetime.now(),
                               "anomaly_count": result.get("anomaly_count", 0),
                               "message": f"완료: {result.get('analyzed_count', 0)}개 분석"})
    except Exception as e:
        _jobs[job_id].update({"status": "failed", "completed_at": datetime.now(), "message": str(e)})
        logger.error(f"잡 실패 {job_id}: {e}")
