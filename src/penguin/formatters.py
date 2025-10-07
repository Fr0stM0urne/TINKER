"""Formatting utilities for Penguin results, optimized for LLM consumption."""

import json
import re
from typing import Dict, Any
from .results import get_penguin_errors



def format_results_for_llm(results: Dict[str, Any]) -> str:
    """
    Format Penguin results in a concise way suitable for LLM consumption.
    
    This formatter creates a structured, token-efficient summary that:
    - Highlights key statistics and metrics
    - Surfaces errors and issues
    - Provides context without overwhelming detail
    - Truncates long outputs appropriately
    
    Args:
        results: Results dictionary from get_penguin_results()
        
    Returns:
        Formatted string summary optimized for LLM analysis
        
    Example:
        >>> results = get_penguin_results(config, proj_path)
        >>> llm_summary = format_results_for_llm(results)
        >>> # Pass llm_summary to your LLM agent
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


    return "\n".join(output)


def format_results_detailed(results: Dict[str, Any]) -> str:
    """
    Format Penguin results with full detail for comprehensive analysis.
    
    Args:
        results: Results dictionary from get_penguin_results()
        
    Returns:
        Detailed formatted string with all available information
    """
    if not results["success"]:
        return f"Failed to collect results: {results.get('error', 'Unknown error')}"
    
    output = []
    output.append("=" * 60)
    output.append(f"PENGUIN EXECUTION RESULTS - Run #{results['run_number']}")
    output.append("=" * 60)
    output.append(f"Results Directory: {results['results_dir']}\n")
    
    # Summary Section
    output.append("SUMMARY:")
    output.append(f"  Files Collected: {results['summary']['files_collected']}")
    output.append(f"  Files Missing: {results['summary']['files_missing']}")
    output.append(f"  Has Console Log: {results['summary']['has_console_log']}\n")
    
    # Statistics
    if results["summary"]["statistics"]:
        output.append("STATISTICS:")
        for key, value in results["summary"]["statistics"].items():
            output.append(f"  {key}: {value}")
        output.append("")
    
    # Errors
    errors = get_penguin_errors(results)
    output.append("ERRORS:")
    for error in errors:
        output.append(f"  {error}")
    output.append("")
    
    # Parsed Data - Full Content
    output.append("PARSED DATA:")
    for filename, data in results["parsed"].items():
        if data:
            output.append("\n" + "=" * 60)
            output.append(f"--- {filename} ---")
            output.append("=" * 60)
            if isinstance(data, str):
                # For console.log (already cleaned text)
                output.append(data)
            elif isinstance(data, (dict, list)):
                # For YAML/CSV parsed data
                output.append(json.dumps(data, indent=2))
            else:
                output.append(str(data))
            output.append("")
    
    output.append("=" * 60)
    
    return "\n".join(output)

