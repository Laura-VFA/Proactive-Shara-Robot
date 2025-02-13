import json
import logging
import random
from datetime import datetime, timedelta


class ProactivePhrases:
    phrases = None

    @staticmethod
    def load(encodings_file='files/proactive_phrases.json'):
        with open(encodings_file) as json_file:
            ProactivePhrases.phrases = json.load(json_file)
    
    @staticmethod
    def get(phrase_key):
        return random.choice(ProactivePhrases.phrases[phrase_key])


class ProactiveService:
    def __init__(self, callback) -> None:
        self.logger = logging.getLogger('Proactive')
        self.logger.setLevel(logging.DEBUG)

        self.question = None
        self.callback = callback

        # Put an alarm every day at 8 am to ask for user mood
        self.next_question_time = (datetime.now() + timedelta(days=1)).replace(hour=8,minute=0)
        self.logger.info(f'First how_are_you set at {self.next_question_time}')
        # [TEST] self.next_question_time = datetime.now() + timedelta(minutes=1)

        self.logger.info('Ready')

    
    def update(self, type, subtype, args={}):
        self.logger.info(f'Update {type}::{subtype} - {args}')

        if type == 'sensor':
            if subtype == 'presence':
                # Timeout, ask 'How are you?'
                if (self.next_question_time - datetime.now()).total_seconds() <= 0: 
                    self.callback('ask_how_are_you')

            elif subtype == 'unknown_face': # Ask new user's name
                self.callback('ask_who_are_you')

            
        elif type == 'abort':
            if subtype == 'how_are_you':
                # Postpone the timer 2 hours
                self.next_question_time = datetime.now() + timedelta(hours=2)
                self.logger.info(f'{subtype} postponed until {self.next_question_time}')
                # [TEST] self.next_question_time = datetime.now() + timedelta(seconds=30)
            
            elif subtype == 'who_are_you':
                pass
            
            elif subtype == 'read_pending_messages':
                pass

        elif type == 'confirm': # Questions asked
            if subtype == 'how_are_you': # Put again a timer tomorrow at 8 am
                self.next_question_time = (datetime.now() + timedelta(days=1)).replace(hour=8,minute=0)
                self.logger.info(f'Next {subtype} set at {self.next_question_time}')
                # [TEST] self.next_question_time = datetime.now() + timedelta(minutes=1)

            elif subtype == 'who_are_you':
                pass
