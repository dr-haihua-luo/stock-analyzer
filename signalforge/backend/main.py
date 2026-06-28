from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import analysis
from backend.config import settings
from backend.cache.redis_client import redis_client
import logging
import subprocess

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="Trading analysis application with AI agents",
    version="0.1.0",
    debug=settings.DEBUG
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(analysis.router, prefix="/api", tags=["analysis"])


@app.on_event("startup")
async def startup_event():
    """Initialize Redis connection and run database migrations on startup."""
    # Run database migrations using alembic
    try:
        logger.info("Running database migrations...")
        result = subprocess.run(
            ["uv", "run", "alembic", "upgrade", "head"],
            cwd=".",
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            logger.info("Database migrations completed successfully")
        else:
            logger.warning(f"Database migration warning: {result.stderr}")
    except Exception as e:
        logger.warning(f"Could not run migrations on startup: {e}")
        # Don't raise - allow app to start and try again later

    # Initialize Redis connection
    try:
        await redis_client.connect()
        logger.info("Redis connection initialized successfully")
    except ConnectionError as e:
        logger.warning(f"Failed to connect to Redis on startup: {e}")
        logger.warning("Application will continue without Redis caching")
        # Don't raise the error - allow app to start without Redis


@app.on_event("shutdown")
async def shutdown_event():
    """Close Redis connection on shutdown."""
    try:
        await redis_client.disconnect()
        logger.info("Redis connection closed")
    except Exception as e:
        logger.warning(f"Error closing Redis connection: {e}")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "version": "0.1.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": "0.1.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )