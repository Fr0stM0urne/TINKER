from src import penguin, ollama
from pathlib import Path

def start_analysis(config, args):
    # init_penguin(config, args)
    init_ollama(config, args)
    ollama.stream_chat(config, "What is your name?")

def init_ollama(config, args):
    # Initialize Ollama model (if needed)
    pass

def init_penguin(config, args):
    # Generate initial Penguin configuration
    if not Path(args.penguin_proj).exists():
        penguin.penguin_init(config, args.fw)
    # First Penguin run
    penguin.penguin_run(config, args.penguin_proj)
