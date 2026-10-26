from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import forecast, metrics


# Data is fetched by synchronous request dependencies, not during startup.
app = FastAPI()
app.include_router(forecast.router, prefix="/api")
app.include_router(metrics.router, prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"message": "backend connected successfully"}
