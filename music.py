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
# CORE REQUEST HELPER
# =========================

def ma_request(command, args=None):
    """Safe wrapper for Music Assistant API calls."""
    payload = {
        "command": command,
        "args": args or {}
    }

    try:
        resp = requests.post(MA_API, headers=HEADERS, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"[MUSIC ERROR] {e}")
        return None

# =========================
# BASIC PLAYBACK
# =========================

def play_uri(uri):
    """Play a URI directly via Music Assistant queue."""
    print(f"[PLAY] {uri}")
    return ma_request("player_queues/play", {
        "queue_id": QUEUE_ID,
        "uri": uri
    })


def pause():
    return ma_request("player/play_pause", {
        "queue_id": QUEUE_ID,
        "state": "pause"
    })


def resume():
    return ma_request("player/play_pause", {
        "queue_id": QUEUE_ID,
        "state": "play"
    })


def skip():
    return ma_request("player_queues/next", {
        "queue_id": QUEUE_ID
    })

# =========================
# SEARCH
# =========================

def search_track(query, limit=5):
    data = ma_request("music/search", {
        "search_query": query
    })

    if not data:
        return []

    result = data.get("result", {})
    tracks = []

    for item in result.get("tracks", []):
        tracks.append({
            "name": item.get("name"),
            "artist": ", ".join([a["name"] for a in item.get("artists", [])]),
            "uri": item.get("uri")
        })

    return tracks[:limit]

# =========================
# STREAM INTELLIGENCE LAYER (NEW)
# =========================

def inspect_track(track):
    """Lightweight metadata inspector."""
    return {
        "name": track.get("name"),
        "uri": track.get("uri"),
        "ready": track.get("uri") is not None
    }


def play_track(query):
    """Search and play best match."""
    tracks = search_track(query)

    if not tracks:
        print("[MUSIC] No results")
        return None

    track = tracks[0]
    print("[MUSIC] Selected:", inspect_track(track))

    return play_uri(track["uri"])


def play_track_async(query):
    """Future-safe async-style wrapper (non-blocking placeholder)."""
    return play_track(query)

# =========================
# QUEUE / STATUS
# =========================

def get_queue():
    return ma_request("player_queues/items", {
        "queue_id": QUEUE_ID
    })


def get_status():
    return ma_request("player/state", {
        "queue_id": QUEUE_ID
    })
