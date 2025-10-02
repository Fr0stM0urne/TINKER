import argparse
import configparser
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from src.tinker import start_analysis

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Firmware input and log output.")
    parser.add_argument("--fw", required=True, metavar="PATH", help="Firmware rootfs path.")
    parser.add_argument(
        "--log",
        metavar="PATH",
        help="Log file path. Defaults to logs/<firmware file name>.log",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        default="config.ini",
        help="Configuration file path (INI format). Defaults to config.ini",
    )
    args = parser.parse_args()

    firmware_path = Path(args.fw)
    firmware_name = firmware_path.stem.split(".")[0]
    log_path = Path(args.log) if args.log else Path("logs") / f"{firmware_name}.log"
    config_path = Path(args.config)

    args.fw = firmware_path
    args.fw_name = firmware_name
    args.log = log_path
    args.config = config_path
    return args

def load_config(config_path: Path) -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    config.read(config_path)
    return config

def main() -> None:
    load_dotenv(find_dotenv(usecwd=True))
    args = parse_arguments()
    config = load_config(args.config)
    args.penguin_proj = Path(f"{config['Penguin']['output_dir']}/{args.fw_name}")
    print(f"FW: {args.fw}, Log: {args.log}, Model: {config['Ollama']['model']}")
    start_analysis(config, args)

if __name__ == "__main__":
    main()
