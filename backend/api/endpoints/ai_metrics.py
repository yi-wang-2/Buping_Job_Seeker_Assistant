from fastapi import APIRouter, Query

from backend.services.ai_metrics_service import get_ai_metrics

router = APIRouter()


@router.get("")
def read_ai_metrics(days: int = Query(default=30, ge=1, le=365)) -> dict:
    return get_ai_metrics(days=days)

