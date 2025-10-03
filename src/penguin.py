import subprocess
import os
from pathlib import Path
from typing import Dict, Optional, List
import yaml
import csv


def penguin_init(config, fw):
    """Initialize firmware with Penguin."""
    print(f"\n===== Running Penguin INIT =====", flush=True)
    cmd = ["penguin", "--image", config['Penguin']['image'], "init", fw]
    print(f"[cmd] {cmd}", flush=True)
    result = subprocess.run(cmd)
    return result


def penguin_run(config, penguin_proj):
    """Run Penguin rehosting for specified timeout."""
    print(f"\n===== Running Penguin for {config['Penguin']['iteration_timeout']} minutes =====", flush=True)
    timeout = int(config['Penguin']['iteration_timeout']) * 60
    firmware_config = penguin_proj / "config.yaml"
    cmd = ["penguin", "--image", config['Penguin']['image'], "run", firmware_config,
            "--timeout", str(timeout)]
    print(f"[cmd] {cmd}", flush=True)
    result = subprocess.run(cmd)
    return result


def get_penguin_results_dir(config, penguin_proj: Path, run_number: Optional[int] = None) -> Optional[Path]:
    """
    Get the results directory for a Penguin project.
    
    Args:
        config: Configuration object
        penguin_proj: Path to the Penguin project directory
        run_number: Specific run number to retrieve, or None for latest
        
    Returns:
        Path to results directory, or None if not found
    """
    results_base = penguin_proj / "results"
    
    if not results_base.exists():
        print(f"[Warning] Results directory not found: {results_base}")
        return None
    
    # Get all numbered result directories
    result_dirs = [
        d for d in results_base.iterdir()
        if d.is_dir() and d.name.isdigit()
    ]
    
    if not result_dirs:
        print(f"[Warning] No result directories found in {results_base}")
        return None
    
    if run_number is not None:
        # Return specific run number
        target_dir = results_base / str(run_number)
        if target_dir.exists():
            return target_dir
        else:
            print(f"[Warning] Run number {run_number} not found")
            return None
    else:
        # Return latest (highest number)
        latest_dir = max(result_dirs, key=lambda d: int(d.name))
        return latest_dir


def get_penguin_results(config, penguin_proj: Path, run_number: Optional[int] = None) -> Dict:
    """
    Collect all Penguin results into a structured dictionary.
    
    Args:
        config: Configuration object
        penguin_proj: Path to the Penguin project directory
        run_number: Specific run number to retrieve, or None for latest
        
    Returns:
        Dictionary containing all result files and parsed data
    """
    results_dir = get_penguin_results_dir(config, penguin_proj, run_number)
    
    if results_dir is None:
        return {
            "success": False,
            "error": "Results directory not found",
            "results_dir": None,
            "files": {}
        }
    
    print(f"\n[Results] Collecting from: {results_dir}")
    
    results = {
        "success": True,
        "results_dir": str(results_dir),
        "run_number": int(results_dir.name),
        "files": {},
        "parsed": {},
        "summary": {}
    }
    
    # List of files to collect
    file_specs = [
        # (filename, parse_function, is_critical)
        ("console.log", None, True),
        ("env_missing.yaml", _parse_yaml, False),
        ("pseudofiles_failures.yaml", _parse_yaml, False),
        ("pseudofiles_modeled.yaml", _parse_yaml, False),
        ("netbinds.csv", _parse_csv, False),
    ]
    
    # Collect files
    for filename, parse_func, is_critical in file_specs:
        file_path = results_dir / filename
        
        if not file_path.exists():
            if is_critical:
                print(f"[Warning] Critical file missing: {filename}")
            results["files"][filename] = None
            continue
        
        # Check if file is empty
        if file_path.stat().st_size < 3:
            results["files"][filename] = f"{filename} is empty"
            results["parsed"][filename] = None
            continue
        
        # Read file content
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            results["files"][filename] = content
            
            # Parse if parser provided
            if parse_func:
                try:
                    parsed_data = parse_func(file_path)
                    results["parsed"][filename] = parsed_data
                except Exception as e:
                    print(f"[Warning] Failed to parse {filename}: {e}")
                    results["parsed"][filename] = None
        
        except Exception as e:
            print(f"[Error] Failed to read {filename}: {e}")
            results["files"][filename] = f"Error reading file: {e}"
    
    # Generate summary
    results["summary"] = _generate_summary(results)
    
    return results


def _parse_yaml(file_path: Path) -> Dict:
    """Parse YAML file."""
    with open(file_path, 'r') as f:
        return yaml.safe_load(f) or {}


def _parse_csv(file_path: Path) -> List[Dict]:
    """Parse CSV file into list of dicts."""
    with open(file_path, 'r') as f:
        reader = csv.DictReader(f)
        return list(reader)


def _generate_summary(results: Dict) -> Dict:
    """Generate a summary of the results for quick analysis."""
    summary = {
        "files_collected": len([f for f in results["files"].values() if f is not None]),
        "files_missing": len([f for f in results["files"].values() if f is None]),
        "has_console_log": results["files"].get("console.log") is not None,
        "errors": [],
        "statistics": {}
    }
    
    # Extract key statistics from parsed data
    if "env_missing.yaml" in results["parsed"] and results["parsed"]["env_missing.yaml"]:
        env_missing = results["parsed"]["env_missing.yaml"]
        summary["statistics"]["env_missing_count"] = len(env_missing) if isinstance(env_missing, (list, dict)) else 0
    
    if "pseudofiles_failures.yaml" in results["parsed"] and results["parsed"]["pseudofiles_failures.yaml"]:
        failures = results["parsed"]["pseudofiles_failures.yaml"]
        summary["statistics"]["pseudofile_failures"] = len(failures) if isinstance(failures, (list, dict)) else 0
    
    if "pseudofiles_modeled.yaml" in results["parsed"] and results["parsed"]["pseudofiles_modeled.yaml"]:
        modeled = results["parsed"]["pseudofiles_modeled.yaml"]
        summary["statistics"]["pseudofiles_modeled"] = len(modeled) if isinstance(modeled, (list, dict)) else 0
    
    if "netbinds.csv" in results["parsed"] and results["parsed"]["netbinds.csv"]:
        summary["statistics"]["network_bindings"] = len(results["parsed"]["netbinds.csv"])
    
    # Check console log for errors
    console = results["files"].get("console.log", "")
    if console and isinstance(console, str):
        error_indicators = ["error", "failed", "exception", "traceback"]
        for indicator in error_indicators:
            if indicator.lower() in console.lower():
                summary["errors"].append(f"Console log contains '{indicator}'")
    
    return summary


def get_penguin_errors(results: Dict) -> List[str]:
    """
    Extract error messages from Penguin results.
    
    Args:
        results: Results dictionary from get_penguin_results()
        
    Returns:
        List of error messages found
    """
    errors = []
    
    # Check console.log for errors
    console = results["files"].get("console.log", "")
    if console and isinstance(console, str):
        console_lines = console.split('\n')
        error_lines = [
            line for line in console_lines
            if any(keyword in line.lower() for keyword in ["error", "failed", "exception", "traceback"])
        ]
        if error_lines:
            errors.append("Console errors:\n" + "\n".join(error_lines[:20]))  # Limit to 20 lines
    
    # Check env_missing
    if results["parsed"].get("env_missing.yaml"):
        env_missing = results["parsed"]["env_missing.yaml"]
        if env_missing:
            count = len(env_missing) if isinstance(env_missing, (list, dict)) else 1
            errors.append(f"Missing environment variables: {count}")
    
    # Check pseudofile failures
    if results["parsed"].get("pseudofiles_failures.yaml"):
        failures = results["parsed"]["pseudofiles_failures.yaml"]
        if failures:
            count = len(failures) if isinstance(failures, (list, dict)) else 1
            errors.append(f"Pseudofile failures: {count}")
    
    return errors if errors else ["No errors found"]


def format_results_for_llm(results: Dict) -> str:
    """
    Format results in a concise way suitable for LLM consumption.
    
    Args:
        results: Results dictionary from get_penguin_results()
        
    Returns:
        Formatted string summary
    """
    if not results["success"]:
        return f"Failed to collect results: {results.get('error', 'Unknown error')}"
    
    output = []
    output.append(f"=== Penguin Results (Run #{results['run_number']}) ===\n")
    
    # Summary statistics
    output.append("Summary:")
    for key, value in results["summary"]["statistics"].items():
        output.append(f"  - {key}: {value}")
    output.append("")
    
    # Errors
    errors = get_penguin_errors(results)
    if errors and errors != ["No errors found"]:
        output.append("Errors Found:")
        for error in errors[:5]:  # Limit to 5 errors
            output.append(f"  - {error[:200]}...")  # Truncate long errors
        output.append("")
    
    # Files collected
    output.append(f"Files Collected: {results['summary']['files_collected']}")
    output.append(f"Files Missing: {results['summary']['files_missing']}")
    
    # Key files preview
    if results["files"].get("console.log"):
        console_preview = results["files"]["console.log"][:500]
        output.append(f"\nConsole Log Preview:\n{console_preview}...")
    
    return "\n".join(output)