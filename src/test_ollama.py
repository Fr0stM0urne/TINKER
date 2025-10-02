import sys
import os
import signal
import time
import json
import ollama


SECRET = {}

def get_current_secret(key: str) -> str:
    if key not in SECRET:
        SECRET[key] = os.getenv(key, "default_secret")
    return SECRET[key]

def set_current_secret(key: str, value: str) -> None:
    SECRET[key] = value
    return value


def main() -> None:
    # Allow overriding model via env, default to a widely available one
    model_name = os.getenv("OLLAMA_MODEL", "llama3.3:70b-instruct-q2_K")
    debug = os.getenv("DEBUG", "").lower() in {"1", "true", "yes"}

    # Initialize client; select model per-request
    client = ollama.Client()

    # Conversation history
    messages = []
    
    # Define tools for the model
    tools = [
        {
            'type': 'function',
            'function': {
                'name': 'get_current_secret',
                'description': 'Retrieve the current value of a secret by key. Returns the secret value stored for the given key.',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'key': {
                            'type': 'string',
                            'description': 'The key name of the secret to retrieve',
                        },
                    },
                    'required': ['key'],
                },
            },
        },
        {
            'type': 'function',
            'function': {
                'name': 'set_current_secret',
                'description': 'Store or update a secret value for a given key. Returns the value that was set.',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'key': {
                            'type': 'string',
                            'description': 'The key name for the secret',
                        },
                        'value': {
                            'type': 'string',
                            'description': 'The secret value to store',
                        },
                    },
                    'required': ['key', 'value'],
                },
            },
        },
    ]

    # Track Ctrl+C presses for double-press detection
    last_interrupt_time = [0.0]  # Use list to allow modification in nested function
    
    # Graceful Ctrl+C handling with double-press to force quit
    def handle_sigint(_signum, _frame):
        current_time = time.time()
        time_since_last = current_time - last_interrupt_time[0]
        
        if time_since_last < 2.0:  # Double press within 2 seconds
            print("\n[Force quitting...]")
            sys.exit(0)
        else:
            print("\nPress Ctrl+C again within 2 seconds to force quit, or use /exit to quit gracefully.")
            last_interrupt_time[0] = current_time
    
    signal.signal(signal.SIGINT, handle_sigint)

    print("Interactive Ollama chat. Type /exit to quit, /reset to clear history.")
    if debug:
        print(f"[DEBUG mode enabled, using model: {model_name}]")
    print()

    # Ensure model is available locally; attempt to pull if missing
    try:
        # Lightweight check; if not found, this raises
        client.show(model=model_name)
    except Exception:
        print(f"[info] Ensuring model '{model_name}' is available (pulling if needed)...")
        try:
            for chunk in client.pull(model=model_name, stream=True):
                status = chunk.get("status") if isinstance(chunk, dict) else None
                percent = chunk.get("percent") if isinstance(chunk, dict) else None
                if status and percent is not None:
                    print(f"  {status}: {percent}%", end="\r", flush=True)
            print()
        except Exception as pull_err:
            print(f"[warning] Could not pull model '{model_name}': {pull_err}")
            print("You can set OLLAMA_MODEL or pre-pull a model, e.g.: 'ollama pull llama3:8b'")

    while True:
        try:
            user_input = input("You: ")
        except EOFError:
            print()
            break

        if not user_input.strip():
            continue

        # Commands
        if user_input.strip().lower() in {"/exit", ":q", ":wq"}:
            break
        if user_input.strip().lower() == "/reset":
            messages = []
            print("[conversation reset]")
            continue

        # Add user message
        messages.append({"role": "user", "content": user_input})

        # Loop to handle tool calls
        while True:
            # Stream assistant response
            print("Assistant: ", end="", flush=True)
            assistant_reply = []
            tool_calls_list = []
            
            try:
                for chunk in client.chat(model=model_name, messages=messages, tools=tools, stream=True):
                    if debug:
                        print(f"\n[DEBUG chunk: {chunk}]\n", file=sys.stderr)
                    
                    content = ""
                    # The ollama python client returns objects, not dicts
                    # Access attributes directly: chunk.message.content
                    try:
                        if hasattr(chunk, 'message') and chunk.message:
                            content = getattr(chunk.message, 'content', '')
                            # Check for tool calls
                            if hasattr(chunk.message, 'tool_calls') and chunk.message.tool_calls:
                                tool_calls_list = chunk.message.tool_calls
                        # Fallback for dict-style responses
                        elif isinstance(chunk, dict):
                            message = chunk.get("message")
                            if isinstance(message, dict):
                                content = message.get("content", "")
                                if message.get("tool_calls"):
                                    tool_calls_list = message.get("tool_calls", [])
                            elif hasattr(message, 'content'):
                                content = message.content
                                if hasattr(message, 'tool_calls') and message.tool_calls:
                                    tool_calls_list = message.tool_calls
                    except (AttributeError, TypeError):
                        pass
                    
                    if content:
                        assistant_reply.append(content)
                        print(content, end="", flush=True)
            except Exception as e:
                print(f"\n[error: {e}]", file=sys.stderr)
                # remove the last user message if the request failed
                messages.pop()
                break

            print()  # newline after streaming completes

            # If streaming yielded nothing, fallback to non-streaming call
            if not assistant_reply and not tool_calls_list:
                try:
                    resp = client.chat(model=model_name, messages=messages, tools=tools, stream=False)
                    if debug:
                        print(f"\n[DEBUG fallback response: {resp}]\n", file=sys.stderr)
                    
                    fallback_text = ""
                    # Access as object attribute: resp.message.content
                    try:
                        if hasattr(resp, 'message') and resp.message:
                            fallback_text = getattr(resp.message, 'content', '')
                            if hasattr(resp.message, 'tool_calls') and resp.message.tool_calls:
                                tool_calls_list = resp.message.tool_calls
                        # Fallback for dict-style responses
                        elif isinstance(resp, dict):
                            message = resp.get("message")
                            if isinstance(message, dict):
                                fallback_text = message.get("content", "")
                                if message.get("tool_calls"):
                                    tool_calls_list = message.get("tool_calls", [])
                            elif hasattr(message, 'content'):
                                fallback_text = message.content
                                if hasattr(message, 'tool_calls') and message.tool_calls:
                                    tool_calls_list = message.tool_calls
                    except (AttributeError, TypeError):
                        pass
                    
                    if fallback_text:
                        print(fallback_text)
                        assistant_reply.append(fallback_text)
                    elif not tool_calls_list:
                        print("[no content received]")
                except Exception as e:
                    print(f"[error on fallback: {e}]", file=sys.stderr)

            # Persist assistant message to history
            full_reply = "".join(assistant_reply)
            messages.append({"role": "assistant", "content": full_reply})
            
            # Handle tool calls if present
            if tool_calls_list:
                if debug:
                    print(f"[DEBUG tool_calls: {tool_calls_list}]", file=sys.stderr)
                
                # Execute each tool call
                for tool_call in tool_calls_list:
                    # Extract function name and arguments
                    func_name = None
                    func_args = {}
                    
                    if hasattr(tool_call, 'function'):
                        func_name = getattr(tool_call.function, 'name', None)
                        args_str = getattr(tool_call.function, 'arguments', '{}')
                        try:
                            func_args = json.loads(args_str) if isinstance(args_str, str) else args_str
                        except json.JSONDecodeError:
                            func_args = {}
                    elif isinstance(tool_call, dict):
                        function = tool_call.get('function', {})
                        func_name = function.get('name')
                        args_str = function.get('arguments', '{}')
                        try:
                            func_args = json.loads(args_str) if isinstance(args_str, str) else args_str
                        except json.JSONDecodeError:
                            func_args = {}
                    
                    if debug:
                        print(f"[DEBUG executing: {func_name}({func_args})]", file=sys.stderr)
                    
                    # Execute the tool function
                    result = None
                    try:
                        if func_name == 'get_current_secret':
                            result = get_current_secret(func_args.get('key', ''))
                            print(f"[Tool: get_current_secret(key='{func_args.get('key')}') -> '{result}']")
                        elif func_name == 'set_current_secret':
                            result = set_current_secret(func_args.get('key', ''), func_args.get('value', ''))
                            print(f"[Tool: set_current_secret(key='{func_args.get('key')}', value='{func_args.get('value')}') -> '{result}']")
                        else:
                            result = f"Unknown function: {func_name}"
                    except Exception as tool_err:
                        result = f"Error executing {func_name}: {tool_err}"
                    
                    # Add tool result to messages
                    messages.append({
                        "role": "tool",
                        "content": str(result),
                    })
                
                # Continue the loop to get the model's response after tool execution
                continue
            else:
                # No tool calls, exit the loop
                break




if __name__ == "__main__":
    main()