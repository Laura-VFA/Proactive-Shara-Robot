import json
from datetime import datetime
from openai import OpenAI  
from pydantic import BaseModel, Field

client = OpenAI()

prev_conversation_history = [] # Conversation history from previous sessions (from file)
current_conversation_history = [] # Conversation history from current session (new current interaction)

# Load prompt from file
def load_prompt(filename="files/shara_prompt.txt"):
    with open(filename, "r", encoding="utf-8") as file:
        return file.read().strip()

# Load function tools from file
def load_tools(filename="files/tools_config.json"):
    with open(filename, "r", encoding="utf-8") as file:
        return json.load(file)

# Load and save conversation history
def load_conversation_history(username, filename="files/conversations_db.json"):
    global prev_conversation_history

    if username:
        try:
            with open(filename, "r", encoding="utf-8") as file:
                conversation_dict = json.load(file)
                prev_conversation_history = conversation_dict.get(username, [])
        except (FileNotFoundError, json.JSONDecodeError):
            prev_conversation_history = []
    
    else:
        prev_conversation_history = []

def save_conversation_history(username, filename="files/conversations_db.json"):
    if current_conversation_history: # Save only if there is conversation history to save
        if username: # Save conversation history only if username is provided
            conversation_dict = {}

            try:
                with open(filename, "r", encoding="utf-8") as file:
                    conversation_dict = json.load(file)
            except (FileNotFoundError, json.JSONDecodeError):
                conversation_dict = {}

            # Update conversation history
            conversation_dict.setdefault(username, []).extend(current_conversation_history)

            # Save conversation history to file
            with open(filename, "w", encoding="utf-8") as file:
                json.dump(conversation_dict, file, ensure_ascii=False, indent=4)
        
        else: # Save conversation history to unknown user database. -- ONLY FOR TESTING PURPOSES --
            try:
                with open('files/conversations_unknown_db.json', "r", encoding="utf-8") as file:
                    try:
                        conversation = json.load(file)
                    except json.JSONDecodeError:
                        conversation = [] 
            except FileNotFoundError:
                conversation = [] 

            conversation.extend(current_conversation_history)

            with open('files/conversations_unknown_db.json', "w", encoding="utf-8") as file:
                json.dump(conversation, file, ensure_ascii=False, indent=4)

def get_full_conversation_history():
    return prev_conversation_history + current_conversation_history

# Clear conversation history in-RAM (temporal context conversation)
def clear_conversation_history():
    prev_conversation_history.clear()
    current_conversation_history.clear()


shara_prompt = load_prompt()
tools = load_tools()


# JSON Schema for response format
class ResponseFormat(BaseModel):
    continue_conversation: bool = Field(alias="continue")
    robot_mood: str
    response: str

# OpenAI completion arguments configuration
completion_args = {
    "model": "gpt-4o-mini",
    "text_format": ResponseFormat,
    "temperature": 1,
    "top_p": 1,
    "instructions": shara_prompt,
    "truncation": "auto" # Truncate messages automatically if they exceed the model's context length
}



def handle_tool_call(tool_call, context_data):
    ''' Tool (functions) calling handler. Process tool calls and return the result and robot action if needed '''

    tool_name = tool_call.name
    args = json.loads(tool_call.arguments)

    result = ''
    robot_action = {}

    if tool_name == "record_face" and context_data.get("proactive_question") == "who_are_you_response":
        username = args.get("username", 'Desconocido')
        if username != 'Desconocido':
            result = 'True'
            robot_action = {"action": "record_face", "username": args['username']} 
        else:
            result = 'False'
    
    elif tool_name == "set_username":
        username = args.get("username", 'Desconocido')
        if username != 'Desconocido':
            result = 'True'
            robot_action = {"action": "set_username", "username": args['username']}
        else:
            result = 'False'
    
    return result, robot_action


def build_messages(input_text, context_data):
    ''' Build messages with conversation history '''

    messages = prev_conversation_history + current_conversation_history # include previous conversation history
    user_message = {"role": "user", "content": json.dumps({**context_data,
                                                           "user_input": input_text,
                                                           "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M")}, ensure_ascii=False)}

    messages.append(user_message)
    current_conversation_history.append(user_message)

    return messages


def get_tools_for_context(context_data):
    ''' Return tools to use based on context data '''
    # Filter who_are_you proactive question (avoid unnecessary record_face tool)
    pq = context_data.get("proactive_question", None)
    tools_to_use = []
    requireness = None

    if pq == "who_are_you_response":
        tools_to_use = [t for t in tools if t["name"] == "record_face"]
        requireness = "required"
    
    elif pq == "casual_ask_known_username":
        tools_to_use = [t for t in tools if t["name"] == "set_username"]
        requireness = "auto"

    return tools_to_use, requireness


def generate_response(input_text, context_data={}):
    ''' Generate response from user input, context data, and conversation history '''
    
    messages = build_messages(input_text, context_data)
    tools_to_use, requireness_tool = get_tools_for_context(context_data)

    # Create OpenAI completion arguments
    completion_args["input"] = messages
    if tools_to_use:  # Only add 'tools' if there are tools available
        completion_args["tools"] = tools_to_use
        completion_args["tool_choice"] = requireness_tool

    robot_action = {}
    response = client.responses.parse(**completion_args)

    # Check if there is a function call in the list of response.output
    if any(item.type == "function_call" for item in response.output):
        tool_call = next(item for item in response.output if item.type == "function_call")
        result, robot_action = handle_tool_call(tool_call, context_data)

        messages.append(tool_call) # append model's function call message
        messages.append({                   # append function result message
            "type": "function_call_output",
            "call_id": tool_call.call_id,
            "output": result
        })

        completion_args.pop("tool_choice", None)  # Remove tools
        completion_args.pop("tools", None)

        response = client.responses.parse(**completion_args)
    
    # Get response dict from OpenAI response
    response_dict = response.output_parsed.model_dump(by_alias=True)
    
    response_text = response_dict.get("response", "").translate(str.maketrans("'", '"', '*_#'))
    
    # Add response to conversation history
    current_conversation_history.append({"role": "assistant", "content": response_text})

    # Build robot_context from parsed data (continue, robot_mood, robot_action)
    robot_context = {
        "continue": response_dict.get("continue", False),
        "robot_mood": response_dict.get("robot_mood", "neutral"),
    } | robot_action
    
    return response_text, robot_context
