from fastapi import APIRouter, Response, status

from db.PostgresManager import get_rawlogs_db, get_users_db
from util.dto.api.LogEventDTO import LogEventDTO

router = APIRouter()

@router.post("/logs")
async def ingest_logs(log_events: list[LogEventDTO], response: Response):
    if not log_events:
        response.status_code = status.HTTP_204_NO_CONTENT
        return None

    api_key_id = "project_context.api_key_id"
    org_id = await get_users_db().get_org_id(api_key_id)

    if not org_id:
        # TODO: authorize api_key_id
        response.status_code = status.HTTP_404_NOT_FOUND
        return {"message": "Invalid API key"}

    await get_rawlogs_db(org_id).insert_raw_logs(log_events)

    response.status_code = status.HTTP_202_ACCEPTED
    return {
        "message": f"Successfully processed {len(log_events)} items",
        "processed_count": len(log_events)
    }
