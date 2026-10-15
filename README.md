# IRIS Setup (Linux / Raspberry Pi OS)

Run these commands from the repository directory.

## 1. Install system packages and create the Python environment

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip alsa-utils portaudio19-dev unzip curl
python3 -m venv iris
source iris/bin/activate
python -m pip install --upgrade pip
pip install vosk sounddevice numpy scipy ollama piper-tts music-assistant-client requests
```

If you already have the `iris` virtual environment, activate it and install the
new Music Assistant client dependency with
`pip install music-assistant-client`.

## 2. Download the Vosk speech model

The small English model is suitable for on-device speech recognition and is
about 50 MB compressed:

```bash
mkdir -p models
curl -fL https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip \
  -o /tmp/vosk-model-small-en-us-0.15.zip
unzip -q /tmp/vosk-model-small-en-us-0.15.zip -d models
mv models/vosk-model-small-en-us-0.15 models/vosk
rm /tmp/vosk-model-small-en-us-0.15.zip
```

The model files should be directly inside `models/vosk/` (for example,
`models/vosk/am/` and `models/vosk/conf/`).
Browse other supported models at [Vosk Models](https://alphacephei.com/vosk/models).

## 3. Download the Piper voice

Download both the ONNX voice and its matching JSON configuration into the
repository root:

```bash
curl -fL \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx \
  -o en_US-ryan-medium.onnx
curl -fL \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx.json \
  -o en_US-ryan-medium.onnx.json
```

The voice list and license information are on the
[Piper voices repository](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US).

## 4. Install and prepare Ollama

Install Ollama using the instructions for your OS at
[ollama.com/download](https://ollama.com/download), then pull the model and
create IRIS's configured model:

```bash
ollama pull gemma3:1b
ollama create iris -f modelfile
```

The Ollama service must be running before starting IRIS. Re-run
`ollama create iris -f modelfile` after editing the Modelfile.

## 5. Configure environment variables and credentials

Create your local, ignored `.env` from the checked-in template:

```bash
cp -n .env.example .env
chmod 600 .env
nano .env
```

In the editor, fill in the values below (save with Ctrl+O, Enter, then exit
with Ctrl+X):

- `MUSIC_ASSISTANT_URL`: the Music Assistant server's base URL, such as
  `http://192.168.1.20:8095`. Use `http://localhost:8095` only if it is on this
  same Raspberry Pi.
- `MUSIC_ASSISTANT_TOKEN`: create a long-lived token in Music Assistant's user
  profile/settings page. Keep it private.
- `MUSIC_ASSISTANT_PLAYER_ID`: identify the speaker/queue as described below.
- `WEBZ_API_TOKEN`: optional [Webz.io News API](https://webz.io/products/news-api)
  token. Leave blank if news is not configured.

The other entries configure model and audio paths/devices. The defaults match
the original IRIS setup; change `IRIS_MIC_DEVICE` and `IRIS_ALSA_DEVICE` to the
device names available on your Pi if needed.

To find the player ID, first put the Music Assistant token in `.env`, activate
the virtual environment, and run:

```bash
set -a
. ./.env
set +a
python music.py
```

This prints Music Assistant player IDs and availability. Copy the desired
player's ID into `MUSIC_ASSISTANT_PLAYER_ID` in `.env`. The token and player ID
are required for playback. IRIS connects to Music Assistant using the
[official Python client's](https://github.com/music-assistant/client)
authenticated WebSocket API; it no longer sends the old hand-built HTTP `/api`
request. If you do not have a Music Assistant server yet, follow its
[installation guide](https://music-assistant.io/installation/).

**Credential safety:** A Webz.io API token was previously hard-coded in
`news.py`. Revoke/rotate that token in Webz.io, then put the replacement only
in your ignored `.env`. The existing Music Assistant token shown in the source
was masked, so obtain a fresh long-lived token from Music Assistant. Do not
commit `.env` or paste tokens into source files.

## 6. Start IRIS

From the repository directory:

```bash
source iris/bin/activate
set -a
. ./.env
set +a
python iriscore.py
```

If you open a new terminal, activate the virtual environment and load `.env`
again. Never run `. ./.env` if you do not trust the contents of that file; it is
read as shell configuration.

Expected model/audio layout:

```text
I.R.I.S/
├── .env
├── en_US-ryan-medium.onnx
├── en_US-ryan-medium.onnx.json
├── models/
│   └── vosk/
│       ├── am/
│       ├── conf/
│       ├── graph/
│       └── ...
├── iriscore.py
├── modelfile
├── music.py
├── news.py
└── weather.py
```

The `.env` file, downloaded model files, and Python bytecode are excluded from
Git by `.gitignore`. `.env.example` is a safe template; it contains no active
credentials.

## Performance and wake-word notes

IRIS uses the small Vosk model for always-on listening. While waiting for the
wake word, `iriscore.py` now gives Vosk a grammar containing only `iris` and
`[unk]`; after the wake word is detected it switches to the normal recognizer
for the user's request. This narrows the always-on decoding search without
adding another model or runtime. The grammar is supported by Vosk's small
models, but test wake-word detection in your room because a restricted grammar
can affect false activations and missed detections.

Other changes intended to reduce delay and resource use:

- Piper's voice is loaded on its first use and reused, rather than loaded for
  every sentence. Audio chunks for each sentence are sent to one `aplay`
  process.
- The microphone callback discards captured audio while IRIS is speaking or
  processing a request. A bounded queue prevents stale audio from building up
  if recognition falls behind. IRIS therefore does not buffer speech spoken
  during its response.
- Ollama is asked to keep the model loaded for 10 minutes, reducing model
  reloads between nearby requests. This uses RAM while the model remains
  loaded; change `keep_alive` in `iriscore.py` if you prefer to release that
  memory sooner.
- `num_predict` is capped at 64 tokens. This limits unusually long generations;
  it may not change the time for normal short answers that already stop early.
- Pi-specific paths, audio devices, wake word, Ollama model/keep-alive, and API
  credentials are read from environment variables. See `.env.example`.

### Conversation memory

IRIS includes the previous three user/assistant exchanges in later Ollama
prompts, so follow-up questions can refer to earlier replies. Each saved user
or assistant message is limited to 600 characters. This history lives only in
memory: it is cleared when IRIS exits or restarts and is not written to disk.
Only requests that reach IRIS's response handling (including music commands)
are added to this short history.

### Wake-word alternatives

For a dedicated low-power detector, [Porcupine](https://picovoice.ai/docs/porcupine/)
is worth testing. A similar Pi Zero 2 W assistant uses Porcupine locally for
wake-word detection and runs Vosk, Ollama, and Piper as separate services:
[HAL Voice Assistant](https://github.com/campwill/hal-voice-assistant).
Porcupine is a commercial product and requires its SDK/access setup, so it adds
a dependency and is not a drop-in free/open-source replacement.

[openWakeWord](https://github.com/dscripka/openWakeWord) is open source and
processes 80 ms audio frames. Its maintainers note that it is not as small as
commercial detectors for highly constrained hardware, although a Pi 5 should
have more headroom than the Pi 3 example in its documentation. For this project,
try Vosk's grammar first because it reuses the already-loaded speech model.
Consider Porcupine if Vosk wake detection is too CPU-intensive or unreliable;
compare CPU use and false activations on your actual microphone before
switching.

### Pi 5 tuning to measure

- Keep `num_thread 3` as the starting point in `modelfile`. It leaves some CPU
  capacity for the operating system while giving Ollama parallelism. Compare
  2, 3, and 4 threads with the same prompts; more threads are not guaranteed to
  improve response time on a four-core Pi, especially if another stage is
  active.
- If your microphone supports 16 kHz mono capture, test it as a direct input
  for Vosk. The current 48 kHz input is downsampled to 16 kHz in Python; direct
  capture could avoid that work. Keep the current setting if the device does
  not support 16 kHz reliably.
- Measure Ollama's first request after idle separately from subsequent
  requests. The first can include model loading. Record temperature and check
  for throttling during repeated requests; the fan helps if it prevents
  throttling, while the SSD mostly improves storage and model-load time rather
  than steady-state token generation.
