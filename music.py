import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any

from music_assistant_client import MusicAssistantClient


MA_URL = os.getenv("MUSIC_ASSISTANT_URL", "http://localhost:8095").rstrip("/")
MA_TOKEN = os.getenv("MUSIC_ASSISTANT_TOKEN", "").strip()
PLAYER_ID = os.getenv("MUSIC_ASSISTANT_PLAYER_ID", "").strip()
REQUEST_TIMEOUT = 15
SEARCH_LIMIT = 10


def _validate_config(require_player: bool = True):
    missing = []
    if not MA_TOKEN:
        missing.append("MUSIC_ASSISTANT_TOKEN")
    if require_player and not PLAYER_ID:
        missing.append("MUSIC_ASSISTANT_PLAYER_ID")
    if missing:
        raise RuntimeError(
            "Music Assistant is not configured; set " + " and ".join(missing) + " in .env"
        )


async def _with_client(
    operation: Callable[[MusicAssistantClient], Awaitable[Any]],
    require_player: bool = True,
) -> Any:
    _validate_config(require_player=require_player)
    client = MusicAssistantClient(MA_URL, None, token=MA_TOKEN)
    try:
        await asyncio.wait_for(client.connect(), timeout=REQUEST_TIMEOUT)
        return await asyncio.wait_for(operation(client), timeout=REQUEST_TIMEOUT)
    finally:
        await client.disconnect()


def _run(
    operation: Callable[[MusicAssistantClient], Awaitable[Any]],
    require_player: bool = True,
) -> Any:
    return asyncio.run(_with_client(operation, require_player=require_player))


def _normalize_results(response: Any) -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        raise RuntimeError("Music Assistant returned an unexpected search response")

    items = []
    for media_type in ("tracks", "artists", "albums", "playlists", "radio"):
        results = response.get(media_type, [])
        if not isinstance(results, list):
            continue
        for item in results:
            if not isinstance(item, dict) or not item.get("uri"):
                continue
            artists = item.get("artists") or []
            items.append({
                "name": item.get("name") or "Unknown title",
                "artist": ", ".join(
                    artist.get("name", "")
                    for artist in artists
                    if isinstance(artist, dict) and artist.get("name")
                ),
                "uri": item["uri"],
                "provider": item.get("provider"),
                "type": media_type[:-1] if media_type.endswith("s") else media_type,
            })
    return items


async def _search(client: MusicAssistantClient, query: str, limit: int):
    response = await client.send_command(
        "music/search",
        search_query=query,
        media_types=["track", "artist", "album", "playlist", "radio"],
        limit=limit,
    )
    return _normalize_results(response)


def search_music(query: str, limit: int = SEARCH_LIMIT) -> list[dict[str, Any]]:
    query = query.strip()
    if not query:
        return []
    if limit < 1:
        raise ValueError("limit must be at least 1")
    return _run(lambda client: _search(client, query, limit))


def play_media(uri: str):
    if not uri.strip():
        raise ValueError("A Music Assistant media URI is required")
    return _run(
        lambda client: client.player_queues.play_media(
            queue_id=PLAYER_ID,
            media=uri,
        )
    )


def play_query(query: str) -> dict[str, Any] | None:
    query = query.strip()
    if not query:
        query = "music"

    async def operation(client: MusicAssistantClient):
        results = await _search(client, query, SEARCH_LIMIT)
        if not results:
            return None
        selected = results[0]
        await client.player_queues.play_media(
            queue_id=PLAYER_ID,
            media=selected["uri"],
        )
        return selected

    return _run(operation)


def _queue_command(method_name: str):
    async def operation(client: MusicAssistantClient):
        method = getattr(client.player_queues, method_name)
        return await method(PLAYER_ID)

    return _run(operation)


def stop():
    return _queue_command("stop")


def pause():
    return _queue_command("pause")


def resume():
    return _queue_command("resume")


def next_track():
    return _queue_command("next")


def previous_track():
    return _queue_command("previous")


def list_players() -> list[dict[str, Any]]:
    async def operation(client: MusicAssistantClient):
        players = await client.send_command("players/all")
        if not isinstance(players, list):
            raise RuntimeError("Music Assistant returned an unexpected player list")
        return [
            {
                "player_id": player.get("player_id"),
                "name": player.get("name"),
                "available": player.get("available"),
            }
            for player in players
            if isinstance(player, dict)
        ]

    return _run(lambda client: operation(client), require_player=False)


if __name__ == "__main__":
    for player in list_players():
        print(
            f"{player['player_id']}  {player['name']}"
            + ("" if player["available"] else " (unavailable)")
        )
