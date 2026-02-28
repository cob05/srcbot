"""
How to Use It

Open a new terminal window (while your MongoDB server is running) and run the script using different flags:

    View the 5 most recent logs (default behavior):
    python query_logs.py

    View only the errors (great for debugging):
    python query_logs.py --level error

    Trace a specific request (paste a request_id from your console output):
    python query_logs.py --id "123e4567-e89b-12d3-a456-426614174000" --limit 20

Because of pprint, your output will look like beautifully formatted Python dictionaries, making it incredibly easy to scan through the contextual data like process_time, endpoint, and status_code.
"""

import os
import asyncio
import argparse
from pprint import pprint
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# Load environment variables from .env file
load_dotenv()

# Access environment variables as if they came from the actual environment
MONGO_INITDB_ROOT_USERNAME = os.getenv('MONGO_INITDB_ROOT_USERNAME')
MONGO_INITDB_ROOT_PASSWORD = os.getenv('MONGO_INITDB_ROOT_PASSWORD')

async def search_logs(level: str | None, request_id: str | None, limit: int):
    # Connect to the local MongoDB instance
    client = AsyncIOMotorClient(f"mongodb://{MONGO_INITDB_ROOT_USERNAME}:{MONGO_INITDB_ROOT_PASSWORD}@localhost:27017")
    collection = client.log_database.srcbot_logs

    # Dynamically build our MongoDB query dictionary
    query = {}
    if level:
        query["level"] = level
    if request_id:
        query["request_id"] = request_id

    print(f"Searching MongoDB with query: {query}\n")
    print("=" * 60)

    # Search the collection, sorting by newest first (assuming TimeStamper adds 'timestamp')
    # If your TimeStamper doesn't add 'timestamp', MongoDB's default order is usually insertion order
    cursor = collection.find(query).sort("$natural", -1).limit(limit)
    
    # Fetch the results
    logs = await cursor.to_list(length=limit)

    if not logs:
        print("No logs found matching your criteria.")
    else:
        for log in logs:
            # Remove the internal MongoDB object ID so the output is cleaner
            log.pop('_id', None)
            
            # Pretty-print the dictionary
            pprint(log)
            print("-" * 60)

    # Clean up the connection
    client.close()

if __name__ == "__main__":
    # Set up command-line arguments
    parser = argparse.ArgumentParser(description="Search Structlog entries in MongoDB.")
    parser.add_argument("--level", type=str, help="Filter by severity (e.g., info, error, warning)")
    parser.add_argument("--id", type=str, help="Filter by a specific request_id")
    parser.add_argument("--limit", type=int, default=5, help="Number of recent logs to fetch (default: 5)")

    args = parser.parse_args()

    # Run the async query function
    asyncio.run(search_logs(level=args.level, request_id=args.id, limit=args.limit))
