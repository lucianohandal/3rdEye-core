from fastapi import FastAPI

from api.v1.logs import router as logs_router
from configs import get_config


_config = get_config()

app = FastAPI(
    title=_config.app.title,
    version=_config.app.version,
)

app.include_router(logs_router, prefix="/v1")
