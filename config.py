import json
import os


MONGO_URI = os.getenv(
    "MONGO_URI", "mongodb://admin:changeme@localhost:27017/?authSource=admin"
)
MONGO_DB = os.getenv("MONGO_DB", "systematic_review")


def load_api_keys(path="api_keys.json"):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def load_search_terms(path="search_terms.json"):
    with open(path) as f:
        data = json.load(f)
    # Support both "search_terms" (new) and "initial_terms" (legacy) keys
    return data.get("search_terms", data.get("initial_terms", []))
