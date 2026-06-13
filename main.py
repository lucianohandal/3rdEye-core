from fastapi import FastAPI

from api.v1.logs import router as logs_router


app = FastAPI(
    title="3rd Eye API",
    version="0.1.0",
)

app.include_router(logs_router, prefix="/v1")