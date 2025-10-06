# Penguin Module

A formal Python module for interacting with the Penguin firmware rehosting framework.

## Overview

This module provides a clean, object-oriented API for:
- Initializing firmware projects
- Running rehosting executions
- Collecting and analyzing results
- Formatting output for LLM agents

## Architecture

```
penguin/
├── __init__.py         # Public API exports
├── client.py           # High-level PenguinClient class
├── operations.py       # Core operations (init, run)
├── results.py          # Result collection and parsing
└── formatters.py       # LLM-optimized formatting
```

## Usage Examples

### Basic Usage with PenguinClient

```python
from pathlib import Path
from src.penguin import PenguinClient
import configparser

# Load configuration
config = configparser.ConfigParser()
config.read("config.ini")

# Initialize client
client = PenguinClient(config)

# Initialize firmware project
client.init("/path/to/firmware.bin")

# Run rehosting
project_path = Path("projects/firmware_001")
client.run(project_path)

# Get results
results = client.get_results(project_path)

# Extract errors
errors = client.get_errors(results)
print("Errors:", errors)

# Format for LLM
llm_summary = client.format_for_llm(results)
print(llm_summary)
```

### Complete Workflow

```python
from pathlib import Path
from src.penguin import PenguinClient

# Initialize client
client = PenguinClient(config)

# Execute complete workflow: init -> run -> analyze
workflow_results = client.execute_workflow(
    firmware_path="/data/firmware.bin",
    project_path=Path("projects/my_firmware")
)

if workflow_results["success"]:
    print("Workflow completed successfully!")
    print(workflow_results["llm_summary"])
else:
    print("Errors:", workflow_results["errors"])
```

### Low-Level Function API

```python
from pathlib import Path
from src.penguin import (
    penguin_init,
    penguin_run,
    get_penguin_results,
    format_results_for_llm
)

# Direct function calls
penguin_init(config, "/path/to/firmware.bin")
penguin_run(config, Path("projects/firmware_001"))

# Get results
results = get_penguin_results(config, Path("projects/firmware_001"))

# Format for LLM
summary = format_results_for_llm(results)
```

## API Reference

### PenguinClient

**Constructor:**
- `PenguinClient(config)` - Initialize with configuration dict

**Methods:**
- `init(firmware_path: str)` - Initialize firmware project
- `run(project_path: Path)` - Run rehosting execution
- `get_results(project_path: Path, run_number: Optional[int] = None)` - Collect results
- `get_results_dir(project_path: Path, run_number: Optional[int] = None)` - Get results directory path
- `get_errors(results: Dict)` - Extract errors from results
- `format_for_llm(results: Dict)` - Format results for LLM (concise)
- `format_detailed(results: Dict)` - Format results with full detail
- `execute_workflow(firmware_path: str, project_path: Path)` - Complete workflow

### Functions

**Operations:**
- `penguin_init(config, fw)` - Initialize firmware
- `penguin_run(config, penguin_proj)` - Run rehosting

**Results:**
- `get_penguin_results_dir(config, penguin_proj, run_number=None)` - Get results directory
- `get_penguin_results(config, penguin_proj, run_number=None)` - Collect all results
- `get_penguin_errors(results)` - Extract error messages

**Formatters:**
- `format_results_for_llm(results)` - Concise LLM-optimized format
- `format_results_detailed(results)` - Full detailed format

## Result Structure

The `get_penguin_results()` function returns:

```python
{
    "success": bool,
    "results_dir": str,
    "run_number": int,
    "files": {
        "console.log": str,
        "env_missing.yaml": str,
        "pseudofiles_failures.yaml": str,
        "pseudofiles_modeled.yaml": str,
        "netbinds.csv": str
    },
    "parsed": {
        "env_missing.yaml": dict,
        "pseudofiles_failures.yaml": dict,
        "pseudofiles_modeled.yaml": dict,
        "netbinds.csv": list
    },
    "summary": {
        "files_collected": int,
        "files_missing": int,
        "has_console_log": bool,
        "errors": list,
        "statistics": {
            "env_missing_count": int,
            "pseudofile_failures": int,
            "pseudofiles_modeled": int,
            "network_bindings": int
        }
    }
}
```

## Integration with LLM Framework

The Penguin module is designed to work seamlessly with the LLM multi-agent framework:

```python
from src.penguin import PenguinClient
from src.llms.schemas import State

# Use in agent context
client = PenguinClient(config)

# Run and get LLM-formatted results
results = client.get_results(project_path)
llm_summary = client.format_for_llm(results)

# Add to state context
state = State(
    goal="Analyze firmware",
    rag_context=[llm_summary]
)
```

## Migration from Old API

If you have code using the old `penguin.py` file:

**Old:**
```python
from src import penguin
penguin.penguin_init(config, fw)
```

**New:**
```python
from src.penguin import PenguinClient
client = PenguinClient(config)
client.init(fw)
```

Or use the function API directly:
```python
from src.penguin import penguin_init
penguin_init(config, fw)
```

