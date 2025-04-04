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
        self.next_presence_question_time = datetime.now() + timedelta(minutes=60)
        self.logger.info(f"First how_are_you (presence) set at {self.next_presence_question_time}")

        self.next_close_face_question_time = {}
        try:
            with open('files/conversations_db.json', "r", encoding="utf-8") as file:
                users = list(json.load(file).keys())
                self.next_close_face_question_time = {user: datetime.now() for user in users}
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
                    self.callback('ask_how_are_you', {'type': 'close_face_recognized', 'username': args['username']})

            elif subtype == 'unknown_face': # Ask new user's name
                self.callback('ask_who_are_you')


        elif type == 'new_timer':
            if subtype == 'how_are_you':# set next future alarms for proactive questions
                 # Set new alarm for presence 2 hours later
                self.next_presence_question_time = datetime.now() + timedelta(hours=2)
                self.logger.info(f"Next how_are_you - presence timer set at {self.next_presence_question_time}")

                if args['username']: # Set new alarm for close face (specific user) 30 minute later
                    self.next_close_face_question_time[args['username']] = datetime.now() + timedelta(minutes=30)
                    self.logger.info(f"Next how_are_you - close_face_recognized ({args['username']}) set at {self.next_close_face_question_time}")
                
                else: # Postpone all the known users alarms 10 minutes later (just in case the user doesn't want to talk after presece proactive question and the user is still there)
                    self.logger.info(f"Postponing all the known users alarms 10 minutes later")
                    for user in self.next_close_face_question_time.keys():
                        self.next_close_face_question_time[user] = datetime.now() + timedelta(minutes=10)
                        self.logger.info(f"Next how_are_you - close_face_recognized postponed 10 min ({user}) set at {self.next_close_face_question_time[user]}")


        elif type == 'confirm': # Questions asked
            if subtype == 'how_are_you':
                self.logger.info(f"{subtype} - {args} proactive question asked")

            elif subtype == 'who_are_you': 
                pass
            
            elif subtype == 'recorded_face': # add new user to the list of users (proactive question alarm)
                self.next_close_face_question_time[args['username']] = datetime.now() + timedelta(minutes=30)
                self.logger.info(f"Added {args['username']} to proactive alarm, set at {self.next_close_face_question_time[args['username']]}")
