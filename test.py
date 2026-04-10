import music

print("Testing search...")

tracks = music.search_track("drake")

print("\nSearch results:")
for t in tracks:
    print(t)

if tracks:
    print("\nTesting play...")
    music.play_uri(tracks[0]["uri"])
