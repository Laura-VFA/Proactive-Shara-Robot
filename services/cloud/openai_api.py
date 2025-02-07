import json
from openai import OpenAI  

client = OpenAI()

# Load prompt from file
def load_prompt(filename="files/shara_prompt.txt"):
    with open(filename, "r", encoding="utf-8") as file:
        return file.read().strip()

# Load function tools from file
def load_tools(filename="files/tools_config.json"):
    with open(filename, "r", encoding="utf-8") as file:
        return json.load(file)


shara_prompt = load_prompt()
tools = load_tools()
conversation_history = []

# OpenAI completion arguments configuration
completion_args = {
    "model": "gpt-4o-mini",
    "response_format": {'type': "json_object"},
    "store": True,
    "temperature": 1,
    "top_p": 1
}



def handle_tool_call(tool_call, context_data):
    ''' Tool (functions) calling handler. Process tool calls and return the result and robot action if needed '''

    tool_name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)

    result = ''
    robot_action = {}

    if tool_name == "record_face" and context_data.get("proactive_question") == "who_are_you":
        username = args.get("username", 'Desconocido')
        if username != 'Desconocido':
            result = 'True'
            robot_action = {"action": "record_face", "username": args['username']} 
        else:
            result = 'False'
    
    return result, robot_action


def build_messages(input_text, context_data):
    ''' Build messages with conversation history '''

    messages = [{"role": "developer", "content": shara_prompt}] + conversation_history # include conversation history
    user_message = {"role": "user", "content": json.dumps({**context_data, "user_input": input_text})}

    messages.append(user_message)
    conversation_history.append(user_message)

    return messages


def get_tools_for_context(context_data):
    ''' Return tools to use based on context data '''
    # Filter who_are_you proactive question (avoid unnecessary record_face tool)
    tools_to_use = tools if context_data.get("proactive_question") == "who_are_you" else [
        tool for tool in tools if tool["function"]["name"] != "record_face"
    ]

    return tools_to_use


def generate_response(input_text, context_data={}):
    ''' Generate response from user input, context data, and conversation history '''
    if not input_text:
        return None
    
    messages = build_messages(input_text, context_data)
    tools_to_use = get_tools_for_context(context_data)

    # Create OpenAI completion arguments
    completion_args["messages"] = messages
    if tools_to_use:  # Only add 'tools' if there are tools available
        completion_args["tools"] = tools_to_use

    robot_action = {}
    response = client.chat.completions.create(**completion_args)

    if response.choices[0].message.tool_calls:
        tool_call = response.choices[0].message.tool_calls[0]
        result, robot_action = handle_tool_call(tool_call, context_data)

        messages.append(response.choices[0].message)  # append model's function call message
        messages.append({                               # append result message
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result
        })

        response = client.chat.completions.create(**completion_args)
    
    # Extract response text from OpenAI response
    response_text = response.choices[0].message.content

    # Add response to conversation history
    conversation_history.append({"role": "assistant", "content": response_text})

    try:
        robot_context = json.loads(response_text)
    except json.JSONDecodeError:
        robot_context = {}

    response_text = robot_context.pop("response", "")
    robot_context = robot_context | robot_action

    return response_text, robot_context
