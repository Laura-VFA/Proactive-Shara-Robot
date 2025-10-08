# Google services wrapper
# (TTS, STT)
from google.cloud import speech, texttospeech

import time

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
    language_code="es-ES",
    enable_automatic_punctuation=True
)
streaming_config = speech.StreamingRecognitionConfig(
    config=stt_config,
    interim_results=True  # Get interim results while speaking
)


def speech_to_text(audio_bytes):
    """
    Converts speech audio to text (non streaming)
    
    Args:
        audio_bytes (bytes): The audio content to transcribe

    Returns:
        str: The transcribed text
    """
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


def create_streaming_stt_request_generator(audio_generator):
    """
    Creates a generator of streaming requests from an audio generator.
    
    Args:
        audio_generator: Generator that yields audio chunks (bytes)
    
    Returns:
        Generator of StreamingRecognizeRequest objects
    """
    for audio_chunk in audio_generator:
        yield speech.StreamingRecognizeRequest(audio_content=audio_chunk)


def streaming_speech_to_text(audio_generator):
    """
    Performs streaming speech recognition on audio chunks.
    
    Args:
        audio_generator: Generator that yields audio chunks (bytes)
    
    Returns:
        tuple: (transcript, silence_detection_time) where silence_detection_time is the time 
               from when the last interim result was received to when final transcript was available
    """
    
    requests = create_streaming_stt_request_generator(audio_generator)
    responses = clientSTT.streaming_recognize(streaming_config, requests)
    
    transcript = ""
    silence_detection_time = None
    last_interim_time = None
    
    try:
        for response in responses:
            if not response.results:
                continue
                
            result = response.results[0]
            
            if not result.is_final:
                # Update the time of the last interim result (user still speaking)
                last_interim_time = time.time()
            else:
                # Final result - calculate time since last interim result
                final_result_time = time.time()
                transcript = result.alternatives[0].transcript
                
                if last_interim_time is not None:
                    silence_detection_time = final_result_time - last_interim_time
                else:
                    # No interim results received, can't measure accurately
                    silence_detection_time = 0.0
                    
                break  # We got the final result
    
    except Exception as e:
        # If the stream ends or there's an error, return what we have
        pass
    
    return transcript, silence_detection_time
