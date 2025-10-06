from src.penguin import PenguinClient
from pathlib import Path

def start_analysis(config, args):
    # init_penguin(config, args)
    init_ollama(config, args)
    # ollama imports removed - to be integrated with LLM framework

def init_ollama(config, args):
    # Initialize Ollama model (if needed)
    pass

def init_penguin(config, args):
    """Initialize and run Penguin using the client API."""
    client = PenguinClient(config)
    
    # Check if we need to initialize or use existing project
    if hasattr(args, 'penguin_proj') and args.penguin_proj and Path(args.penguin_proj).exists():
        # Use existing project path
        project_path = Path(args.penguin_proj)
        print(f"Using existing project at: {project_path}")
    else:
        # Initialize firmware and auto-detect project path
        init_result, project_path = client.init(args.fw)
        
        if init_result.returncode != 0:
            print(f"[Error] Penguin initialization failed")
            return
        
        if project_path is None:
            print(f"[Error] Could not detect project path from penguin init output")
            return
        
        print(f"Initialized project at: {project_path}")
    
    # Run Penguin on the project
    client.run(project_path)
