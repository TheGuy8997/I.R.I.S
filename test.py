# test.py

from music import play_uri

# Try different track URIs until one works
track_uris = [
    "soundcloud://track/1172913403",
    "soundcloud://track/253166273",
    "soundcloud://track/306453014"
]

for uri in track_uris:
    print(f"[TEST] Trying track: {uri}")
    result = play_uri(uri)
    if result["status"] == "success":
        print("[TEST] SUCCESS!")
        break
    else:
        print(f"[TEST] Failed, trying next...")