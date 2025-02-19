import json
import logging
from datetime import datetime, timedelta


class ProactiveService:
    def __init__(self, callback) -> None:
        self.logger = logging.getLogger('Proactive')
        self.logger.setLevel(logging.DEBUG)

        self.question = None
        self.callback = callback

        # Put an alarms to ask for user mood
        self.next_presence_question_time = datetime.now() + timedelta(minutes=30)
        self.logger.info(f"First how_are_you (presence) set at {self.next_presence_question_time}")

        self.next_close_face_question_time = {}
        try:
            with open('files/conversations_db.json', "r", encoding="utf-8") as file:
                users = list(json.load(file).keys())
                self.next_close_face_question_time = {user: datetime.now() + timedelta(minutes=30) for user in users}
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        self.logger.info(f"First how_are_you (close faces) set at {self.next_close_face_question_time}")

        self.logger.info('Ready')

    
    def update(self, type, subtype, args={}):
        self.logger.info(f"Update {type}::{subtype} - {args}")

        if type == 'sensor':
            if subtype == 'presence':
                # Timeout, ask 'How are you?'
                if (self.next_presence_question_time - datetime.now()).total_seconds() <= 0: 
                    self.callback('ask_how_are_you', {'type': 'presence'})
                
            elif subtype == 'close_face_recognized':
                # Timeout, ask 'How are you? to specific user'
                if (self.next_close_face_question_time[args['username']] - datetime.now()).total_seconds() <= 0: 
                    self.callback('ask_how_are_you', {'type': 'close_face_recognized'})

            elif subtype == 'unknown_face': # Ask new user's name
                self.callback('ask_who_are_you')

            
        elif type == 'abort':
            if subtype == 'how_are_you':
                self.next_presence_question_time = datetime.now() + timedelta(hours=2) # Postpone the timer 2 hours
                self.logger.info(f"{subtype} - presence postponed until {self.next_presence_question_time}")

                if args['type'] == 'close_face_recognized': # Set new alarm for close face 30 minute later and for presence 2 hours later
                    self.next_close_face_question_time[args['username']] = datetime.now() + timedelta(minutes=30)
                    self.logger.info(f"{subtype} - {args['type']} postponed until {self.next_close_face_question_time}")
            
            elif subtype == 'who_are_you':
                pass
    

        elif type == 'confirm': # Questions asked
            if subtype == 'how_are_you':# set next future alarms for proactive questions
                if args['type'] == 'presence': # Set new alarm for presence 4 hours later
                    self.next_presence_question_time = datetime.now() + timedelta(hours=4)  

                elif args['type'] == 'close_face_recognized': # Set new alarm for close face 30 minute later and for presence 2 hours later
                    self.next_close_face_question_time[args['username']] = datetime.now() + timedelta(minutes=30)
                    self.next_presence_question_time = datetime.now() + timedelta(hours=2)
                    self.logger.info(f"Next {subtype} - {args['type']} set at {self.next_close_face_question_time}")

                self.logger.info(f"Next {subtype} - presence set at {self.next_presence_question_time}")

            elif subtype == 'who_are_you': 
                pass
            
            elif subtype == 'recorded_face': # add new user to the list of users (proactive question alarm)
                self.next_close_face_question_time[args['username']] = datetime.now() + timedelta(minutes=30)
                self.logger.info(f"Added {args['username']} to proactive alarm, set at {self.next_close_face_question_time[args['username']]}")
