from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from auth.core import AuthContext
from auth.dependencies import require_jwt_scope_dependency, require_logs_write_api_key
from db.PostgresManager import get_rawlogs_db
from util.dto.api.LogEventDTO import LogEventDTO

router = APIRouter()

@router.post("/logs")
async def ingest_logs(
    log_events: list[LogEventDTO],
    response: Response,
    auth: Annotated[AuthContext, Depends(require_logs_write_api_key)],
):
    if not log_events:
        response.status_code = status.HTTP_204_NO_CONTENT
        return None

    await get_rawlogs_db(auth.org_id).insert_raw_logs(log_events)

    response.status_code = status.HTTP_202_ACCEPTED
    return {
        "message": f"Successfully processed {len(log_events)} items",
        "processed_count": len(log_events)
    }

@router.get("/search")
async def search_logs(
    auth: Annotated[AuthContext, Depends(require_jwt_scope_dependency("logs:read"))],
):
    print(auth.org_id)
    return {"org_id": str(auth.org_id)}

@router.get("/alerts")
async def get_alerts(
    auth: Annotated[AuthContext, Depends(require_jwt_scope_dependency("logs:read"))],
):
    print(auth.org_id)
    return {"org_id": str(auth.org_id)}