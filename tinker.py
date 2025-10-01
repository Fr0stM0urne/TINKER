import argparse
import configparser
from pathlib import Path
from dotenv import load_dotenv, find_dotenv


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
    log_path = Path(args.log) if args.log else Path("logs") / f"{firmware_path.stem}.log"
    config_path = Path(args.config)

    args.fw = firmware_path
    args.log = log_path
    args.config = config_path
    return args


def load_config(config_path: Path) -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    config.read(config_path)
    return config


def ensure_log_directory(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)


def main() -> None:
    load_dotenv(find_dotenv(usecwd=True))
    args = parse_arguments()
    ensure_log_directory(args.log)
    config = load_config(args.config)

    print(f"Firmware path: {args.fw}")
    print(f"Log path: {args.log}")
    print(f"Loaded config sections: {', '.join(config.sections()) or '(none)'}")


if __name__ == "__main__":
    main()
