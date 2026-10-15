#!/usr/bin/env python3
import queue
import json
import os
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
# MUSIC INTEGRATION 
# =========================
try:
    import music
    MUSIC_ENABLED = True
    print("[IRIS] Music features enabled")
except Exception as e:
    MUSIC_ENABLED = False
    print("[WARNING] Music module not found or failed to load, music features disabled")
    print("[MUSIC ERROR]", repr(e))

# =========================
# CONFIG
# =========================
VOSK_MODEL_PATH = os.getenv("IRIS_VOSK_MODEL_PATH", "models/vosk")
WAKE_WORD = os.getenv("IRIS_WAKE_WORD", "iris").strip().lower()

MIC_DEVICE_INDEX = os.getenv("IRIS_MIC_DEVICE", "ZTD39 Device")
MIC_SR = int(os.getenv("IRIS_MIC_SAMPLE_RATE", "48000"))
VOSK_SR = 16000

BLOCKSIZE = int(os.getenv("IRIS_AUDIO_BLOCKSIZE", "9600"))
CHANNELS = 1
DTYPE = "int16"
WAKE_GRAMMAR = json.dumps([WAKE_WORD, "[unk]"])

PIPER_VOICE = os.getenv("IRIS_PIPER_VOICE", "en_US-ryan-medium.onnx")
APLAY_DEVICE = os.getenv("IRIS_ALSA_DEVICE", "plughw:CARD=Device,DEV=0")
PIPER_SR = int(os.getenv("IRIS_PIPER_SAMPLE_RATE", "22050"))
OLLAMA_MODEL = os.getenv("IRIS_OLLAMA_MODEL", "iris")
OLLAMA_KEEP_ALIVE = os.getenv("IRIS_OLLAMA_KEEP_ALIVE", "10m")

MIN_TEXT_LEN = 3
FINAL_COOLDOWN = 1.0

# =========================
# CONVERSATION CALLBACKS
# =========================
conversation_callbacks = []
piper_voice = None
conversation_history = []
MAX_HISTORY_TURNS = 3
MAX_HISTORY_TEXT = 600

def register_conversation_callback(func):
    conversation_callbacks.append(func)

def run_conversation_callbacks(role, text):
    for cb in conversation_callbacks:
        try:
            cb(role, text)
        except Exception as e:
            print("[IRIS callback error]", e)

def remember_turn(user_text, assistant_text):
    conversation_history.append((
        user_text[-MAX_HISTORY_TEXT:],
        assistant_text[-MAX_HISTORY_TEXT:],
    ))
    del conversation_history[:-MAX_HISTORY_TURNS]

def add_conversation_context(prompt):
    if not conversation_history:
        return prompt

    history = ["Recent conversation, for understanding follow-up questions:"]
    for user_text, assistant_text in conversation_history:
        history.append(f"User: {user_text}")
        history.append(f"IRIS: {assistant_text}")
    history.append(f"Current request: {prompt}")
    return "\n".join(history)

def respond_to_turn(user_text, assistant_text):
    remember_turn(user_text, assistant_text)
    speak(assistant_text)
    run_conversation_callbacks("assistant", assistant_text)

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
    global piper_voice

    if piper_voice is None:
        piper_voice = PiperVoice.load(PIPER_VOICE)

    for sentence in split_sentences(text):
        print("I.R.I.S.:", sentence)
        pcm_bytes = b"".join(
            chunk.audio_int16_bytes for chunk in piper_voice.synthesize(sentence)
        )
        if pcm_bytes:
            play_pcm(pcm_bytes)

# =========================
# MUSIC HANDLER
# =========================

def extract_music_intent(text: str):
    normalized = re.sub(r"[^\w\s']", " ", text.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()

    commands = (
        ("stop", r"^(?:stop|stop music|stop playing)(?:\s+music)?$"),
        ("pause", r"^(?:pause|pause music|hold on)(?:\s+the music)?$"),
        ("resume", r"^(?:resume|resume music|continue|unpause)(?:\s+music)?$"),
        ("next", r"^(?:next|next track|skip|skip this)(?:\s+(?:track|song|this track|this song))?$"),
        ("previous", r"^(?:previous|previous track|back|go back)(?:\s+(?:track|song))?$"),
    )
    for intent, pattern in commands:
        if re.fullmatch(pattern, normalized):
            return intent, ""

    play_match = re.match(
        r"^(?:(?:please|can you|could you|would you)\s+)*(?:play|put on|queue|listen to)\b",
        normalized,
    )
    if play_match:
        query = normalized[play_match.end():].strip()
        query = re.sub(r"^(?:some|the)\s+", "", query)
        return "play", query

    return None, ""


def handle_music_command(text):
    intent, query = extract_music_intent(text)
    if not intent:
        return None

    try:
        if intent == "play":
            selected = music.play_query(query)
            if selected is None:
                return f"I couldn't find {query or 'music'}."
            else:
                title = selected["name"]
                artist = selected.get("artist")
                return f"Playing {title}" + (f" by {artist}" if artist else "")
        else:
            getattr(music, {
                "stop": "stop",
                "pause": "pause",
                "resume": "resume",
                "next": "next_track",
                "previous": "previous_track",
            }[intent])()
            return {
                "stop": "Music stopped.",
                "pause": "Music paused.",
                "resume": "Resuming music.",
                "next": "Skipping to the next track.",
                "previous": "Going back one track.",
            }[intent]
    except Exception as error:
        print(f"[MUSIC ERROR] {error}")
        return "Music Assistant is unavailable. Check its connection and settings."

# =========================
# COMMAND HANDLER
# =========================
def handle_command(text):
    print("[IRIS] → Processing:", text)
    run_conversation_callbacks("user", text)

    # MUSIC FIRST (IMPORTANT)
    music_response = handle_music_command(text)
    if music_response is not None:
        respond_to_turn(text, music_response)
        return

    # NEWS
    if NEWS_ENABLED and is_news_question(text):
        raw_news = handle_news_command(text)

        if raw_news and not raw_news.startswith("Sorry"):
            prompt = add_conversation_context(
                f"Here are news headlines:\n{raw_news}\n\n"
                "Explain them simply and conversationally, using the recent "
                "conversation only to understand the user's request."
            )
            try:
                resp = ollama.generate(
                    model=OLLAMA_MODEL, prompt=prompt, keep_alive=OLLAMA_KEEP_ALIVE
                )
                raw = resp.get("response", "")
            except Exception:
                respond_to_turn(text, raw_news)
                return

            tts_text = clean_for_tts(raw)

            if tts_text:
                respond_to_turn(text, tts_text)
            return

    # WEATHER / NORMAL LLM
    prompt = text

    if WEATHER_ENABLED and is_weather_question(text):
        try:
            prompt = f"Context: {get_weather_context()}\n\nQuestion: {text}"
        except:
            pass

    prompt = add_conversation_context(prompt)
    try:
        resp = ollama.generate(
            model=OLLAMA_MODEL, prompt=prompt, keep_alive=OLLAMA_KEEP_ALIVE
        )
    except Exception as error:
        print("[OLLAMA ERROR]", error)
        respond_to_turn(text, "Sorry, I had trouble responding.")
        return

    raw = resp.get("response", "")
    tts_text = clean_for_tts(raw)

    if tts_text:
        respond_to_turn(text, tts_text)

# =========================
# AUDIO PROCESSING
# =========================
audio_q = queue.Queue(maxsize=5)
awake = False
last_final_time = 0
audio_busy = False

vosk_model = Model(VOSK_MODEL_PATH)

def create_recognizer(wake_only=False):
    if wake_only:
        result = KaldiRecognizer(vosk_model, VOSK_SR, WAKE_GRAMMAR)
    else:
        result = KaldiRecognizer(vosk_model, VOSK_SR)
    result.SetWords(True)
    return result

def clear_audio_queue():
    while True:
        try:
            audio_q.get_nowait()
        except queue.Empty:
            return

recognizer = create_recognizer(wake_only=True)

def audio_callback(indata, frames, time_info, status):
    if audio_busy:
        return
    if status:
        print("[sd status]", status, file=sys.stderr)
    try:
        audio_q.put_nowait(bytes(indata))
    except queue.Full:
        pass

def process_audio():
    global awake, audio_busy, last_final_time, recognizer

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
                if re.search(rf"\b{re.escape(WAKE_WORD.lower())}\b", text):
                    awake = True
                    recognizer = create_recognizer()
                    audio_busy = True
                    clear_audio_queue()
                    try:
                        speak("Hello!")
                    finally:
                        clear_audio_queue()
                        audio_busy = False
                continue

            audio_busy = True
            clear_audio_queue()
            try:
                handle_command(text)
            finally:
                clear_audio_queue()
                recognizer = create_recognizer(wake_only=True)
                awake = False
                audio_busy = False

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
