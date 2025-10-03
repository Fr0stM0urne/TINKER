# Penguin Results - Files Collected

## Essential Files (5 files)

The result collection now focuses on these 5 essential files:

### 1. **console.log** (Critical)
- **Type**: Text log file
- **Parsed**: No (kept as raw text)
- **Purpose**: Main execution log showing firmware boot process
- **Usage**: Search for errors, track execution flow
- **Example**:
  ```python
  console = results["files"]["console.log"]
  if "error" in console.lower():
      print("Errors detected in console")
  ```

### 2. **env_missing.yaml**
- **Type**: YAML
- **Parsed**: Yes → Dict
- **Purpose**: Lists environment variables that are missing but needed
- **Usage**: Identify configuration gaps
- **Example**:
  ```python
  env_missing = results["parsed"]["env_missing.yaml"]
  count = results["summary"]["statistics"]["env_missing_count"]
  print(f"Missing {count} environment variables")
  ```

### 3. **pseudofiles_failures.yaml**
- **Type**: YAML
- **Parsed**: Yes → Dict/List
- **Purpose**: Pseudofiles that failed to model
- **Usage**: Identify which files need manual intervention
- **Example**:
  ```python
  failures = results["parsed"]["pseudofiles_failures.yaml"]
  count = results["summary"]["statistics"]["pseudofile_failures"]
  print(f"Failed to model {count} pseudofiles")
  ```

### 4. **pseudofiles_modeled.yaml**
- **Type**: YAML
- **Parsed**: Yes → Dict/List
- **Purpose**: Successfully modeled pseudofiles
- **Usage**: See what's working, reference for similar files
- **Example**:
  ```python
  modeled = results["parsed"]["pseudofiles_modeled.yaml"]
  count = results["summary"]["statistics"]["pseudofiles_modeled"]
  print(f"Successfully modeled {count} pseudofiles")
  ```

### 5. **netbinds.csv**
- **Type**: CSV
- **Parsed**: Yes → List[Dict]
- **Purpose**: Network bindings and ports discovered
- **Usage**: Understand network services, check connectivity
- **Example**:
  ```python
  netbinds = results["parsed"]["netbinds.csv"]
  for bind in netbinds:
      print(f"Port {bind['port']}: {bind['process']}")
  ```

## Result Structure

```python
{
    "success": True,
    "results_dir": "/path/to/results/1",
    "run_number": 1,
    
    # Raw file contents
    "files": {
        "console.log": "full text content...",
        "env_missing.yaml": "raw yaml text...",
        "pseudofiles_failures.yaml": "raw yaml text...",
        "pseudofiles_modeled.yaml": "raw yaml text...",
        "netbinds.csv": "raw csv text..."
    },
    
    # Parsed data structures
    "parsed": {
        "env_missing.yaml": {...},              # Dict
        "pseudofiles_failures.yaml": {...},     # Dict/List
        "pseudofiles_modeled.yaml": {...},      # Dict/List
        "netbinds.csv": [{...}, {...}]          # List of Dicts
    },
    
    # Summary statistics
    "summary": {
        "files_collected": 5,
        "files_missing": 0,
        "has_console_log": True,
        "errors": ["Console log contains 'error'"],
        "statistics": {
            "env_missing_count": 3,
            "pseudofile_failures": 5,
            "pseudofiles_modeled": 20,
            "network_bindings": 3
        }
    }
}
```

## Quick Access Patterns

### Get all errors
```python
from penguin import get_penguin_results, get_penguin_errors

results = get_penguin_results(config, penguin_proj)
errors = get_penguin_errors(results)

for error in errors:
    print(error)
```

### Get statistics only
```python
results = get_penguin_results(config, penguin_proj)
stats = results["summary"]["statistics"]

print(f"Env missing: {stats.get('env_missing_count', 0)}")
print(f"Pseudofile failures: {stats.get('pseudofile_failures', 0)}")
print(f"Pseudofiles modeled: {stats.get('pseudofiles_modeled', 0)}")
print(f"Network bindings: {stats.get('network_bindings', 0)}")
```

### Get formatted summary for LLM
```python
from penguin import format_results_for_llm

results = get_penguin_results(config, penguin_proj)
summary = format_results_for_llm(results)

# Send to LLM
llm.invoke(f"Analyze these results:\n{summary}")
```

### Check specific issues
```python
results = get_penguin_results(config, penguin_proj)

# Check if rehosting was successful
has_errors = len(results["summary"]["errors"]) > 0
env_issues = results["summary"]["statistics"].get("env_missing_count", 0) > 0
pseudofile_issues = results["summary"]["statistics"].get("pseudofile_failures", 0) > 5

if has_errors or env_issues or pseudofile_issues:
    print("Rehosting needs attention")
else:
    print("Rehosting looks good")
```

## Usage in LangChain Agent

```python
from langchain.tools import tool
from pathlib import Path
import configparser
from penguin import get_penguin_results, format_results_for_llm

@tool
def analyze_rehosting_results(firmware_name: str) -> str:
    """
    Analyze Penguin rehosting results and provide summary.
    
    Collects:
    - console.log (execution log)
    - env_missing.yaml (missing environment vars)
    - pseudofiles_failures.yaml (failed file models)
    - pseudofiles_modeled.yaml (successful file models)
    - netbinds.csv (network bindings)
    
    Returns formatted summary with errors and statistics.
    """
    config = configparser.ConfigParser()
    config.read('config.ini')
    
    penguin_proj = Path(config['Penguin']['output_dir']) / firmware_name
    results = get_penguin_results(config, penguin_proj)
    
    return format_results_for_llm(results)
```

## File Priority for Debugging

When debugging rehosting issues, check files in this order:

1. **console.log** - First check for obvious errors
2. **env_missing.yaml** - See what config is needed
3. **pseudofiles_failures.yaml** - Identify problematic files
4. **pseudofiles_modeled.yaml** - See what's working (reference)
5. **netbinds.csv** - Verify network services started

## Example: Quick Health Check

```python
def quick_health_check(results):
    """Quick assessment of rehosting results."""
    stats = results["summary"]["statistics"]
    
    # Good indicators
    modeled = stats.get("pseudofiles_modeled", 0)
    bindings = stats.get("network_bindings", 0)
    
    # Problem indicators
    failures = stats.get("pseudofile_failures", 0)
    missing_env = stats.get("env_missing_count", 0)
    has_errors = len(results["summary"]["errors"]) > 0
    
    score = 0
    if modeled > 10: score += 2
    if bindings > 0: score += 1
    if failures < 5: score += 1
    if missing_env < 3: score += 1
    if not has_errors: score += 2
    
    if score >= 6:
        return "GOOD - Rehosting successful"
    elif score >= 4:
        return "PARTIAL - Needs some fixes"
    else:
        return "FAILED - Significant issues"
```

## Summary

These 5 files provide the essential information needed to:
- ✅ Understand execution flow (console.log)
- ✅ Identify missing configuration (env_missing.yaml)
- ✅ Know what failed (pseudofiles_failures.yaml)
- ✅ Know what worked (pseudofiles_modeled.yaml)
- ✅ Verify network services (netbinds.csv)

Perfect for building an LLM agent that can analyze results and suggest fixes! 🚀

