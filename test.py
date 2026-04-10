from music import search_music, play_media, stop, resume

def main():
    print("\n🎧 === IRIS MUSIC TEST ===\n")

    query = input("🔎 Search music: ")

    print("\n[TEST] Searching...\n")
    results = search_music(query)

    if not results:
        print("❌ No results found")
        return

    print("\n✅ Results:\n")
    for i, r in enumerate(results):
        print(f"{i}. {r['name']} - {r.get('artist','')}")

    choice = input("\n🎯 Pick index (ENTER = 0): ").strip()
    idx = int(choice) if choice.isdigit() else 0

    track = results[idx]

    print("\n🎵 Playing:\n", track)

    res = play_media(track["uri"])
    print("\n[PLAY RESPONSE]", res)

    while True:
        cmd = input("\n(stop / pause / resume / next / quit): ").strip().lower()

        if cmd == "stop":
            print(stop())
        elif cmd == "pause":
            print(stop())
        elif cmd == "resume":
            print(resume())
        elif cmd == "next":
            print(next_track())
        elif cmd == "quit":
            break


if __name__ == "__main__":
    main()
