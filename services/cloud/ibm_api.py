# IBM Watson wrapper
# (Watson Assistant, NLU Emotion Analysis)
import json
import os
from datetime import datetime

from ibm_watson import AssistantV2, NaturalLanguageUnderstandingV1


# Watson Assistant
with open(os.environ.get('WATSON_ASSISTANT_CREDENTIALS')) as json_file:
    assistant_id = json.load(json_file)['assistant_id']

SESSION_TIME = 20 # in seconds
last_query_time = None
session_id = ''
assistant = AssistantV2(version='2024-08-25')


# NLU Emotion Analysis
nlu_options = {
    'text': '',
    'features': {
        'emotion': {},
    },
    'language': "en"
}
nlu = NaturalLanguageUnderstandingV1(version='2022-04-07')



def create_session(): 
    # Create Watson Assistant session

    global session_id, assistant_id

    response = assistant.create_session(
        assistant_id=assistant_id
    ).get_result()

    session_id = response['session_id']

def is_session_active():
    # Empty query to check if session is active

    global last_query_time

    return last_query_time is not None and (datetime.now() - last_query_time).total_seconds() < SESSION_TIME 

def generate_response(input_text, context_data={}):
    global session_id, assistant_id, last_query_time

    if not input_text :
        return None

    response = assistant.message(
        assistant_id=assistant_id,
        session_id=session_id,
        input={
            'message_type': 'text',
            'text': input_text,
            'options': {
                'return_context': True # For returning the context variables
            }
        },
        context={
            "skills": {
                "main skill": {
                    "user_defined": context_data
                }
            }
        }
    ).get_result()

    last_query_time = datetime.now()

    response_text = '. '.join([resp['text'] for resp in response['output']['generic']])

    user_skills = response['context']['skills']['main skill']['user_defined']

    return response_text, user_skills

def analyze_mood(text):
    nlu_options['text'] = text
    try:
        response = nlu.analyze(**nlu_options).get_result()
    except Exception:
        return {}
    else:
        return response['emotion']['document']['emotion']
