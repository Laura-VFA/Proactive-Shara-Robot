# Google services wrapper
# (TTS, STT and translation)
from google.cloud import speech, texttospeech
from google.cloud import translate_v2 as translate


# TTS
clientTTS = texttospeech.TextToSpeechClient()
voice = texttospeech.VoiceSelectionParams(
    language_code='es-ES',
    ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
)
tts_config = texttospeech.AudioConfig(
    audio_encoding=texttospeech.AudioEncoding.LINEAR16,
    sample_rate_hertz=24000,
    pitch=-0.4,
)

# STT 
clientSTT = speech.SpeechClient()
stt_config = speech.RecognitionConfig(
    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
    sample_rate_hertz=16000,
    language_code="es-ES"
)

# Translator 
translate_client = translate.Client()



def speech_to_text(audio_bytes):
    audio = speech.RecognitionAudio(content=audio_bytes)
    response = clientSTT.recognize(config=stt_config, audio=audio)

    # The first alternative is the most likely one
    return "".join(result.alternatives[0].transcript for result in response.results)

def text_to_speech(text):
    synthesis_input = texttospeech.SynthesisInput(text=text)
    response = clientTTS.synthesize_speech(
        input=synthesis_input, voice=voice, audio_config=tts_config
    )

    return response.audio_content

def translate_to(text, source_lang='es', target_lang='en'):
    result = translate_client.translate(
        text,
        source_language=source_lang,
        target_language=target_lang
    )

    return result["translatedText"]
