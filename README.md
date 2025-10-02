# TINKER

TINKER is a small command-line utility that prepares firmware analysis inputs.

## Features

- Argument parsing with sensible defaults:
	- `--fw` (required): firmware rootfs archive path.
	- `--log` (optional): log file path; defaults to `logs/<firmware-name>.log`.
	- `--config` (optional): configuration file; defaults to `config.ini`.
- `projects` folder will host the penguin rehosting output

## Requirements

- Python 3.8 or newer (matching the provided virtual environment).
- External packages listed in `requirements.txt`
- Penguin rehosting tool

## Quick Start

```bash
# create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# install dependencies
pip install -r requirements.txt

# run the CLI with a firmware image
python tinker.py --fw temp/firmware/stride.rootfs.tar.gz
```

## Configuration

- **Environment Variables:** Place them in a `.env` file at the project root. They are loaded automatically with `find_dotenv(usecwd=True)`.
- **INI File (`config.ini`):** Houses application settings. The default file includes sections such as:

	```ini
	[Ollama]
	model = llama3:8b

	[Penguin]
	version = v2.1.14
	```

	Supply a different INI file with `--config <path>` if needed.

## Logs

When `--log` is omitted, the script writes logs under `logs/` using the firmware file name stem. Ensure the directory is writable; it will be created automatically on demand when downstream tasks run.
