# music.py

import requests
import json

# =========================
# CONFIGURATION
# =========================

MA_API = "http://localhost:8095/api"
TOKEN = "rNcJ2T9xqubO9UJ1PqnAPaspxHHRwwflmwOAk2LPYXvnIdMGcCGeXGZZkDOBCmih"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

QUEUE_ID = "ma_ghhsuopngx"


# =========================
# MUSIC FUNCTIONS (Ultra Minimal)
# =========================

def play_uri(uri):
    """Play a URI directly - no queue management."""
    print(f"[PLAY] Playing: {uri}")
    
    # Single direct play command
    payload = {
        "command": "player_queues/play",
        "args": {
            "queue_id": QUEUE_ID,
            "uri": uri
        }
    }
    
    resp = requests.post(MA_API, headers=HEADERS, json=payload)
    if resp.status_code == 200:
        print("[SUCCESS] Playback started!")
        return {"status": "success"}
    else:
        print(f"[ERROR] Failed: {resp.text}")
        return {"status": "error", "message": resp.text}


def search_track(query, limit=5):
    """Search for tracks using REST API."""
    payload = {
        "command": "music/search",
        "args": {
            "search_query": query
        }
    }

    resp = requests.post(MA_API, headers=HEADERS, json=payload)
    resp.raise_for_status()
    result = resp.json().get("result", {})

    tracks = []
    for item in result.get("tracks", []):
        tracks.append({
            "name": item.get("name"),
            "artist": ", ".join([a["name"] for a in item.get("artists", [])]),
            "uri": item.get("uri")
        })
    return tracks[:limit]