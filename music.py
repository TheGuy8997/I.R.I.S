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
    """Play a URI using the active Music Assistant queue."""
    print(f"[PLAY] {uri}")

    return ma_request("player_queues/play", {
        "uri": uri
    })


def pause():
    return ma_request("player/play_pause", {
        "state": "pause"
    })


def resume():
    return ma_request("player/play_pause", {
        "state": "play"
    })


def skip():
    return ma_request("player_queues/next", {})

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
# STREAM INTELLIGENCE LAYER
# =========================

def inspect_track(track):
    return {
        "name": track.get("name"),
        "uri": track.get("uri"),
        "ready": track.get("uri") is not None
    }


def play_track(query):
    tracks = search_track(query)

    if not tracks:
        print("[MUSIC] No results")
        return None

    track = tracks[0]
    print("[MUSIC] Selected:", inspect_track(track))

    return play_uri(track["uri"])


def play_track_async(query):
    return play_track(query)
