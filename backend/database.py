import os
from datetime import datetime
from typing import Any, Dict
from pymongo import MongoClient, ReturnDocument

DATABASE_URL = os.environ.get("DATABASE_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.environ.get("DATABASE_NAME", "secret_closet")

client = MongoClient(DATABASE_URL)
db = client[DATABASE_NAME]


def create_document(collection_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.utcnow()
    data.setdefault("created_at", now)
    data.setdefault("updated_at", now)
    res = db[collection_name].insert_one(data)
    return db[collection_name].find_one({"_id": res.inserted_id})


def get_documents(collection_name: str, filter_dict: Dict[str, Any] | None = None, limit: int = 50):
    return list(db[collection_name].find(filter_dict or {}).limit(limit))
