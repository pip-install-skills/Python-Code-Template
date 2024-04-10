from fastapi import FastAPI, Query
from pymongo import MongoClient

app = FastAPI()
client = MongoClient("mongodb://localhost:27017/")
db = client["your_database"]
collection = db["your_collection"]

@app.get("/entries/")
async def get_entries(page: int = Query(1, ge=1), per_page: int = Query(10, ge=1, le=100)):
    skip = (page - 1) * per_page
    entries_cursor = collection.find().skip(skip).limit(per_page)
    entries = list(entries_cursor)
    for entry in entries:
        entry["_id"] = str(entry["_id"])
        created_at = entry.get('created_at')
        if created_at is not None:
            entry['created_at'] = created_at.strftime("%Y-%m-%d %H:%M:%S")
    return entries
