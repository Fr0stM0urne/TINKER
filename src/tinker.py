from src import penguin
from pathlib import Path

def start_analysis(config, args):
    # Generate initial Penguin configuration
    if not Path(args.penguin_proj).exists():
        penguin.penguin_init(config, args.fw)
    # First Penguin run
    penguin.penguin_run(config, args.penguin_proj)




    