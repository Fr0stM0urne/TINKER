"""Result collection, parsing, and analysis for Penguin executions."""

import csv
import yaml
from pathlib import Path
from typing import Dict, Optional, List, Any
from configparser import ConfigParser


def get_penguin_results_dir(
    config: ConfigParser,
    penguin_proj: Path,
    run_number: Optional[int] = None
) -> Optional[Path]:
    """
    Get the results directory for a Penguin project.
    
    Args:
        config: Configuration object
        penguin_proj: Path to the Penguin project directory
        run_number: Specific run number to retrieve, or None for latest
        
    Returns:
        Path to results directory, or None if not found
        
    Example:
        >>> results_dir = get_penguin_results_dir(config, Path("projects/fw"))
        >>> if results_dir:
        ...     print(f"Results in: {results_dir}")
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


def get_penguin_results(
    config: ConfigParser,
    penguin_proj: Path,
    run_number: Optional[int] = None
) -> Dict[str, Any]:
    """
    Collect all Penguin results into a structured dictionary.
    
    Args:
        config: Configuration object
        penguin_proj: Path to the Penguin project directory
        run_number: Specific run number to retrieve, or None for latest
        
    Returns:
        Dictionary containing all result files and parsed data with structure:
        {
            "success": bool,
            "results_dir": str,
            "run_number": int,
            "files": {filename: content},
            "parsed": {filename: parsed_data},
            "summary": {statistics and errors}
        }
        
    Example:
        >>> results = get_penguin_results(config, Path("projects/fw"))
        >>> if results["success"]:
        ...     print(f"Collected {results['summary']['files_collected']} files")
        ...     errors = get_penguin_errors(results)
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


def get_penguin_errors(results: Dict[str, Any]) -> List[str]:
    """
    Extract error messages from Penguin results.
    
    Args:
        results: Results dictionary from get_penguin_results()
        
    Returns:
        List of error messages found, or ["No errors found"] if clean
        
    Example:
        >>> results = get_penguin_results(config, proj_path)
        >>> errors = get_penguin_errors(results)
        >>> for error in errors:
        ...     print(f"Error: {error}")
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


# Private helper functions

def _parse_yaml(file_path: Path) -> Dict[str, Any]:
    """Parse YAML file."""
    with open(file_path, 'r') as f:
        return yaml.safe_load(f) or {}


def _parse_csv(file_path: Path) -> List[Dict[str, Any]]:
    """Parse CSV file into list of dicts."""
    with open(file_path, 'r') as f:
        reader = csv.DictReader(f)
        return list(reader)


def _generate_summary(results: Dict[str, Any]) -> Dict[str, Any]:
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

