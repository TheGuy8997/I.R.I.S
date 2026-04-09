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
    from news import handle_news_command, is_news_question
    NEWS_ENABLED = True
except Exception:
    NEWS_ENABLED = False

# =========================
# CONFIG
# =========================
VOSK_MODEL_PATH = "models/vosk"
WAKE_WORD = "iris"

MIC_DEVICE_INDEX = None
MIC_SR = 48000
VOSK_SR = 16000

BLOCKSIZE = 4800
CHANNELS = 1
DTYPE = "int16"

PIPER_VOICE = "en_US-ryan-medium.onnx"
APLAY_DEVICE = "USB2.0 Device"
PIPER_SR = 22050

MIN_TEXT_LEN = 3
FINAL_COOLDOWN = 0.5

# =========================
# MEMORY
# =========================
conversation_history = []
MAX_HISTORY = 6

LAST_INTERACTION_TIME = 0
CONVO_TIMEOUT = 10

# =========================
# VAD
# =========================
INTERRUPT_VOLUME_THRESHOLD = 600
VAD_SMOOTHING = 3
vad_counter = 0

# =========================
# THREAD SAFETY
# =========================
audio_lock = threading.Lock()

# =========================
# TEXT UTILS
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
voice = None
try:
    voice = PiperVoice.load(PIPER_VOICE)
except Exception as e:
    print("[IRIS] Piper load failed:", e)

current_audio_process = None
stop_speaking_flag = False

def stop_speaking():
    global current_audio_process, stop_speaking_flag
    with audio_lock:
        stop_speaking_flag = True
        if current_audio_process:
            try:
                current_audio_process.terminate()
            except Exception:
                pass
            current_audio_process = None

def play_chunk_process(pcm_bytes, proc):
    try:
        if proc.stdin:
            proc.stdin.write(pcm_bytes)
    except Exception:
        pass

def speak(text):
    global stop_speaking_flag, current_audio_process

    with audio_lock:
        stop_speaking_flag = False

    if not voice:
        print("[IRIS] No TTS voice loaded.")
        return

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

            with audio_lock:
                current_audio_process = proc

            for chunk in voice.synthesize(sentence):
                if stop_speaking_flag:
                    break
                play_chunk_process(chunk.audio_int16_bytes, proc)

            if proc.stdin:
                proc.stdin.close()
            proc.wait(timeout=2)

        except Exception:
            pass

# =========================
# PROMPT BUILDER
# =========================
def build_prompt(user_text):
    conversation_history.append({"role": "user", "content": user_text})

    # FIXED slicing
    conversation_history[:] = conversation_history[-MAX_HISTORY:]

    convo = ""
    for msg in conversation_history:
        role = "User" if msg["role"] == "user" else "IRIS"
        convo += f"{role}: {msg['content']}\n"

    return f"""
You are IRIS, a smart home assistant.
Keep responses short and natural.

Conversation:
{convo}

IRIS:
"""

# =========================
# COMMAND HANDLER
# =========================
def handle_command(text):
    global LAST_INTERACTION_TIME

    print("[IRIS] → Processing:", text)

    if NEWS_ENABLED and is_news_question(text):
        raw_news = handle_news_command(text)
        if raw_news:
            speak(raw_news)
            return

    prompt = text

    if WEATHER_ENABLED and is_weather_question(text):
        try:
            prompt = f"Context: {get_weather_context()}\n\nQuestion: {text}"
        except Exception:
            pass

    full_prompt = build_prompt(prompt)

    try:
        resp = ollama.generate(
            model="iris",
            prompt=full_prompt,
            options={"keep_alive": -1}
        )
    except Exception:
        speak("Sorry, I had trouble responding.")
        return

    raw = resp.get("response", "")

    conversation_history.append({"role": "assistant", "content": raw})

    _, cleaned = extract_actions(raw)
    tts_text = clean_for_tts(cleaned)

    if tts_text:
        speak(tts_text)

# =========================
# AUDIO INPUT
# =========================
audio_q = queue.Queue(maxsize=20)
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

    try:
        audio_q.put_nowait(bytes(indata))
    except queue.Full:
        pass

def process_audio():
    global awake, last_final_time, LAST_INTERACTION_TIME

    while True:
        data = audio_q.get()

        pcm48 = np.frombuffer(data, dtype=np.int16)

        # FIXED resampling
        pcm16 = resample_poly(pcm48, 16000, 48000).astype(np.int16)

        if recognizer.AcceptWaveform(pcm16.tobytes()):
            result = json.loads(recognizer.Result())
            text = result.get("text", "").strip()

            now = time.time()

            if not text or len(text) < MIN_TEXT_LEN:
                continue

            last_final_time = now
            print("[VOSK]:", text)

            if not awake:
                if WAKE_WORD in text.lower():
                    awake = True
                    LAST_INTERACTION_TIME = now
                    speak("Hello")
                continue

            # FIXED timeout handling
            LAST_INTERACTION_TIME = now

            if time.time() - LAST_INTERACTION_TIME < CONVO_TIMEOUT:
                handle_command(text)
            else:
                awake = False

# =========================
# CLI LOOP
# =========================
def cli_loop():
    while True:
        try:
            text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)

        if text:
            handle_command(text)

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
