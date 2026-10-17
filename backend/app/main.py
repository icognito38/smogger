from fastapi import FastAPI

from app.api.smoke import router as smoke_router

app = FastAPI(
    title="GoEZ Wildfire Smoke Service",
    version="0.1.0",
    description="Approximate smoke-transport forecasts for wildfire decision support.",
)

app.include_router(smoke_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
