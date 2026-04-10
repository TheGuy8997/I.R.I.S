import requests

# =========================
# CONFIG
# =========================

MA_URL = "http://localhost:8095/api"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI3aUg4SkFvV2xETlZTNHUzVWY0SHVDSFA4N2ZOcUFwYVZEWFRlSlZqdjRjIiwianRpIjoiLXBobThvTmlUallWQ1FDbmdXNGV5WXkzZ1Q1bnB6eGM4MGlaYkZNU1lzayIsImlhdCI6MTc3NTc4MjM5NiwiZXhwIjoyMDkxMTQyMzk2LCJ1c2VybmFtZSI6ImlyaXMiLCJyb2xlIjoiYWRtaW4iLCJ0b2tlbl9uYW1lIjoiaXJpcyIsImlzX2xvbmdfbGl2ZWQiOnRydWV9.6z6ji89E4ex3pSVwqH_o7UvzsCkONjxRMX-MV2nMeiw"

PLAYER_ID = "ma_7r40h6sc1k"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# =========================
# CORE REQUEST
# =========================

def ma_request(command, args):
    payload = {
        "message_id": "1",
        "command": command,
        "args": args
    }

    r = requests.post(MA_URL, json=payload, headers=HEADERS, timeout=10)

    try:
        return r.json()
    except Exception:
        print("[MA ERROR]", r.text)
        return None


# =========================
# SEARCH
# =========================

def search_music(query, limit=5):
    res = ma_request("music/search", {
        "search_query": query,
        "limit": limit
    })

    if not res:
        return []

    items = []
    for section in ["tracks", "artists", "albums"]:
        for i in res.get(section, []):
            items.append({
                "name": i.get("name"),
                "artist": ", ".join([a["name"] for a in i.get("artists", [])]) if i.get("artists") else "",
                "uri": i.get("uri"),
                "provider": i.get("provider")
            })

    return items


# =========================
# PLAYBACK
# =========================

def play_media(uri):
    return ma_request("player_queues/play_media", {
        "queue_id": PLAYER_ID,
        "media": uri
    })


def stop():
    return ma_request("player_queues/stop", {
        "queue_id": PLAYER_ID
    })


def pause():
    return ma_request("player_queues/pause", {
        "queue_id": PLAYER_ID
    })


def resume():
    return ma_request("player_queues/resume", {
        "queue_id": PLAYER_ID
    })


def next_track():
    return ma_request("player_queues/next", {
        "queue_id": PLAYER_ID
    })


def previous_track():
    return ma_request("player_queues/previous", {
        "queue_id": PLAYER_ID
    })
