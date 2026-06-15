from fastapi import APIRouter, Response, status

from db.PostgresManager import get_rawlogs_db
from util.dto.api.LogEventDTO import LogEventDTO

router = APIRouter()

@router.post("/logs")
async def ingest_logs(log_events: list[LogEventDTO], response: Response):
    if not log_events:
        response.status_code = status.HTTP_204_NO_CONTENT
        return None

    org_id = "project_context.org_id"
    api_key_id = "project_context.api_key_id"

    #TODO: authorize api_key_id

    db = get_rawlogs_db(org_id)
    await db.insert_raw_logs(log_events)

    response.status_code = status.HTTP_202_ACCEPTED
    return {
        "message": f"Successfully processed {len(log_events)} items",
        "processed_count": len(log_events)
    }
