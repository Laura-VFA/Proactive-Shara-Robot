import logging
import logging.config
import queue
import threading
import concurrent.futures

from services.camera_services import (FaceDB, PresenceDetector, RecordFace,
                                     Wakeface)
from services.cloud import server
from services.eyes.service import Eyes
from services.leds import ArrayLed, LedState
from services.mic import Recorder
from services.proactive_service import ProactiveService
from services.speaker import Speaker
from services.touchscreen import TouchScreen


logging.config.fileConfig('files/logging.conf')
logger = logging.getLogger('Main')
logger.setLevel(logging.DEBUG)


robot_context = { # Eva status & knowledge of the environment
    'state':'idle', 
    'username': None, 
    'continue_conversation': False, 
    'proactive_question': '',
    'unknown_user_interactions': 0
}

notifications = queue.Queue() # Transition state queue

listen_timer = None # Listening timeout handler
DELAY_TIMEOUT = 5 # in sec

global_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10) # Global executor for async tasks (server queries)
SERVER_QUERY_TIMEOUT = 15 # in sec

# Preload of error audios
with open('files/connection_error.wav', 'rb') as f:
    connection_error_audio = f.read()


def wf_event_handler(event, usernames=None):
    global robot_context

    if event == 'face_listen' and robot_context['state'] == 'idle_presence':
        notifications.put({'transition': 'idle_presence2listening'})
    
    elif event in ['face_not_listen', 'not_faces', 'face_too_far']:
        robot_context['username'] = None

        if robot_context['state'] == 'listening':
            notifications.put({'transition': 'listening2idle_presence'})
        
    elif event == 'face_recognized':
        known_names = [name for name in usernames if name] # remove None names
        if known_names:
            # Sort names by number of consecutive frames recognized
            known_names = sorted(usernames, key=lambda name: usernames[name], reverse=True)
            robot_context['username'] = known_names[0]
            logger.info(f"Username updated to {robot_context['username']}")

            proactive.update('sensor', 'close_face_recognized', args={'username': robot_context['username']})

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
    global robot_context

    if event == 'person_detected' and robot_context['state'] == 'idle' :
        notifications.put({'transition': 'idle2idle_presence'})
    
    elif event == 'empty_room'  and robot_context['state'] == 'idle_presence' :
        notifications.put({'transition': 'idle_presence2idle'})
    
    elif event == 'person_detected_longtime' and robot_context['state'] == 'idle_presence':
        # User is in the room for a long time without looking at the robot: ask proactive question
        if not robot_context['username']: # This condition is not needed, but just in case for robustness
            proactive.update('sensor', 'presence')

def mic_event_handler(event, audio=None):
    global robot_context

    notification = {
        'transition': '',
        'params': {
            'audio': audio
        }
    }
    if event == 'start_recording' and robot_context['state'] in ['listening', 'listening_without_cam']:
        if robot_context['state'] == 'listening':
            notification['transition']  = 'listening2recording'
        elif robot_context['state'] == 'listening_without_cam':
            notification['transition']  = 'listening_without_cam2recording'
        notifications.put(notification)

    if event == 'stop_recording' and robot_context['state'] == 'recording':
        notification['transition']  = 'recording2processingquery'
        notifications.put(notification)

def speaker_event_handler(event):
    global robot_context

    if event == 'finish_speak':
        if robot_context['continue_conversation']:
            notifications.put({'transition': 'speaking2listening_without_cam'})
        
        else:
            notifications.put({'transition': 'speaking2idle_presence'})

def touchscreen_event_handler(event):
    if event == 'shutdown':
        notifications.put({'transition': 'shutdown'})

def proactive_service_event_handler(event, params={}):
    notification = {
        'transition': 'proactive2processingquery',
        'params': {
            'question': None
        }
    }

    if event == 'ask_how_are_you':
        notification ['params']['question'] = 'how_are_you'
        notification['params']['type'] = params['type']
        notification['params']['username'] = params.get('username', None)
        notifications.put(notification)
    
    elif event == 'ask_who_are_you':
        notification ['params']['question'] = 'who_are_you'
        notifications.put(notification)


def listen_timeout_handler():
    global robot_context

    if robot_context['state'] == 'listening_without_cam':
        notifications.put({'transition': 'listening_without_cam2idle_presence'})


def process_transition(transition, params={}):
    global robot_context, listen_timer

    logger.info(f'Handling transition {transition}')

    # User presence detected in the room
    if transition == 'idle2idle_presence' and robot_context['state'] == 'idle':
        robot_context['state'] = 'idle_presence'
        leds.set(LedState.static_color((186,85,211))) # set static purple color 
        wf.start()
    
    # User left the room
    elif transition == 'idle_presence2idle' and robot_context['state'] == 'idle_presence':
        robot_context['state'] = 'idle'
        robot_context['username'] = None
        leds.set(LedState.static_color((0,0,0))) # set static black color
        wf.stop()

    # User looking at the robot
    elif transition == 'idle_presence2listening' and robot_context['state'] == 'idle_presence':
        robot_context['state'] = 'listening'
        leds.set(LedState.loop((52,158,235))) # set light blue loop color
        pd.stop()
        mic.start()

    # User stopped looking at the robot
    elif transition == 'listening2idle_presence' and robot_context['state'] == 'listening':
        robot_context['state'] = 'idle_presence'
        robot_context['username'] = None
        leds.set(LedState.static_color((0,0,0))) # set static black color
        mic.stop()
        pd.start()

    # User looking at the robot starts talking
    elif transition == 'listening2recording' and robot_context['state'] == 'listening':
        robot_context['state'] = 'recording'
        leds.set(LedState.loop((255,255,255))) # set white loop color
        wf.stop()
        try:
            server.load_conversation_db(robot_context['username']) # Load conversation history for that user
        except Exception as e:
            logger.warning(f'Could not load conversation history. {str(e)}') 
    
    # User in conversation starts talking
    elif transition == 'listening_without_cam2recording' and robot_context['state'] == 'listening_without_cam':
        robot_context['state'] = 'recording'
        leds.set(LedState.loop((255,255,255))) # set white loop color
        listen_timer.cancel()

    # User finished talking: sending audio to server
    elif transition == 'recording2processingquery' and robot_context['state'] == 'recording':
        robot_context['state'] = 'processing_query'
        leds.set(LedState.static_color((0,0,0)))
        mic.stop()

        audio = params['audio']

        future = global_executor.submit(
            server.query,  # Make the query to the cloud
            server.Request(audio, username=robot_context['username'], proactive_question=robot_context['proactive_question'])
        )
        try:
            response = future.result(timeout=SERVER_QUERY_TIMEOUT) # Wait for the response
        except concurrent.futures.TimeoutError: # Timeout error: play error msg
            logger.error('Timeout error in query processing')

            robot_context['continue_conversation'] = False
            robot_context['proactive_question'] = ''
            robot_context['state'] = 'speaking'
            leds.set(LedState.breath((255,0,0))) # set breath red animation
            speaker.start(connection_error_audio)

        except Exception as e: # Unable to connect to the server: play error msg
            logger.error(f'Could not make the query. {str(e)}')

            robot_context['continue_conversation'] = False
            robot_context['proactive_question'] = ''
            robot_context['state'] = 'speaking'
            leds.set(LedState.breath((255,0,0))) # set breath red animation
            speaker.start(connection_error_audio)

        else:
            if response:
                if response.action: # Execute associated action
                    if response.action == 'record_face':
                        robot_context['username'] = response.username
                        rf.start(response.username)
                        proactive.update('confirm', 'recorded_face', {'username': response.username})
                    
                    elif response.action == 'set_username':
                        logger.info(f"Updating username to {response.username} (proactive presence conversation - N interactions {robot_context['unknown_user_interactions']})")
                        
                        robot_context['username'] = response.username
                        robot_context['unknown_user_interactions'] = 0 # Reset unknown user interactions counter
                        try:
                            server.load_conversation_db(robot_context['username'])
                        except Exception as e:
                            logger.warning(f'Could not load conversation history. {str(e)}') 


                robot_context['continue_conversation'] = response.continue_conversation
                robot_context['proactive_question'] = ''

                # Reproduce response                
                robot_context['state'] = 'speaking'
                eyes.set(response.robot_mood)
                leds.set(LedState.breath((52,158,235))) # light blue breath
                speaker.start(response.audio)

                if not robot_context['username']: # Unknown user
                    robot_context['unknown_user_interactions'] += 1

                    if robot_context['unknown_user_interactions'] >= 1: # consecutive interactions with unknown user
                        robot_context['proactive_question'] = 'casual_ask_known_username'

                        logger.info(f"Time to ask casual_ask_known_username (proactive presence conversation - N interactions {robot_context['unknown_user_interactions']})")

            elif robot_context['continue_conversation']: # Avoid end the conversation due to noises
                logger.info(f'Not text in audio, continuing conversation')
                logger.info(f'Handling transition processing_query2listening_without_cam')

                robot_context['state'] = 'listening_without_cam'
                leds.set(LedState.loop((52,158,235))) # light blue loop
                mic.start()

                # Add a timeout to execute a transition function due to inactivity
                listen_timer = threading.Timer(DELAY_TIMEOUT, listen_timeout_handler)
                listen_timer.start()

            else:
                logger.info(f'Not text in audio, back to idle')
                logger.info(f'Handling transition processing_query2idle_presence')

                robot_context['state'] = 'idle_presence'
                robot_context['username'] = None
                robot_context['proactive_question'] = ''           
                eyes.set('neutral')
                leds.set(LedState.static_color((0,0,0))) # put black static color
                pd.start()
                wf.start()

    # Continue conversation after robot speaks: waiting for user audio
    elif transition == 'speaking2listening_without_cam' and robot_context['state'] == 'speaking':
        robot_context['state'] = 'listening_without_cam'
        leds.set(LedState.loop((52,158,235))) # light blue color
        mic.start()

        # Add a timeout to execute a transition funcion due to inactivity
        listen_timer = threading.Timer(DELAY_TIMEOUT, listen_timeout_handler)
        listen_timer.start()

    # Conversation finishes due to goodbye
    elif transition == 'speaking2idle_presence' and robot_context['state'] == 'speaking':
        try:
            server.dump_conversation_db(robot_context['username']) # Update conversation history database
        except Exception as e:
            logger.warning(f'Could not dump conversation database. {str(e)}') 
        
        proactive.update('new_timer', 'how_are_you', {'username': robot_context['username']})

        robot_context['state'] = 'idle_presence' 
        robot_context['username'] = None
        robot_context['proactive_question'] = ''
        robot_context['continue_conversation'] = False
        robot_context['unknown_user_interactions'] = 0
        eyes.set('neutral')
        leds.set(LedState.static_color((0,0,0))) # put black static color
        rf.stop()
        pd.start()
        wf.start()
    
    # Conversation finishes due to timeout waiting for user audio
    elif transition == 'listening_without_cam2idle_presence'and robot_context['state'] == 'listening_without_cam':

        try:
            server.dump_conversation_db(robot_context['username']) # Update conversation history database
        except Exception as e:
            logger.warning(f'Could not dump conversation database. {str(e)}') 
        
        proactive.update('new_timer', 'how_are_you', {'username': robot_context['username']})

        robot_context['state'] = 'idle_presence' 
        robot_context['username'] = None
        robot_context['proactive_question'] = ''
        robot_context['continue_conversation'] = False
        robot_context['unknown_user_interactions'] = 0
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
            if robot_context['state'] in ['idle_presence', 'listening']:
                robot_context['state'] = 'processing_query'
                leds.set(LedState.static_color((0,0,0))) # put black static color

                # Interrupt services
                wf.stop()
                pd.stop()
                mic.stop()

                robot_context['username'] = params.get('username', None) # Get the username from params

                try:
                    server.load_conversation_db(robot_context['username']) # Load conversation history for that user
                except Exception as e:
                    logger.warning(f'Could not load conversation history. {str(e)}') 

                future = global_executor.submit(
                    server.proactive_query, # Make the query to the cloud
                    server.Request(
                        username=robot_context['username'], 
                        proactive_question='how_are_you'
                    )
                )

                try:
                    response = future.result(timeout=SERVER_QUERY_TIMEOUT) # Wait for the response

                except concurrent.futures.TimeoutError: # Timeout error: play error msg
                    logger.error('Timeout error in proactive query processing')

                    robot_context['continue_conversation'] = False
                    robot_context['proactive_question'] = ''
                    robot_context['state'] = 'speaking'
                    leds.set(LedState.breath((255,0,0))) # set breath red animation
                    speaker.start(connection_error_audio)

                except Exception as e: # Unable to connect to the server: play error msg
                    logger.error(f'Could not make the proactive query. {str(e)}')

                    robot_context['continue_conversation'] = False
                    robot_context['proactive_question'] = ''
                    robot_context['state'] = 'speaking'
                    leds.set(LedState.breath((255,0,0))) # set breath red animation
                    speaker.start(connection_error_audio)

                else: # Asked question
                    robot_context['continue_conversation'] = True
                    robot_context['state'] = 'speaking'
                    leds.set(LedState.breath((52,158,235))) # light blue led breath animation
                    speaker.start(response.audio)

                    proactive.update('confirm', 'how_are_you', {'type': params['type'], 'username': robot_context['username']})
            
        elif params['question'] == 'who_are_you':
            if robot_context['state'] == 'listening':
                robot_context['state'] = 'processing_query'
                leds.set(LedState.static_color((0,0,0))) # set static black color

                # Interrupt services
                mic.stop()
                wf.stop()

                future = global_executor.submit(
                    server.proactive_query, # Make the query to the cloud
                    server.Request(
                        username=robot_context['username'], 
                        proactive_question='who_are_you'
                    )
                )

                try:
                    response = future.result(timeout=SERVER_QUERY_TIMEOUT) # Wait for the response

                except concurrent.futures.TimeoutError: # Timeout error: play error ms
                    logger.error('Timeout error in proactive query processing')

                    robot_context['continue_conversation'] = False
                    robot_context['proactive_question'] = ''
                    robot_context['state'] = 'speaking'
                    leds.set(LedState.breath((255,0,0)))
                    speaker.start(connection_error_audio)

                except Exception as e: # Error in server connection
                    logger.error(f'Could not make the proactive query. {str(e)}')

                    robot_context['continue_conversation'] = False
                    robot_context['proactive_question'] = ''
                    robot_context['state'] = 'speaking'
                    leds.set(LedState.breath((255,0,0))) # red breath animation
                    speaker.start(connection_error_audio)

                else:
                    robot_context['proactive_question'] = 'who_are_you_response'
                    robot_context['continue_conversation'] = True
                    robot_context['state'] = 'speaking'
                    leds.set(LedState.breath((52,158,235))) # light blue led breath animation
                    speaker.start(response.audio)
                    try:
                        server.load_conversation_db(robot_context['username']) # Load conversation history for that user
                    except Exception as e:
                        logger.warning(f'Could not load conversation history. {str(e)}') 

                    proactive.update('confirm', 'who_are_you')


    # Record new user face
    elif transition == 'recording_face':
        logger.info(f"Recording progress: {params['progress']:.2f}; Current state: {robot_context['state']}")

        leds.set(LedState.progress((0,255,0), percentage=params['progress'])) # percentage leds in green color

        if params['progress'] == 100: # Recording completed
            rf.stop()
            if robot_context['state'] in ['listening_without_cam', 'listening']:
                leds.set(LedState.loop((52,158,235))) # light loop blue animation
            elif robot_context['state'] == 'recording':
                leds.set(LedState.loop((255,255,255))) # white loop animation
            else:
                leds.set(LedState.static_color((0,0,0))) # static black color

    else:
        logger.info(f'Transition {transition} discarded')


if __name__ == '__main__':
    
    leds = ArrayLed()
    eyes = Eyes(sc_width=600, sc_height=1024)
    FaceDB.load() # load face embeddings

    wf = Wakeface(wf_event_handler)
    rf = RecordFace(rf_event_handler)
    pd = PresenceDetector(pd_event_handler)

    proactive = ProactiveService(proactive_service_event_handler)

    speaker = Speaker(speaker_event_handler)
    mic = Recorder(mic_event_handler)
    touch = TouchScreen(touchscreen_event_handler)

    touch.start()
    pd.start()

    logger.info('Ready')
    try:
        while True:
            notification = notifications.get()

            if notification.get('transition') == 'shutdown':
                break # Finish the execution due to finish event

            process_transition(**notification)

    except KeyboardInterrupt:
        pass

    finally:
        logger.info("Interruption detected. Stopping and shutting down the robot...")
    
        with open('files/powerdown_sound.wav', 'rb') as f:
            powerdown_audio = f.read()
        
        speaker.start(powerdown_audio) # play goodbye audio

        touch.stop()

        server.dump_conversation_db(robot_context['username']) # dump in-RAM conversation history before exit

        eyes.set('neutral_closed') # close eyes animation

        global_executor.shutdown(wait=False) # shutdown global executor

        wf.stop()
        rf.stop()
        pd.stop()
        mic.destroy()
        speaker.destroy()
        leds.stop()
        eyes.stop()

        logger.info('Stopped')
