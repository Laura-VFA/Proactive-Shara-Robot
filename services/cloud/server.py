import logging
from dataclasses import dataclass

from .google_api import speech_to_text, text_to_speech, translate_to
from .ibm_api import (analyze_mood, create_session, generate_response,
                      is_session_active)


logger = logging.getLogger('Server')
logger.setLevel(logging.DEBUG)


@dataclass
class Request:
    audio: str
    text: str = None
    username: str = None
    proactive_question: str = ''

@dataclass
class Response:
    request: Request
    audio: str
    action: str
    username: str
    continue_conversation: bool
    eva_mood: str = 'neutral'
    text: str = None


def query(request: Request):
    # STT
    request.text = speech_to_text(request.audio)
    logger.info(f"STT result :: '{request.text}'")
    
    if not request.text:
        return None

    # Translation (for emotion analysis)
    translation = translate_to(request.text)
    logger.info(f'Translation result :: {translation}')

    # Emotion Analysis & other context variables
    context_variables = analyze_mood(translation) 
    context_variables["username"] = request.username
    context_variables["action"] = None
    context_variables["continue"] = ""
    context_variables["eva_mood"] = ""
    context_variables["proactive_question"] = request.proactive_question 
    logger.info(f'Query context :: {context_variables}')

    # Generate the response
    text_response, user_skills = generate_response(request.text, context_variables)
    logger.info(f'Response text :: {text_response}')
    logger.info(f'Response context :: {user_skills}')

    # TTS
    audio_response = text_to_speech(text_response)
    logger.info("TTS result obtained")

    # Send back the response
    return Response(
        request,
        audio_response,
        user_skills.get('action', None),
        user_skills.get('username', None),
        bool(user_skills.get('continue', '')),
        user_skills['eva_mood'] if 'eva_mood' in user_skills and user_skills['eva_mood'] else 'neutral',
        text_response
    )

def prepare():
    # Check if session is alive: if not, create a new one
    if not is_session_active():
        create_session()

        logger.info('New IBM session created')
