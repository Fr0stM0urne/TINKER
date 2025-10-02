from ollama import chat
from ollama import ChatResponse

def stream_chat(config, query):
    stream = chat(
    model=config['Ollama']['model'],
    messages=[{'role': 'user', 'content': query}],
    stream=True,
    )
    for chunk in stream:
        print(chunk['message']['content'], end='', flush=True)
    print()

def chat_llm(config, query):
    response: ChatResponse = chat(model=config['Ollama']['model'], messages=[
        {
            'role': 'user',
            'content': query,
        },
    ])
    print(response['message']['content'])
