import os
import time
import uuid
import asyncio
import structlog
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi.responses import FileResponse
from motor.motor_asyncio import AsyncIOMotorClient

# Load environment variables from .env file
load_dotenv()

# Access environment variables as if they came from the actual environment
MONGO_INITDB_ROOT_USERNAME = os.getenv('MONGO_INITDB_ROOT_USERNAME')
MONGO_INITDB_ROOT_PASSWORD = os.getenv('MONGO_INITDB_ROOT_PASSWORD')

# Global objects to hold the MongoDB client and database
mongo_client = None
mongo_db = None

def mongodb_log_processor(_logger, method_name, event_dict):
    if mongo_db is not None:
        log_doc = event_dict.copy()
        log_doc["level"] = method_name
        
        # Add a native Python datetime object for MongoDB's TTL index
        log_doc["created_at"] = datetime.now(timezone.utc)
        
        async def save_to_mongo(document):
            try:
                if mongo_db is not None:
                    await mongo_db.api_logs.insert_one(document)
            except Exception as e:
                # Catch DB connection issues so they don't crash the event loop
                print(f"Background MongoDB insert failed: {e}")

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(save_to_mongo(log_doc))
        except RuntimeError:
            pass
            
    return event_dict

def drop_noisy_logs(_logger, _method_name, event_dict):
    """
    Drops log events associated with high-volume or noisy endpoints.
    """
    noisy_endpoints = ["/health", "/favicon.ico"]
    
    if event_dict.get("endpoint") in noisy_endpoints:
        raise structlog.DropEvent
        
    return event_dict

# Configure Structlog
structlog.configure(
    processors=[
        # 1. Merge context variables FIRST
        structlog.contextvars.merge_contextvars, 
        
        # 2. Add timestamps
        structlog.processors.TimeStamper(fmt="iso"),
        
        # 3. Filter noisy logs (your custom function)
        drop_noisy_logs,
        
        # 4. Save to database (your custom function)
        mongodb_log_processor,
        
        # 5. Render to console
        structlog.dev.ConsoleRenderer() 
    ]
)

# Instantiate the logger
logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    global mongo_client, mongo_db
    
    mongo_client = AsyncIOMotorClient(f"mongodb://{MONGO_INITDB_ROOT_USERNAME}:{MONGO_INITDB_ROOT_PASSWORD}@localhost:27017")
    mongo_db = mongo_client.log_database
    
    # ---------------------------------------------------------
    # Create the TTL Index here!
    # expireAfterSeconds = 604800 (which is exactly 7 days)
    # ---------------------------------------------------------
    await mongo_db.api_logs.create_index(
        "created_at", 
        expireAfterSeconds=7 * 24 * 60 * 60 
    )
    
    logger.info("Application starting", action="startup")
    
    yield
    
    logger.info("Application shutting down", action="shutdown")
    mongo_client.close()

# Create the FastAPI app
app = FastAPI(lifespan=lifespan)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    # 1. Clear the context (crucial to prevent data leaking between requests!)
    structlog.contextvars.clear_contextvars()
    
    # 2. Generate a unique Request ID
    request_id = str(uuid.uuid4())
    
    # 3. Bind the ID to the context. Every logger.info() called from here on 
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
    
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    # Return the actual file to the browser
    return FileResponse("favicon.ico")

@app.get("/")
async def read_root():
    # Because of our custom processor, this will instantly log to the console
    # while a background task handles saving it to MongoDB.
    # logger.info("Root endpoint accessed", endpoint="/", user="anonymous")
    return {"message": "Hello World"}

@app.post("/items/{item_id}")
async def create_item(item_id: int, q: str | None = None):
    if q:
        logger.info("Item searched", item_id=item_id, query=q, status="success")
    else:
        logger.warning("Item requested without query", item_id=item_id)
        
    return {"item_id": item_id, "query": q}

@app.get("/items/{item_id}")
async def get_item(item_id: int):
    # Notice we don't pass the request_id here manually!
    logger.info("Fetching item from database", item_id=item_id)
    
    # ... pretend we do some database lookup here ...
    time.sleep(2.5)
    
    logger.info("Item fetched successfully", item_id=item_id)
    return {"item": item_id}

@app.get("/health")
async def health_check():
    # Because of our new processor, this log will be completely ignored
    # logger.info("Health check ping", endpoint="/health", status="ok")
    return {"status": "healthy"}
