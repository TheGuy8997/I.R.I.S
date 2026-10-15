# =========================
# NEWS MODULE
# =========================

import requests
import time
import os
from datetime import datetime

# =========================
# CONFIG
# =========================

API_TOKEN = os.getenv("WEBZ_API_TOKEN", "").strip()
API_URL = "https://api.webz.io/newsApiLite"

NEWS_CACHE = {
    "data": None,
    "timestamp": 0,
    "category": None
}

CACHE_DURATION = 600  # 10 minutes

# =========================
# NEWS CATEGORY DETECTION
# =========================

def categorize_news_request(text: str) -> str:
    text = text.lower()

    # Summary requests
    if any(w in text for w in ["summarize", "summary", "roundup", "main stories", "overview"]):
        return "summary"

    # Technology
    if any(w in text for w in ["tech", "technology", "linux", "windows", "amd", "nvidia", "ai"]):
        return "technology"

    # World / International
    if any(w in text for w in ["world", "global", "international", "worldwide"]):
        return "world"

    # Politics
    if any(w in text for w in ["politics", "government", "president", "congress", "senate"]):
        return "politics"

    # Sports
    if any(w in text for w in ["sports", "football", "basketball", "soccer"]):
        return "sports"

    # Business
    if any(w in text for w in ["business", "market", "economy", "finance", "stocks"]):
        return "business"

    # Entertainment
    if any(w in text for w in ["entertainment", "celebrity", "movie", "music", "hollywood"]):
        return "entertainment"

    return "news"

# =========================
# NEWS FETCHING ENGINE
# =========================

def fetch_news(category: str):
    """Low-level API fetcher"""

    if not API_TOKEN:
        print("[NEWS ERROR] WEBZ_API_TOKEN is not configured")
        return []

    query = category

    params = {
        "token": API_TOKEN,
        "q": query,
        "size": 10
    }

    # Force US-only for all except world news
    if category not in ["world", "global", "international"]:
        params["country"] = "us"

    try:
        print(f"[NEWS] Fetching {category} news")
        response = requests.get(API_URL, params=params, timeout=10)

        if response.status_code == 429:
            print("[NEWS ERROR] Rate limit exceeded")
            return []

        if response.status_code != 200:
            print(f"[NEWS ERROR] HTTP {response.status_code}: {response.text}")
            return []

        data = response.json()
        articles = data.get("articles", []) or data.get("posts", [])

        print(f"[NEWS] Retrieved {len(articles)} articles")
        return articles

    except requests.exceptions.RequestException as e:
        print(f"[NEWS ERROR] Network failure: {e}")
        return []
    except Exception as e:
        print(f"[NEWS ERROR] Unknown failure: {e}")
        return []

# =========================
# CACHED FETCH
# =========================

def get_news(category: str):
    """Cached news fetcher"""

    current_time = time.time()

    if (
        NEWS_CACHE["data"] is not None and
        NEWS_CACHE["category"] == category and
        current_time - NEWS_CACHE["timestamp"] < CACHE_DURATION
    ):
        return NEWS_CACHE["data"]

    articles = fetch_news(category)

    NEWS_CACHE["data"] = articles
    NEWS_CACHE["timestamp"] = current_time
    NEWS_CACHE["category"] = category

    return articles

# =========================
# FORMATTING ENGINE
# =========================

def format_headlines(articles, category: str) -> str:
    if not articles:
        return f"Sorry, I couldn't fetch any {category} news right now."

    output = f"Here are the latest {category} headlines:\n\n"

    for i, article in enumerate(articles[:5], 1):
        title = article.get("title", "").strip()
        description = article.get("description", article.get("snippet", "")).strip()
        source = article.get("source", {}).get("name", "Unknown Source")

        if not title:
            continue

        output += f"{i}. {title} ({source})\n"

        if description:
            description = description.replace("\n", " ").strip()
            if len(description) > 160:
                description = description[:157] + "..."
            output += f"   {description}\n"

        output += "\n"

    return output.strip()

def format_summary():
    categories = ["world", "technology", "business", "entertainment"]
    output = "Here’s a quick news roundup:\n\n"

    for cat in categories:
        articles = get_news(cat)
        if articles:
            title = articles[0].get("title", "").strip()
            source = articles[0].get("source", {}).get("name", "Unknown Source")

            if title:
                output += f"• {title} ({source})\n"

    return output.strip()

# =========================
# GEMMA CONTEXT INTERFACE
# =========================

def get_news_context(text: str) -> str:
    category = categorize_news_request(text)

    if category == "summary":
        return format_summary()

    articles = get_news(category)
    return format_headlines(articles, category)

# =========================
# IRIS COMPATIBILITY LAYER
# =========================

def is_news_question(text: str) -> bool:
    keywords = [
        "news", "headlines", "today", "current events",
        "breaking", "updates", "what's happening", "happening",
        "roundup", "summary", "stories", "world", "tech", "business"
    ]
    return any(word in text.lower() for word in keywords)

def handle_news_command(text: str) -> str:
    """IRIS-compatible entrypoint"""
    return get_news_context(text)

# Alias for Gemma routing
handle_news_command_for_gemma = handle_news_command
