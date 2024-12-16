import logging
import logging.config
import queue
import threading

from services.camera_services import (FaceDB, PresenceDetector, RecordFace,
                                     Wakeface)
from services.cloud import server
from services.cloud.telegram import TelegramService
from services.eyes.service import Eyes
from services.leds import ArrayLed, LedState
from services.mic import Recorder
from services.proactive_service import ProactivePhrases, ProactiveService
from services.speaker import Speaker


logging.config.fileConfig('files/logging.conf')
logger = logging.getLogger('Main')
logger.setLevel(logging.DEBUG)


eva_context = { # Eva status & knowledge of the environment
    'state':'idle', 
    'username': None, 
    'continue_conversation': False, 
    'proactive_question': '', 
    'tg_destination_name': ''
}

notifications = queue.Queue() # Transition state queue

listen_timer = None # Listening timeout handler
DELAY_TIMEOUT = 5 # in sec

# Preload of error audios
with open('files/connection_error.wav', 'rb') as f:
    connection_error_audio = f.read()
with open('files/tg_contact_error.wav', 'rb') as f:
    tg_contact_error_audio = f.read()



def wf_event_handler(event, usernames=None):
    global eva_context

    if event == 'face_listen' and eva_context['state'] == 'idle_presence':
        notifications.put({'transition': 'idle_presence2listening'})
    
    elif event in ['face_not_listen', 'not_faces']:
        eva_context['username'] = None

        if eva_context['state'] == 'listening':
            notifications.put({'transition': 'listening2idle_presence'})
        
    elif event == 'face_recognized':
        known_names = [name for name in usernames if name] # remove None names
        if known_names:
            # Sort names by number of consecutive frames recognized
            known_names = sorted(usernames, key=lambda name: usernames[name], reverse=True)
            eva_context['username'] = known_names[0]
            logger.info(f"Username updated to {eva_context['username']}")

        elif None in usernames and usernames[None] >= 3: # Detect 3 unknown in a row
            proactive.update('sensor', 'unknown_face')

def rf_event_handler(event, progress=None):
    if event == 'recording_face':
        notifications.put({
            'transition': 'recording_face', 
            'params': {
                'progress': progress # update recording progress
            }
        })

def pd_event_handler(event):
    global eva_context

    if event == 'person_detected' and eva_context['state'] == 'idle' :
        notifications.put({'transition': 'idle2idle_presence'})
        proactive.update('sensor', 'presence')
    
    elif event == 'empty_room'  and eva_context['state'] == 'idle_presence' :
        notifications.put({'transition': 'idle_presence2idle'})

def mic_event_handler(event, audio=None):
    global eva_context

    notification = {
        'transition': '',
        'params': {
            'audio': audio
        }
    }
    if event == 'start_recording' and eva_context['state'] in ['listening', 'listening_without_cam']:
        if eva_context['state'] == 'listening':
            notification['transition']  = 'listening2recording'
        elif eva_context['state'] == 'listening_without_cam':
            notification['transition']  = 'listening_without_cam2recording'
        notifications.put(notification)

    if event == 'stop_recording' and eva_context['state'] == 'recording':
        notification['transition']  = 'recording2processingquery'
        notifications.put(notification)

def speaker_event_handler(event):
    global eva_context

    if event == 'finish_speak':
        if eva_context['continue_conversation']:
            notifications.put({'transition': 'speaking2listening_without_cam'})
        
        else:
            notifications.put({'transition': 'speaking2idle_presence'})

def proactive_service_event_handler(event, params={}):
    notification = {
        'transition': 'proactive2processingquery',
        'params': {
            'question': None
        }
    }

    if event == 'ask_how_are_you':
        notification ['params']['question'] = 'how_are_you'
        notifications.put(notification)
    
    elif event == 'ask_who_are_you':
        notification ['params']['question'] = 'who_are_you'
        notifications.put(notification)
    
    elif event == 'read_pending_messages':
        notification ['params']['question'] = 'read_pending_messages'
        notification['params']['messages'] = params
        notifications.put(notification)
        
def tg_event_handler(name, message): # incoming telegram message
    notifications.put({
        'transition': 'received_tg_message', 
        'params': {
            'name': name, # Sender contact name
            'message': message
        }
    })


def listen_timeout_handler():
    global eva_context

    if eva_context['state'] == 'listening_without_cam':
        notifications.put({'transition': 'listening_without_cam2idle_presence'})


def process_transition(transition, params={}):
    global eva_context, listen_timer

    logger.info(f'Handling transition {transition}')

    # User presence detected in the room
    if transition == 'idle2idle_presence' and eva_context['state'] == 'idle':
        eva_context['state'] = 'idle_presence'
        leds.set(LedState.static_color((186,85,211))) # set static purple color 
        wf.start()
    
    # User left the room
    elif transition == 'idle_presence2idle' and eva_context['state'] == 'idle_presence':
        eva_context['state'] = 'idle'
        eva_context['username'] = None
        leds.set(LedState.static_color((0,0,0))) # set static black color
        wf.stop()

    # User looking at the robot
    elif transition == 'idle_presence2listening' and eva_context['state'] == 'idle_presence':
        eva_context['state'] = 'listening'
        leds.set(LedState.loop((52,158,235))) # set light blue loop color
        pd.stop()
        mic.start()

    # User stopped looking at the robot
    elif transition == 'listening2idle_presence' and eva_context['state'] == 'listening':
        eva_context['state'] = 'idle_presence'
        eva_context['username'] = None
        leds.set(LedState.static_color((0,0,0))) # set static black color
        mic.stop()
        pd.start()

    # User looking at the robot starts talking
    elif transition == 'listening2recording' and eva_context['state'] == 'listening':
        eva_context['state'] = 'recording'
        leds.set(LedState.loop((255,255,255))) # set white loop color
        wf.stop()
        try:
            server.prepare() # Create session in advance if necessary
        except Exception as e:
            logger.warning(f'Could not create the IBM session. {str(e)}') 
    
    # User in conversation starts talking
    elif transition == 'listening_without_cam2recording' and eva_context['state'] == 'listening_without_cam':
        eva_context['state'] = 'recording'
        leds.set(LedState.loop((255,255,255))) # set white loop color
        listen_timer.cancel()
        try:
            server.prepare() # Create session in advance if necessary
        except Exception as e:
            logger.warning(f'Could not create the IBM session. {str(e)}')

    # User finished talking: sending audio to server
    elif transition == 'recording2processingquery' and eva_context['state'] == 'recording':
        eva_context['state'] = 'processing_query'
        leds.set(LedState.static_color((0,0,0)))
        mic.stop()

        audio = params['audio']

        try:
            response = server.query( # Make the query to the cloud
                server.Request(
                    audio, 
                    username=eva_context['username'], 
                    proactive_question=eva_context['proactive_question']
                )
            )
        except Exception as e: # Unable to connect to the server: play error msg
            logger.error(f'Could not make the query. {str(e)}')

            eva_context['continue_conversation'] = False
            eva_context['proactive_question'] = ''
            eva_context['state'] = 'speaking'
            eva_context['tg_destination_name'] = ''
            leds.set(LedState.breath((255,0,0))) # set breath red animation
            speaker.start(connection_error_audio)
        else:
            if response:
                if response.action: # Execute associated action
                    if response.action == 'record_face':
                        eva_context['username'] = response.username
                        rf.start(response.username)
                    elif response.action == 'update_target_name':
                        # Get text from speech to obtain target message contact name
                        text = response.request.text.split()
                        dst_name = ' '.join(text[text.index('a' if 'a' in text else 'para') + 1 :])
                        eva_context['tg_destination_name'] = dst_name
                    elif response.action == 'send_message': # Send telegram message
                        msg = response.request.text
                        try:
                            tg.send_message(eva_context['tg_destination_name'], msg)
                        except (KeyError, IndexError): # Contact not found
                            logger.error(f"Target user '{eva_context['tg_destination_name']}' not found in TG contacts list")

                            response.audio = tg_contact_error_audio
                        eva_context['tg_destination_name'] = '' # Clear target name

                eva_context['continue_conversation'] = response.continue_conversation
                eva_context['proactive_question'] = ''

                # Reproduce response                
                eva_context['state'] = 'speaking'
                eyes.set(response.eva_mood)
                leds.set(LedState.breath((52,158,235))) # light blue breath
                speaker.start(response.audio)

            elif eva_context['continue_conversation']: # Avoid end the conversation due to noises
                logger.info(f'Not text in audio, continuing conversation')
                logger.info(f'Handling transition processing_query2listening_without_cam')

                eva_context['state'] = 'listening_without_cam'
                leds.set(LedState.loop((52,158,235))) # light blue loop
                mic.start()

                # Add a timeout to execute a transition function due to inactivity
                listen_timer = threading.Timer(DELAY_TIMEOUT, listen_timeout_handler)
                listen_timer.start()

            else:
                logger.info(f'Not text in audio, back to idle')
                logger.info(f'Handling transition processing_query2idle_presence')

                eva_context['state'] = 'idle_presence'
                eva_context['username'] = None
                eva_context['proactive_question'] = ''
                eva_context['tg_destination_name'] = ''                
                eyes.set('neutral')
                leds.set(LedState.static_color((0,0,0))) # put black static color
                pd.start()
                wf.start()

    # Continue conversation after robot speaks: waiting for user audio
    elif transition == 'speaking2listening_without_cam' and eva_context['state'] == 'speaking':
        eva_context['state'] = 'listening_without_cam'
        leds.set(LedState.loop((52,158,235))) # light blue color
        mic.start()

        # Add a timeout to execute a transition funcion due to inactivity
        listen_timer = threading.Timer(DELAY_TIMEOUT, listen_timeout_handler)
        listen_timer.start()

    # Conversation finishes due to goodbye
    elif transition == 'speaking2idle_presence' and eva_context['state'] == 'speaking':
        eva_context['state'] = 'idle_presence' 
        eva_context['username'] = None
        eva_context['proactive_question'] = ''
        eva_context['tg_destination_name'] = ''
        eva_context['continue_conversation'] = False
        eyes.set('neutral')
        leds.set(LedState.static_color((0,0,0))) # put black static color
        rf.stop()
        pd.start()
        wf.start()
    
    # Conversation finishes due to timeout waiting for user audio
    elif transition == 'listening_without_cam2idle_presence'and eva_context['state'] == 'listening_without_cam':
        eva_context['state'] = 'idle_presence'
        eva_context['continue_conversation'] =  False
        eva_context['proactive_question'] =  ''
        eva_context['tg_destination_name'] = ''
        eyes.set('neutral')
        leds.set(LedState.static_color((0,0,0))) # put black static color
        mic.stop()
        rf.stop()
        pd.start()
        wf.start()

    # Handle a proactive question
    elif transition == 'proactive2processingquery':

        logger.info(f"Proactive question: {params['question']}")

        if params['question'] == 'how_are_you':
            if eva_context['state'] == 'idle_presence':
                eva_context['state'] = 'processing_query'
                leds.set(LedState.static_color((0,0,0))) # put black static color

                # Interrupt services
                wf.stop()
                pd.stop()

                try:
                    audio_response = server.text_to_speech(ProactivePhrases.get(params['question']))
                except Exception as e: # Error in server connection
                    logger.error(f'TTS failed. {str(e)}')

                    eva_context['continue_conversation'] = False
                    eva_context['proactive_question'] = ''
                    eva_context['state'] = 'speaking'
                    leds.set(LedState.breath((255,0,0))) # red breath animation
                    speaker.start(connection_error_audio)

                    proactive.update('abort', 'how_are_you')

                else:
                    eva_context['proactive_question'] = 'how_are_you'
                    eva_context['continue_conversation'] = True
                    eva_context['state'] = 'speaking'
                    leds.set(LedState.breath((52,158,235))) # light blue led breath animation
                    speaker.start(audio_response)
                    try:
                        server.prepare() # Create session in advance if necessary
                    except Exception as e:
                        logger.warning(f'Could not create the IBM session. {str(e)}')

                    proactive.update('confirm', 'how_are_you')

            else:
                proactive.update('abort', 'how_are_you')
            
        elif params['question'] == 'who_are_you':
            if eva_context['state'] == 'listening':
                eva_context['state'] = 'processing_query'
                leds.set(LedState.static_color((0,0,0))) # set static black color

                # Interrupt services
                mic.stop()
                wf.stop()

                try:
                    audio_response = server.text_to_speech(ProactivePhrases.get(params['question']))    
                except Exception as e: # Error in server connection
                    logger.error(f'TTS failed. {str(e)}')

                    eva_context['continue_conversation'] = False
                    eva_context['proactive_question'] = ''
                    eva_context['state'] = 'speaking'
                    leds.set(LedState.breath((255,0,0))) # red breath animation
                    speaker.start(connection_error_audio)

                    proactive.update('abort', 'who_are_you')
                else:
                    eva_context['proactive_question'] = 'who_are_you'
                    eva_context['continue_conversation'] = True
                    eva_context['state'] = 'speaking'
                    leds.set(LedState.breath((52,158,235))) # light blue led breath animation
                    speaker.start(audio_response)
                    try:
                        server.prepare() # Create session in advance if necessary
                    except Exception as e:
                        logger.warning(f'Could not create the IBM session. {str(e)}')

                    proactive.update('confirm', 'who_are_you')
            else:
                proactive.update('abort', 'who_are_you')
            
        elif params['question'] == 'read_pending_messages':
            if eva_context['state'] in ['listening', 'idle_presence']: # Check if it's a good moment to read the messages
                eva_context['state'] = 'processing_query'
                leds.set(LedState.static_color((0,0,0))) # set static black color

                # Interrupt services
                if eva_context['state'] == 'listening': mic.stop()
                wf.stop()
                if eva_context['state'] == 'idle_presence': pd.stop()

                
                # Join messages (if several)
                text = '. '.join(
                    ProactivePhrases.get('single_tg_msg').format(
                        name=name, msg=messages[0]
                    ) if len(messages) == 1 
                    else ProactivePhrases.get('multi_tg_msg').format(
                            name=name, msg='. '.join(messages)
                            )
                    for name, messages in params['messages'].items()
                )

                try:
                    # Generate the audio
                    audio_response = server.text_to_speech(text)    

                except Exception as e: # Error in server connection
                    logger.error(f'TTS failed. {str(e)}')

                    eva_context['continue_conversation'] = False
                    eva_context['proactive_question'] = ''
                    eva_context['state'] = 'speaking'
                    leds.set(LedState.breath((255,0,0))) # red breath animation
                    speaker.start(connection_error_audio)

                    proactive.update('abort', 'read_pending_messages')
                else:
                    eva_context['continue_conversation'] = False
                    eva_context['state'] = 'speaking'
                    leds.set(LedState.breath((0,255,0))) # green breath animation
                    speaker.start(audio_response)

                    proactive.update('confirm', 'read_pending_messages')
            else:
                proactive.update('abort', 'read_pending_messages')

    # Record new user face
    elif transition == 'recording_face':
        logger.info(f"Recording progress: {params['progress']:.2f}; Current state: {eva_context['state']}")

        leds.set(LedState.progress((0,255,0), percentage=params['progress'])) # percentage leds in green color

        if params['progress'] == 100: # Recording completed
            rf.stop()
            if eva_context['state'] in ['listening_without_cam', 'listening']:
                leds.set(LedState.loop((52,158,235))) # light loop blue animation
            elif eva_context['state'] == 'recording':
                leds.set(LedState.loop((255,255,255))) # white loop animation
            else:
                leds.set(LedState.static_color((0,0,0))) # static black color

    # Handle incoming telegram message
    elif transition == 'received_tg_message':
        if eva_context['state'] in ['idle_presence', 'listening']: # Message can be read right now
            eva_context['state'] = 'processing_query'
            leds.set(LedState.static_color((0,0,0))) # static black color

            # Interrupt services
            if eva_context['state'] == 'listening': mic.stop()
            wf.stop()
            if eva_context['state'] == 'idle_presence': pd.stop()

            try:
                audio_response = server.text_to_speech(
                    ProactivePhrases.get('single_tg_msg').format(
                        name=params["name"], msg=params["message"]
                    )
                )    
            except Exception as e: # Error in server connection
                logger.error(f'TTS failed. {str(e)}')

                eva_context['continue_conversation'] = False
                eva_context['proactive_question'] = ''
                eva_context['state'] = 'speaking'
                leds.set(LedState.breath((255,0,0))) # red breath led animation
                speaker.start(connection_error_audio)

            else:
                eva_context['continue_conversation'] = False
                eva_context['state'] = 'speaking'
                leds.set(LedState.breath((0,255,0))) # green breath led animation
                speaker.start(audio_response)
        
        else:
            # Pass message to proactive service, to read it later
            proactive.update('sensor', 'received_tg_message', params)
    
    else:
        logger.info(f'Transition {transition} discarded')



if __name__ == '__main__':
    
    leds = ArrayLed()
    eyes = Eyes(sc_width=600, sc_height=1024)
    FaceDB.load() # load face embeddings
    ProactivePhrases.load()

    wf = Wakeface(wf_event_handler)
    rf = RecordFace(rf_event_handler)
    pd = PresenceDetector(pd_event_handler)

    proactive = ProactiveService(proactive_service_event_handler)

    speaker = Speaker(speaker_event_handler)
    mic = Recorder(mic_event_handler)

    tg = TelegramService(tg_event_handler)


    pd.start()

    logger.info('Ready')
    try:
        while True:
            notification = notifications.get()

            process_transition(**notification)
    except KeyboardInterrupt:
        pass
        

    wf.stop()
    rf.stop()
    pd.stop()
    mic.destroy()
    speaker.destroy()
    leds.stop()
    eyes.stop()
    tg.stop()

    logger.info('Stopped')
