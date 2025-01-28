import json
from openai import OpenAI


client = OpenAI()

thread_id = ''
assistant_id = ''

# Assistant description (personlaity prompt)
shara_descrip = ''
with open("files/shara_prompt.txt", "r") as f:
    shara_descrip = f.read()


# Asssistant functions
def create_assistant_thread(name="SHARA", instructions=shara_descrip, tools=[], model="gpt-4o-mini"):
    global assistant_id, thread_id
    assistant = client.beta.assistants.create(
        name=name,
        instructions=instructions,
        tools=tools,
        model=model
    )
    assistant_id = assistant.id

    # Create a thread (conversation) for the assistant
    thread = create_thread()
    thread_id = thread.id

    # Save assistant and thread ids for future use
    save_assistant_data(assistant_id, thread_id)

    return assistant, thread

def get_assistant(assistant_id):
    return client.beta.assistants.retrieve(assistant_id)

def delete_assistant(assistant_id):
    return client.beta.assistants.delete(assistant_id)

def list_assistants():
    return client.beta.assistants.list(order="desc", limit=20).data


# Thread functions
def create_thread():
    return client.beta.threads.create()

def get_thread(thread_id):
    return client.beta.threads.retrieve(thread_id)

def delete_thread(thread_id):
    return client.beta.threads.delete(thread_id)


# Function to prepare the assistant and thread for interaction
def prepare_assistant_thread():
    global assistant_id, thread_id

    if not assistant_id: # Assistant is not loaded
        assistant_id, thread_id = load_assistant_data()

        if not assistant_id: # No existing assistant
            assistant, thread = create_assistant_thread()
            assistant_id = assistant.id
            thread_id = thread.id
            save_assistant_data(assistant_id, thread_id)

        elif not thread_id: # There is assistant but not thread
            thread = create_thread()
            thread_id = thread.id
            save_thread_id(thread_id)

    


def generate_response(input_text, context_data={}):
    global thread_id, assistant_id

    if not input_text:
        return None

    # Cereate message in the thread
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=json.dumps({**context_data, "user_input": input_text})
    )

    robot_context = ""
    with client.beta.threads.runs.stream(
        thread_id=thread_id,
        assistant_id=assistant_id
    ) as stream:
        robot_context = json.loads(''.join(text for text in stream.text_deltas))
    
    response = robot_context.pop("response", "")    
    
    return response, robot_context




# Utils
def save_assistant_data(assistant_id, thread_id, file_path="files/assistant_data.json"):
    with open(file_path, "w") as f:
        json.dump({"assistant_id": assistant_id, "thread_id": thread_id}, f)

def load_assistant_data(file_path="files/assistant_data.json"):
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
            print(data)
            return data.get("assistant_id"), data.get("thread_id")
    except (FileNotFoundError, json.JSONDecodeError):
        return None, None

def load_thread_id(file_path="files/assistant_data.json"):
    _, thread_id = load_assistant_data(file_path)
    return thread_id

def save_thread_id(thread_id, file_path="files/assistant_data.json"):
    assistant_id, _ = load_assistant_data(file_path)
    save_assistant_data(assistant_id, thread_id)

