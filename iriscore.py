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
APLAY_DEVICE = " USB2.0 Device"
PIPER_SR = 22050
MIN_TEXT_LEN = 3
FINAL_COOLDOWN = 1.0

# =========================
# MUSIC FUNCTIONS
# =========================
def handle_music_command(text):
    return False

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
        ["aplay",
         "-D", APLAY_DEVICE,
         "-r", str(PIPER_SR),
         "-f", "S16_LE",
         "-c", "1",
         "-t", "raw",
         "--quiet"],
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
# COMMAND HANDLER
# =========================
def handle_command(text):
    print("[IRIS] → Processing:", text)

    if handle_music_command(text):
        return

    # 🔹 NEWS → GEMMA EXPLANATION PIPELINE
    if NEWS_ENABLED and is_news_question(text):
        raw_news = handle_news_command(text)

        if raw_news and not raw_news.startswith("Sorry"):
            print("[IRIS] → Sending news to Gemma for explanation")

            prompt = f"""
You are IRIS, a friendly home voice assistant.

Here are today's news headlines:

{raw_news}

Please explain this news in a natural, conversational, and easy-to-understand way.
Summarize clearly and avoid sounding robotic.
"""

            try:
                print("[IRIS] → Routing to Gemma")
                resp = ollama.generate(model="iris", prompt=prompt)
                raw = resp.get("response", "")
            except Exception as e:
                print("[IRIS ERROR] Ollama failed:", e)
                speak(raw_news)
                return

            actions, cleaned = extract_actions(raw)
            tts_text = clean_for_tts(cleaned)

            if tts_text:
                speak(tts_text)
            return

    # WEATHER → GEMMA
    prompt = text
    if WEATHER_ENABLED and is_weather_question(text):
        weather_context = get_weather_context()
        prompt = f"Context: {weather_context}\n\nQuestion: {text}\nPlease provide a helpful, conversational response about the weather."

    try:
        resp = ollama.generate(model="iris", prompt=prompt)
    except Exception as e:
        print("[IRIS ERROR] Ollama failed:", e)
        return

    raw = resp.get("response", "")
    actions, cleaned = extract_actions(raw)
    tts_text = clean_for_tts(cleaned)

    if tts_text:
        speak(tts_text)

    if actions:
        print("[IRIS actions]")
        print(json.dumps(actions, indent=2))

# =========================
# AUDIO PROCESSING
# =========================
audio_q = queue.Queue()
awake = False
last_final_time = 0

vosk_model = Model(VOSK_MODEL_PATH)
recognizer = KaldiRecognizer(vosk_model, VOSK_SR)
recognizer.SetWords(True)

device_info = sd.query_devices(MIC_DEVICE_INDEX)
print(f"[IRIS] Using input device {MIC_DEVICE_INDEX}:",
      device_info["name"], f"(sr={MIC_SR})")

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
            recognizer.Reset()
            now = time.time()

            if (
                not text
                or len(text) < MIN_TEXT_LEN
                or text in ("the", "uh", "um", "by", "that")
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
# CLI LOOP
# =========================
def cli_loop():
    while True:
        try:
            text = input("You (text): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[IRIS] Exiting cleanly.")
            sys.exit(0)

        if text:
            handle_command(text)

# =========================
# MAIN
# =========================
def main():
    print("[IRIS] Initializing...")
    print("[IRIS] Listening... Say 'iris'")
    print("Type text commands anytime.\n")

    threading.Thread(target=process_audio, daemon=True).start()

    with sd.RawInputStream(
        samplerate=MIC_SR,
        blocksize=BLOCKSIZE,
        device=MIC_DEVICE_INDEX,
        dtype=DTYPE,
        channels=CHANNELS,
        callback=audio_callback
    ):
        cli_loop()

if __name__ == "__main__":
    main()
