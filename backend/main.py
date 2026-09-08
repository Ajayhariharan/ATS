from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import config

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logging.getLogger("httpx").setLevel(logging.INFO)

# Import ATS core routes and database
from database import db
from routes.role_routes import router as role_router
from routes.candidate_routes import router as candidate_router
from routes.settings_routes import router as settings_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Automatically verify and create database + tables + seed data if missing
    try:
        db.init_database()
    except Exception as e:
        logging.error(f"[Startup] Database initialization error: {e}")
    yield

app = FastAPI(title="Enterprise ATS", version="1.0.0", lifespan=lifespan)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(role_router)
app.include_router(candidate_router)
app.include_router(settings_router)

@app.get("/")
async def root():
    return {
        "message": "Enterprise ATS System",
        "version": "1.0.0",
        "status": "operational",
        "database": config.DB_NAME,
        "server": config.DB_HOST,
        "llm_provider": "OpenRouter Gemini"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "openrouter_gemini_configured": bool(config.OPENROUTER_API_KEY),
        "database_configured": bool(config.DB_HOST)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG,
        log_level="info"
    )