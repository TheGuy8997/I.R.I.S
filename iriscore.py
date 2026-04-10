#!/usr/bin/env python3
import queue
import json
import time
import re
import threading
import sys
import subprocess
import numpy as np
from scipy.signal import resample_poly
import sounddevice as sd
from vosk import Model, KaldiRecognizer
import ollama
from piper import PiperVoice

# =========================
# WEATHER INTEGRATION
# =========================
try:
    from weather import get_weather_context, is_weather_question
    WEATHER_ENABLED = True
    print("[IRIS] Weather features enabled")
except ImportError:
    WEATHER_ENABLED = False
    print("[WARNING] Weather module not found, weather features disabled")

# =========================
# NEWS INTEGRATION
# =========================
try:
    from news import (
        handle_news_command,
        handle_news_command_for_gemma,
        is_news_question
    )
    NEWS_ENABLED = True
    print("[IRIS] News features enabled")
except Exception as e:
    NEWS_ENABLED = False
    print("[WARNING] News module not found or failed to load, news features disabled")
    print("[NEWS ERROR] Exception during import:", repr(e))

# =========================
# MUSIC INTEGRATION (NEW)
# =========================
try:
    import music
    MUSIC_ENABLED = True
    print("[IRIS] Music features enabled")
except Exception as e:
    MUSIC_ENABLED = False
    print("[WARNING] Music module not found or failed to load, music features disabled")
    print("[MUSIC ERROR]", repr(e))

MUSIC_PLAYER_ID = "ma_7r40h6sc1k"

# =========================
# CONFIG
# =========================
VOSK_MODEL_PATH = "models/vosk"
WAKE_WORD = "iris"

MIC_DEVICE_INDEX = "ZTD39 Device"
MIC_SR = 48000
VOSK_SR = 16000

BLOCKSIZE = 9600
CHANNELS = 1
DTYPE = "int16"

PIPER_VOICE = "en_US-ryan-medium.onnx"
APLAY_DEVICE = "plughw:CARD=Device,DEV=0"
PIPER_SR = 22050

MIN_TEXT_LEN = 3
FINAL_COOLDOWN = 1.0

# =========================
# CONVERSATION CALLBACKS
# =========================
conversation_callbacks = []

def register_conversation_callback(func):
    conversation_callbacks.append(func)

def run_conversation_callbacks(role, text):
    for cb in conversation_callbacks:
        try:
            cb(role, text)
        except Exception as e:
            print("[IRIS callback error]", e)

# =========================
# TEXT / ACTION UTILS
# =========================
ACTION_PATTERN = re.compile(r'\{action:\s*(\{.*?\})\s*\}', re.DOTALL)

def extract_actions(text):
    actions = []

    def repl(match):
        try:
            actions.append(json.loads(match.group(1)))
        except Exception:
            actions.append({"error": "invalid_action"})
        return ""

    clean = ACTION_PATTERN.sub(repl, text)
    return actions, clean.strip()

def clean_for_tts(text):
    text = text.replace("*", "").replace(":", "")
    text = re.sub(r"[^\x00-\x7F]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def split_sentences(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]

# =========================
# AUDIO OUTPUT
# =========================
def play_pcm(pcm_bytes):
    p = subprocess.Popen(
        [
            "aplay",
            "-D", APLAY_DEVICE,
            "-r", str(PIPER_SR),
            "-f", "S16_LE",
            "-c", "1",
            "-t", "raw",
            "--quiet"
        ],
        stdin=subprocess.PIPE
    )
    p.stdin.write(pcm_bytes)
    p.stdin.close()
    p.wait()

def speak(text):
    for sentence in split_sentences(text):
        print("I.R.I.S.:", sentence)
        voice = PiperVoice.load(PIPER_VOICE)
        for chunk in voice.synthesize(sentence):
            play_pcm(chunk.audio_int16_bytes)

# =========================
# MUSIC HANDLER (UPDATED FOR NEW music.py)
# =========================

def extract_music_intent(text: str):
    text = text.lower()

    if "stop music" in text or text.strip() == "stop":
        return "stop"
    if "pause" in text:
        return "pause"
    if "resume" in text or "start music" in text:
        return "resume"
    if "next" in text or "skip" in text:
        return "next"
    if "previous" in text or "back" in text:
        return "previous"
    if "play" in text:
        return "play"

    return None


def handle_music_command(text):
    intent = extract_music_intent(text)
    if not intent:
        return False

    # =========================
    # PLAY (SEARCH → PLAY MEDIA)
    # =========================
    if intent == "play":
        query = text.lower().replace("play", "").strip()

        if not query:
            query = "music"

        results = music.search_music(query)

        if not results:
            speak("I couldn't find that music.")
            return True

        track = results[0]

        try:
            music.play_media(track["uri"])   # 🔥 UPDATED (NOT play_uri)
            speak(f"Playing {track['name']}")
        except Exception as e:
            print("[MUSIC ERROR]", e)
            speak("Music failed to play.")

        return True

    # =========================
    # STOP
    # =========================
    if intent == "stop":
        try:
            music.stop()
            speak("Music stopped")
        except Exception as e:
            print("[MUSIC ERROR]", e)
        return True

    # =========================
    # PAUSE
    # =========================
    if intent == "pause":
        try:
            music.pause()
            speak("Paused")
        except Exception as e:
            print("[MUSIC ERROR]", e)
        return True

    # =========================
    # RESUME
    # =========================
    if intent == "resume":
        try:
            music.resume()
            speak("Resuming music")
        except Exception as e:
            print("[MUSIC ERROR]", e)
        return True

    # =========================
    # NEXT
    # =========================
    if intent == "next":
        try:
            music.next_track()
        except Exception as e:
            print("[MUSIC ERROR]", e)
        return True

    # =========================
    # PREVIOUS
    # =========================
    if intent == "previous":
        try:
            music.previous_track()
        except Exception as e:
            print("[MUSIC ERROR]", e)
        return True

    return False

# =========================
# COMMAND HANDLER
# =========================
def handle_command(text):
    print("[IRIS] → Processing:", text)
    run_conversation_callbacks("user", text)

    # MUSIC FIRST (IMPORTANT)
    if handle_music_command(text):
        return

    # NEWS
    if NEWS_ENABLED and is_news_question(text):
        raw_news = handle_news_command(text)

        if raw_news and not raw_news.startswith("Sorry"):
            prompt = f"""
You are IRIS.

Here are news headlines:
{raw_news}

Explain simply and conversationally.
"""
            try:
                resp = ollama.generate(model="iris", prompt=prompt)
                raw = resp.get("response", "")
            except Exception:
                speak(raw_news)
                return

            tts_text = clean_for_tts(raw)

            if tts_text:
                speak(tts_text)
                run_conversation_callbacks("assistant", tts_text)
            return

    # WEATHER / NORMAL LLM
    prompt = text

    if WEATHER_ENABLED and is_weather_question(text):
        try:
            prompt = f"Context: {get_weather_context()}\n\nQuestion: {text}"
        except:
            pass

    try:
        resp = ollama.generate(model="iris", prompt=prompt)
    except:
        speak("Sorry, I had trouble responding.")
        return

    raw = resp.get("response", "")
    tts_text = clean_for_tts(raw)

    if tts_text:
        speak(tts_text)
        run_conversation_callbacks("assistant", tts_text)

# =========================
# AUDIO PROCESSING
# =========================
audio_q = queue.Queue()
awake = False
last_final_time = 0

vosk_model = Model(VOSK_MODEL_PATH)
recognizer = KaldiRecognizer(vosk_model, VOSK_SR)
recognizer.SetWords(True)

def audio_callback(indata, frames, time_info, status):
    if status:
        print("[sd status]", status, file=sys.stderr)
    audio_q.put(bytes(indata))

def process_audio():
    global awake, last_final_time

    while True:
        data = audio_q.get()

        pcm48 = np.frombuffer(data, dtype=np.int16)
        pcm16 = resample_poly(pcm48, 1, 3).astype(np.int16)

        if recognizer.AcceptWaveform(pcm16.tobytes()):
            result = json.loads(recognizer.Result())
            text = result.get("text", "").strip()

            now = time.time()

            if (
                not text
                or len(text) < MIN_TEXT_LEN
                or now - last_final_time < FINAL_COOLDOWN
            ):
                continue

            last_final_time = now
            print("[VOSK final]:", text)

            if not awake:
                if WAKE_WORD in text:
                    awake = True
                    speak("Hello!")
                continue

            handle_command(text)
            awake = False

# =========================
# MAIN
# =========================
def main():
    print("[IRIS] Initializing...")
    print("[IRIS] Listening... Say 'iris'")

    threading.Thread(target=process_audio, daemon=True).start()

    with sd.RawInputStream(
        samplerate=MIC_SR,
        blocksize=BLOCKSIZE,
        device=MIC_DEVICE_INDEX,
        dtype=DTYPE,
        channels=CHANNELS,
        callback=audio_callback
    ):
        while True:
            time.sleep(0.1)

if __name__ == "__main__":
    main()
