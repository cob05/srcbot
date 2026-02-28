# routers/items.py
from fastapi import APIRouter
import structlog

# Initialize the router with a prefix and a tag for the Swagger docs
router = APIRouter(
    prefix="/items",
    tags=["Items"]
)

# Grab the Structlog logger (it automatically inherits your main.py config!)
logger = structlog.get_logger()

@router.get("/{item_id}")
async def read_item(item_id: int, q: str | None = None):
    if q:
        logger.info("Item searched", item_id=item_id, query=q)
    else:
        logger.warning("Item requested without query", item_id=item_id)
        
    return {"item_id": item_id, "query": q}

@router.post("/")
async def create_item(item_name: str):
    logger.info("Item created", item_name=item_name)
    return {"name": item_name, "status": "success"}
