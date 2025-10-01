import argparse
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
    args = parser.parse_args()
    firmware_path = Path(args.fw)
    log_path = Path(args.log) if args.log else Path("logs") / f"{firmware_path.stem}.log"
    args.fw = firmware_path
    args.log = log_path
    return args

if __name__ == "__main__":

    args = parse_arguments()
    print(args)
