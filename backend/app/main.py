"""FastAPI application entrypoint for the Image-to-IMDB tool."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal, init_db
from app.routers import auth, export, extract, meta, records, sessions

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast in production if the JWT secret was never changed.
    if settings.jwt_secret_is_default:
        msg = "JWT_SECRET is unset/default — tokens would be forgeable."
        if settings.is_production:
            raise RuntimeError(msg + " Refusing to start in production.")
        logger.warning("%s Set JWT_SECRET in .env before deploying.", msg)
    if not settings.gemini_api_key:
        logger.warning("GEMINI_API_KEY is not set — image extraction will fail until configured.")

    if settings.auto_create_tables:
        init_db()
    else:
        logger.info("AUTO_CREATE_TABLES is off — manage schema with `alembic upgrade head`.")
    yield


app = FastAPI(
    title="AI-Driven Image-to-IMDB Tool",
    description="Auto-fill product master attributes from product images.",
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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all so unexpected errors return a clean envelope, never a stack trace."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# Versioned API — all feature routers live under /api/v1.
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(extract.router, prefix=settings.api_prefix)
app.include_router(records.router, prefix=settings.api_prefix)
app.include_router(sessions.router, prefix=settings.api_prefix)
app.include_router(meta.router, prefix=settings.api_prefix)
app.include_router(export.router, prefix=settings.api_prefix)


@app.get("/health", tags=["health"])
def health() -> JSONResponse:
    """Readiness probe — verifies the database is reachable."""
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return JSONResponse({"status": "ok", "database": "ok"})
    except Exception as exc:  # noqa: BLE001
        logger.error("Health check DB failure: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "degraded", "database": "error"},
        )
