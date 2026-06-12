"""FastAPI application entrypoint for the Image-to-IMDB tool."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import auth, export, extract, records


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="AI-Driven Image-to-IMDB Tool",
    description="Auto-fill the 10 IMDB attributes from product images.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(extract.router)
app.include_router(records.router)
app.include_router(export.router)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}
