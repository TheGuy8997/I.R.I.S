# IRIS Setup 

## 1. Create and activate virtual environment
python3 -m venv iris

source iris/bin/activate

## 2. Install dependencies
pip install vosk sounddevice numpy scipy ollama piper-tts

## 3. System dependencies (audio)
sudo apt install alsa-utils portaudio19-dev

## 4. Download Vosk model
Download:
https://alphacephei.com/vosk/models

Model:
vosk-model-small-en-us-0.15

Unzip the contents INTO:
models/vosk/

Result:
models/vosk/
  am/
  conf/
  graph/
  ivector/
  ...

## 5. Download Piper voice
Download:
https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US

File:
en_US-ryan-medium.onnx

Place in root:
iris/en_US-ryan-medium.onnx

## 6. Setup Ollama model
ollama pull gemma2:2b
ollama create iris -f Modelfile

## 7. File structure
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


## 8. Run
python iriscore.py

## 9. Config (in code)
VOSK_MODEL_PATH = "models/vosk"
PIPER_VOICE = "en_US-ryan-medium.onnx"
