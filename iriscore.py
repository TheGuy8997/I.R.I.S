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
except ImportError:
    WEATHER_ENABLED = False

# =========================
# NEWS INTEGRATION
# =========================
try:
    from news import (
        handle_news_command,
        is_news_question,
        categorize_news_request,
        get_news_context
    )
    NEWS_ENABLED = True
except Exception:
    NEWS_ENABLED = False

# =========================
# CONFIG
# =========================
VOSK_MODEL_PATH = "models/vosk"
WAKE_WORD = "iris"

MIC_DEVICE_INDEX = "ZTD39 Device"
MIC_SR = 48000
VOSK_SR = 16000

BLOCKSIZE = 4800
CHANNELS = 1
DTYPE = "int16"

PIPER_VOICE = "en_US-ryan-medium.onnx"
APLAY_DEVICE = ""
PIPER_SR = 22050

MIN_TEXT_LEN = 3
FINAL_COOLDOWN = 0.5
CONVO_TIMEOUT = 10

# =========================
# MEMORY (CHAT STYLE)
# =========================
conversation_history = []
MAX_HISTORY = 8

LAST_INTERACTION_TIME = 0

# =========================
# VAD
# =========================
INTERRUPT_VOLUME_THRESHOLD = 600
VAD_SMOOTHING = 3
vad_counter = 0

# =========================
# TEXT UTILS
# =========================

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
voice = PiperVoice.load(PIPER_VOICE)
current_audio_process = None
stop_speaking_flag = False


def stop_speaking():
    global current_audio_process, stop_speaking_flag
    stop_speaking_flag = True
    if current_audio_process:
        try:
            current_audio_process.kill()
        except Exception:
            pass
        current_audio_process = None


def speak(text):
    global stop_speaking_flag, current_audio_process

    stop_speaking_flag = False

    for sentence in split_sentences(text):
        if stop_speaking_flag:
            break

        print("I.R.I.S.:", sentence)

        try:
            proc = subprocess.Popen(
                ["aplay",
                 "-D", APLAY_DEVICE,
                 "-r", str(PIPER_SR),
                 "-f", "S16_LE",
                 "-c", "1",
                 "-t", "raw",
                 "--quiet"],
                stdin=subprocess.PIPE
            )

            current_audio_process = proc

            for chunk in voice.synthesize(sentence):
                if stop_speaking_flag:
                    break
                proc.stdin.write(chunk.audio_int16_bytes)

            if proc.stdin:
                proc.stdin.close()
            proc.wait(timeout=2)

        except Exception:
            pass

# =========================
# NEWS HANDLER
# =========================

def handle_news(text):
    category = categorize_news_request(text)
    news_text = get_news_context(text)

    if category == "summary":
        prompt = f"Summarize this news in 1–2 short spoken sentences:\n\n{news_text}"
    else:
        prompt = f"Convert this news into a short spoken briefing. Do not read formatting:\n\n{news_text}"

    try:
        resp = ollama.generate(
            model="iris",
            prompt=prompt,
            options={"keep_alive": -1}
        )
        speak(resp.get("response", ""))
    except Exception:
        speak("News is currently unavailable.")

# =========================
# COMMAND HANDLER (CHAT STYLE MEMORY)
# =========================

def handle_command(text):
    global LAST_INTERACTION_TIME

    print("[IRIS] → Processing:", text)

    # NEWS
    if NEWS_ENABLED and is_news_question(text):
        handle_news(text)
        return

    # WEATHER (inject context only)
    if WEATHER_ENABLED and is_weather_question(text):
        try:
            text = f"Context: {get_weather_context()}\nUser: {text}"
        except Exception:
            pass

    # =========================
    # CHAT STYLE MEMORY (NO MANUAL PROMPT BUILDING)
    # =========================

    conversation_history.append({"role": "user", "content": text})
    conversation_history[:] = conversation_history[-MAX_HISTORY:]

    try:
        resp = ollama.chat(
            model="iris",
            messages=conversation_history,
            options={"keep_alive": -1}
        )
    except Exception:
        speak("Sorry, I had trouble responding.")
        return

    reply = resp.get("message", {}).get("content", "")

    conversation_history.append({"role": "assistant", "content": reply})

    tts_text = clean_for_tts(reply)
    if tts_text:
        speak(tts_text)

# =========================
# AUDIO INPUT
# =========================
audio_q = queue.Queue()
awake = False
last_final_time = 0

vosk_model = Model(VOSK_MODEL_PATH)
recognizer = KaldiRecognizer(vosk_model, VOSK_SR)
recognizer.SetWords(True)


def audio_callback(indata, frames, time_info, status):
    global vad_counter, awake

    audio_np = np.frombuffer(indata, dtype=np.int16)
    volume = np.mean(np.abs(audio_np))

    vad_counter = vad_counter + 1 if volume > INTERRUPT_VOLUME_THRESHOLD else 0

    if awake and vad_counter >= VAD_SMOOTHING:
        stop_speaking()

    audio_q.put(bytes(indata))


def process_audio():
    global awake, last_final_time, LAST_INTERACTION_TIME

    while True:
        data = audio_q.get()

        pcm48 = np.frombuffer(data, dtype=np.int16)
        pcm16 = resample_poly(pcm48, 16000, 48000).astype(np.int16)

        if recognizer.AcceptWaveform(pcm16.tobytes()):
            result = json.loads(recognizer.Result())
            text = result.get("text", "").strip()

            now = time.time()

            if not text or len(text) < MIN_TEXT_LEN:
                continue

            if not awake:
                if WAKE_WORD in text.lower():
                    awake = True
                    LAST_INTERACTION_TIME = now
                    speak("Hello")
                continue

            LAST_INTERACTION_TIME = now

            handle_command(text)

            # ALWAYS RETURN TO WAKE STATE AFTER RESPONSE
            awake = False

# =========================
# CLI
# =========================

def cli_loop():
    while True:
        try:
            text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)

        if text:
            handle_command(text)
            awake = False

# =========================
# MAIN
# =========================

def main():
    print("[IRIS] Starting... Say 'iris' to wake.")

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
