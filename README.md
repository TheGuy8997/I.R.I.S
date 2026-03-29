\IRIS Setup (Linux)

IRIS is a lightweight voice assistant powered by Vosk (speech recognition), Piper (text-to-speech), and Ollama (LLM backend).

--------------------------------------------------

INSTALLATION & SETUP

1. Create and Activate Virtual Environment
python3 -m venv iris
source iris/bin/activate

--------------------------------------------------

2. Install Python Dependencies
pip install vosk sounddevice numpy scipy ollama piper-tts

--------------------------------------------------

3. Install System Dependencies (Audio)
sudo apt update
sudo apt install alsa-utils portaudio19-dev

--------------------------------------------------

MODEL DOWNLOADS

4. Download Vosk Model

Download from:
https://alphacephei.com/vosk/models

Model:
vosk-model-small-en-us-0.15

Unzip the model into:
models/vosk/

Expected structure:
models/vosk/
├── am/
├── conf/
├── graph/
├── ivector/
└── ...

--------------------------------------------------

5. Download Piper Voice

Download from:
https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US

File:
en_US-ryan-medium.onnx

Place it in the project root:
iris/en_US-ryan-medium.onnx

--------------------------------------------------

OLLAMA SETUP

6. Pull and Create Model
ollama pull gemma2:2b
ollama create iris -f Modelfile

--------------------------------------------------

PROJECT STRUCTURE

iris/
├── iriscore.py
├── en_US-ryan-medium.onnx
├── models/
│   └── vosk/
│       ├── am/
│       ├── conf/
│       ├── graph/
│       ├── ivector/
│       └── ...
├── weather.py
└── news.py

--------------------------------------------------

RUN THE APPLICATION

python iriscore.py

--------------------------------------------------

CONFIGURATION

Ensure the following paths are set in your code:

VOSK_MODEL_PATH = "models/vosk"
PIPER_VOICE = "en_US-ryan-medium.onnx"

--------------------------------------------------

CREDITS

Vosk: https://alphacephei.com/vosk/
Piper TTS: https://github.com/rhasspy/piper
Ollama: https://ollama.com/

--------------------------------------------------
