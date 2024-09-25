from vosk import Model, KaldiRecognizer
import json

model = Model(".vosk-model-small-es-0.42")  # load model

# Vosk config
stt = KaldiRecognizer(model, 16000)  # rate 16000 Hz

def speech_to_text(audio_bytes):
    stt.Reset()
    stt.AcceptWaveform(audio_bytes)

    result = json.loads(stt.Result())
    transcript = result.get("text", "")

    return transcript
