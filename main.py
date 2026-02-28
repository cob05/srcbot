import os
import time
import uuid
import asyncio
import structlog
from routers import items
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi.responses import FileResponse
from log_config import setup_logging, set_mongo_db
from motor.motor_asyncio import AsyncIOMotorClient

# Load environment variables from .env file
load_dotenv()

# Access environment variables as if they came from the actual environment
MONGO_INITDB_ROOT_USERNAME = os.getenv('MONGO_INITDB_ROOT_USERNAME')
MONGO_INITDB_ROOT_PASSWORD = os.getenv('MONGO_INITDB_ROOT_PASSWORD')

# Global objects to hold the MongoDB client and database
mongo_client = None

# Instantiate the logger
setup_logging()
logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    global mongo_client
    
    mongo_client = AsyncIOMotorClient(f"mongodb://{MONGO_INITDB_ROOT_USERNAME}:{MONGO_INITDB_ROOT_PASSWORD}@localhost:27017")
    db = mongo_client.log_database
    set_mongo_db(db)
    
    # ---------------------------------------------------------
    # Create the TTL Index here!
    # expireAfterSeconds = 604800 (which is exactly 7 days)
    # ---------------------------------------------------------
    # await mongo_db.srcbot_logs.create_index(
    #     "created_at", 
    #     expireAfterSeconds=7 * 24 * 60 * 60 
    # )
    await db.srcbot_logs.create_index("created_at", expireAfterSeconds=7 * 24 * 60 * 60)

    logger.info("Application starting", action="startup")
    
    yield
    
    logger.info("Application shutting down", action="shutdown")
    mongo_client.close()

# Create the FastAPI app
app = FastAPI(lifespan=lifespan)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Clear the context (crucial to prevent data leaking between requests!)
    structlog.contextvars.clear_contextvars()
    
    # Generate a unique Request ID
    request_id = str(uuid.uuid4())
    
    # Bind the ID to the context. Every logger.info() called from here on 
    # out—even inside your route functions—will automatically include this ID!
    structlog.contextvars.bind_contextvars(request_id=request_id)
    
    start_time = time.perf_counter()
    path = request.url.path
    
    try:
        response = await call_next(request)
        process_time = time.perf_counter() - start_time
        
        logger.info(
            "Request completed",
            method=request.method,
            endpoint=path,
            status_code=response.status_code,
            process_time=f"{process_time:.4f}s"
        )
        return response
        
    except Exception as e:
        process_time = time.perf_counter() - start_time
        logger.error(
            "Request failed with unhandled exception",
            method=request.method,
            endpoint=path,
            status_code=500,
            process_time=f"{process_time:.4f}s",
            error=str(e)
        )
        raise e
    
app.include_router(items.router)

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(os.path.join("assets", "static", "images", "favicon", "favicon.ico"))

@app.get("/")
async def read_root():
    return {"message": "Hello World"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
