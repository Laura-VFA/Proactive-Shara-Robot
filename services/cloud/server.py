import logging
import time
from dataclasses import dataclass

from .google_api import speech_to_text, text_to_speech
from .openai_api import generate_response, load_conversation_history, save_conversation_history, clear_conversation_history

logger = logging.getLogger('Server')
logger.setLevel(logging.DEBUG)


@dataclass
class Request:
    audio: str = b''
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
    robot_mood: str = 'neutral'
    text: str = None


def query(request: Request):
    # STT
    start_time = time.time()
    request.text = speech_to_text(request.audio)
    logger.info(f"STT result ({time.time() - start_time:.2f} seconds) :: '{request.text}'")
    
    if not request.text:
        return None

    # Set context variables
    context_variables = {}
    context_variables["username"] = request.username
    context_variables["proactive_question"] = request.proactive_question 
    logger.info(f'Query context :: {context_variables}')

    # Generate the response
    start_time = time.time()
    text_response, robot_context = generate_response(request.text, context_variables)
    logger.info(f'LLM response generated in {time.time() - start_time:.2f} seconds')
    logger.info(f'Response text :: {text_response}')
    logger.info(f'Response context :: {robot_context}')

    # TTS
    start_time = time.time()
    audio_response = text_to_speech(text_response)
    logger.info(f"TTS result obtained (response generated in {time.time() - start_time:.2f} seconds)")

    # Send back the response
    return Response(
        request,
        audio_response,
        robot_context.get('action', None),
        robot_context.get('username', None),
        bool(robot_context.get('continue', '')),
        robot_context['robot_mood'] if 'robot_mood' in robot_context and robot_context['robot_mood'] else 'neutral',
        text_response
    )

def proactive_query(request: Request):
    # Same as query but with empty input_text and without STT
    # Set context variables
    context_variables = {}
    context_variables["username"] = request.username
    context_variables["proactive_question"] = request.proactive_question 
    logger.info(f'Query context :: {context_variables}')

    # Generate the response
    start_time = time.time()
    text_response, robot_context = generate_response('', context_variables) # Empty input_text since it's a proactive question
    logger.info(f'LLM response generated in {time.time() - start_time:.2f} seconds')
    logger.info(f'Response text :: {text_response}')
    logger.info(f'Response context :: {robot_context}')

    # TTS
    start_time = time.time()
    audio_response = text_to_speech(text_response)
    logger.info(f"TTS result obtained (response generated in {time.time() - start_time:.2f} seconds)")

    # Send back the response
    return Response(
        request,
        audio_response,
        robot_context.get('action', None),
        robot_context.get('username', None),
        bool(robot_context.get('continue', '')),
        robot_context['robot_mood'] if 'robot_mood' in robot_context and robot_context['robot_mood'] else 'neutral',
        text_response
    )

def load_conversation_db(username):
    # Load conversation history for the user
    load_conversation_history(username)

    logger.info(f'Conversation history of {username} loaded')

def dump_conversation_db(username):
    # Dump conversation history for the user, update database
    save_conversation_history(username)
    clear_conversation_history() # Clear conversation history in-RAM

    logger.info(f'Conversation history of {username} updated to file database')
