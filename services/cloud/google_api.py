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

# STT Config (non-streaming) - used as fallback
stt_config = speech.RecognitionConfig(
    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
    sample_rate_hertz=16000,
    language_code="es-ES",
    enable_automatic_punctuation=True,
    model="latest_short"  # Good for both long and short utterances
)

# STT Streaming config - uses latest_long (optimized for conversations)
streaming_config = speech.StreamingRecognitionConfig(
    config=speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="es-ES",
        enable_automatic_punctuation=True,
        model="latest_long"
    ),
    interim_results=True
)


def speech_to_text(audio_bytes):
    """
    Converts speech audio to text (non-streaming, synchronous).
    Uses latest_short model which works well for short utterances.
    
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
    
    Yields:
        StreamingRecognizeRequest objects
    """
    for audio_chunk in audio_generator:
        yield speech.StreamingRecognizeRequest(audio_content=audio_chunk)


def create_streaming_requests_with_collection(audio_generator):
    """
    Creates streaming requests while collecting audio for fallback.
    
    Args:
        audio_generator: Generator that yields audio chunks (bytes)
    
    Returns:
        tuple: (request_generator, collected_audio_list)
    """
    collected = []
    
    def gen():
        for audio_chunk in audio_generator:
            collected.append(audio_chunk)
            yield speech.StreamingRecognizeRequest(audio_content=audio_chunk)
    
    return gen(), collected


def streaming_speech_to_text(audio_generator):
    """
    Core streaming STT function. Pure streaming logic without fallback.
    
    Args:
        audio_generator: Generator that yields audio chunks (bytes)
    
    Returns:
        tuple: (transcript, silence_detection_time, audio_bytes) where:
            - transcript: The transcribed text from streaming
            - silence_detection_time: Time from last interim to final result
            - audio_bytes: Collected audio for potential fallback
    """
    # Create requests and collect audio for potential fallback
    requests, collected_audio = create_streaming_requests_with_collection(audio_generator)
    responses = clientSTT.streaming_recognize(streaming_config, requests)
    
    transcript = ""
    silence_detection_time = None
    last_interim_time = None
    last_interim_transcript = ""  # Store last interim result as fallback
    interim_count = 0
    
    try:
        for response in responses:
            if not response.results:
                continue
                
            result = response.results[0]
            
            if not result.is_final:
                # Update the time of the last interim result (user still speaking)
                interim_count += 1
                last_interim_transcript = result.alternatives[0].transcript  # Save interim transcript
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
                
                # If final transcript is empty but we had interim results, use the last interim
                # Only do this if we had multiple interim results (more confidence)
                if not transcript and last_interim_transcript and interim_count >= 2:
                    transcript = last_interim_transcript

                break  # We got the final result
    
    except Exception as e:
        # If the stream ends or there's an error, return what we have
        # Use last interim result if available
        if not transcript and last_interim_transcript and interim_count >= 2:
            transcript = last_interim_transcript
    
    audio_bytes = b''.join(collected_audio) if collected_audio else b''
    return transcript, silence_detection_time, audio_bytes


def compose_streaming_fallback_speech_to_text(audio_generator):
    """
    Performs streaming speech recognition with automatic fallback for empty results.
    
    Strategy:
    1. Try streaming STT with latest_long model (optimized for conversations)
    2. If result is empty, fallback to latest_short model (better for monosyllables)
    
    Args:
        audio_generator: Generator that yields audio chunks (bytes)
    
    Returns:
        tuple: (transcript, silence_detection_time) where:
            - transcript: The transcribed text
            - silence_detection_time: Total time including fallback if used
    """
    # Step 1: Try streaming STT
    transcript, silence_time, audio_bytes = streaming_speech_to_text(audio_generator)
    
    # Step 2: Fallback if result is empty
    if not transcript and audio_bytes:
        try:
            fallback_start = time.time()
            fallback_transcript = speech_to_text(audio_bytes)
            fallback_time = time.time() - fallback_start
            
            if fallback_transcript:
                transcript = fallback_transcript
                # Add fallback time to total time
                if silence_time is not None:
                    silence_time += fallback_time
                else:
                    silence_time = fallback_time
        except Exception:
            # Fallback failed, keep original transcript
            pass
    
    return transcript, silence_time
