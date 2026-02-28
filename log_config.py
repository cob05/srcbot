# log_config.py
import asyncio
from datetime import datetime, timezone
import structlog

# A module-level variable to hold the database connection
_mongo_db = None

def set_mongo_db(db):
    """Called by FastAPI on startup to pass the active MongoDB connection."""
    global _mongo_db
    _mongo_db = db

def drop_noisy_logs(_logger, _method_name, event_dict):
    noisy_endpoints = ["/health", "/favicon.ico"]
    if event_dict.get("endpoint") in noisy_endpoints:
        raise structlog.DropEvent
    return event_dict

def mongodb_log_processor(_logger, method_name, event_dict):
    if _mongo_db is not None:
        log_doc = event_dict.copy()
        log_doc["level"] = method_name
        log_doc["created_at"] = datetime.now(timezone.utc)
        
        async def save_to_mongo(document):
            try:
                if _mongo_db is not None:
                    await _mongo_db.api_logs.insert_one(document)
            except Exception as e:
                print(f"Background MongoDB insert failed: {e}")

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(save_to_mongo(log_doc))
        except RuntimeError:
            pass
            
    return event_dict

def setup_logging():
    """Configures Structlog pipelines."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso"),
            drop_noisy_logs,
            mongodb_log_processor,
            structlog.dev.ConsoleRenderer()
        ]
    )