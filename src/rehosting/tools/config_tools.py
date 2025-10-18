"""
Configuration tools for Penguin rehosting.

This module provides tools for updating Penguin YAML configuration files
following the JSON tool format for better parameter handling.
"""

try:
    import yaml
except ImportError:
    from ruamel import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
import subprocess
import tempfile
import shutil
import difflib
import json


@dataclass
class ToolDefinition:
    """Definition of a tool following the JSON format."""
    name: str
    description: str
    parameters: Dict[str, Any]
    required: List[str]
    strict: bool = True


class ConfigToolRegistry:
    """Registry of configuration tools for Penguin rehosting."""
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.config_file = project_path / "config.yaml"
        
        # Store original config for diff purposes
        self.original_config = None
        self.config = self._load_config()
        
        # Store original config if it exists
        if self.config:
            self.original_config = self._deep_copy_config(self.config)
    
    def _load_config(self) -> Dict[str, Any]:
        """Load existing config.yaml or return empty dict."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                print(f"Warning: Could not load config.yaml: {e}")
                return {}
        return {}
    
    def _save_config(self) -> bool:
        """Save config to file."""
        try:
            with open(self.config_file, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def _ensure_section(self, path: str) -> None:
        """Ensure a nested section exists in config."""
        parts = path.split('.')
        current = self.config
        
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
    
    def _get_nested_value(self, path: str) -> Any:
        """Get value from nested path."""
        parts = path.split('.')
        current = self.config
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current
    
    def _set_nested_value(self, path: str, value: Any) -> None:
        """Set value at nested path."""
        parts = path.split('.')
        current = self.config
        
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        current[parts[-1]] = value
    
    def _add_to_list(self, path: str, value: Any) -> None:
        """Add value to list at path."""
        parts = path.split('.')
        current = self.config
        
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        if parts[-1] not in current:
            current[parts[-1]] = []
        
        if not isinstance(current[parts[-1]], list):
            current[parts[-1]] = []
        
        current[parts[-1]].append(value)
    
    def _remove_from_list(self, path: str, value: Any) -> bool:
        """Remove value from list at path."""
        parts = path.split('.')
        current = self.config
        
        for part in parts[:-1]:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return False
        
        if isinstance(current, dict) and parts[-1] in current:
            if isinstance(current[parts[-1]], list):
                try:
                    current[parts[-1]].remove(value)
                    return True
                except ValueError:
                    return False
        return False
    
    def _remove_nested_value(self, path: str) -> bool:
        """Remove value at nested path."""
        parts = path.split('.')
        current = self.config
        
        for part in parts[:-1]:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return False
        
        if isinstance(current, dict) and parts[-1] in current:
            del current[parts[-1]]
            return True
        return False
    
    # Tool implementations following JSON format
    
    def change_init_program(self, error: str) -> Dict[str, Any]:
        """
        Select a different system init program.
        
        Invoke if you see something like: Kernel panic - not syncing: Attempted to kill init! exitcode=0x00000000
        """
        try:
            # Common init programs to try
            init_programs = ["/sbin/init", "/bin/init", "/usr/sbin/init", "/usr/bin/init"]
            
            # Try to find a working init program
            for init_prog in init_programs:
                if Path(init_prog).exists():
                    self._set_nested_value("env.igloo_init", init_prog)
                    if self._save_config():
                        return {
                            "status": "success",
                            "message": f"Changed init program to {init_prog}",
                            "changes": {"init_program": init_prog}
                        }
            
            return {
                "status": "failed",
                "message": "No suitable init program found",
                "changes": {}
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": f"Error changing init program: {e}",
                "changes": {}
            }
    
    def add_environment_variable_placeholder(self, name: str, reason: str) -> Dict[str, Any]:
        """
        Add a new environment variable with a magic placeholder value for dynamic discovery.
        
        This sets a placeholder value (DYNVALDYNVALDYNVAL) for dynamic discovery. Use 
        set_environment_variable_value to set the actual value once discovered.
        
        Never change the igloo_init env var.
        The env var name argument you provide must be one that see you indication is missing.
        Do not make up any fake arguments.
        """
        try:
            if name == "igloo_init":
                return {
                    "status": "failed",
                    "message": "Cannot modify igloo_init environment variable",
                    "changes": {}
                }
            
            # Set to a placeholder value that can be discovered dynamically
            placeholder_value = "DYNVALDYNVALDYNVAL"
            self._set_nested_value(f"env.{name}", placeholder_value)
            
            if self._save_config():
                return {
                    "status": "success",
                    "message": f"Added environment variable {name} with placeholder value for dynamic discovery",
                    "changes": {"env_var": name, "value": placeholder_value}
                }
            else:
                return {
                    "status": "failed",
                    "message": "Failed to save config",
                    "changes": {}
                }
        except Exception as e:
            return {
                "status": "failed",
                "message": f"Error adding environment variable: {e}",
                "changes": {}
            }
    
    def set_environment_variable_value(self, name: str, value: str, reason: str) -> Dict[str, Any]:
        """
        Set the actual value for an environment variable that was previously added with a placeholder.
        
        Use this after dynamic discovery has found the real value.
        """
        try:
            if name == "igloo_init":
                return {
                    "status": "failed",
                    "message": "Cannot modify igloo_init environment variable",
                    "changes": {}
                }
            
            # Set the actual value
            self._set_nested_value(f"env.{name}", value)
            
            if self._save_config():
                return {
                    "status": "success",
                    "message": f"Set environment variable {name} = {value}",
                    "changes": {"env_var": name, "value": value}
                }
            else:
                return {
                    "status": "failed",
                    "message": "Failed to save config",
                    "changes": {}
                }
        except Exception as e:
            return {
                "status": "failed",
                "message": f"Error setting environment variable value: {e}",
                "changes": {}
            }
    
    def remove_environment_variable(self, name: str, reason: str) -> Dict[str, Any]:
        """
        Remove an environment variable from the Penguin config.yaml.
        
        Never change the igloo_init env var.
        Do not make up any fake arguments.
        """
        try:
            if name == "igloo_init":
                return {
                    "status": "failed",
                    "message": "Cannot remove igloo_init environment variable",
                    "changes": {}
                }
            
            if self._remove_nested_value(f"env.{name}"):
                if self._save_config():
                    return {
                        "status": "success",
                        "message": f"Removed environment variable {name}",
                        "changes": {"removed_env_var": name}
                    }
                else:
                    return {
                        "status": "failed",
                        "message": "Failed to save config",
                        "changes": {}
                    }
            else:
                return {
                    "status": "failed",
                    "message": f"Environment variable {name} not found",
                    "changes": {}
                }
        except Exception as e:
            return {
                "status": "failed",
                "message": f"Error removing environment variable: {e}",
                "changes": {}
            }
    
    def add_pseudofile(self, filepath: str, name: str, reason: str) -> Dict[str, Any]:
        """
        Add a new pseudofile to the Penguin config.yaml modeling a device in /sys, /dev, or /proc.
        
        If the file is an mtd (/dev/mtdX) device, specify the name of the MTD device as the <name> argument.
        We leave the devices unconfigured because we do not know what the system is trying to do with the device.
        The pseudofile path you provide must be one that you see indication is missing.
        Do not make up any fake arguments.
        """
        try:
            # Validate path is in allowed directories
            if not any(filepath.startswith(prefix) for prefix in ["/sys/", "/dev/", "/proc/"]):
                return {
                    "status": "failed",
                    "message": "Pseudofile path must be in /sys, /dev, or /proc",
                    "changes": {}
                }
            
            # Ensure pseudofiles section exists
            self._ensure_section("pseudofiles")
            
            # Check if pseudofile already exists
            if filepath in self.config.get("pseudofiles", {}):
                return {
                    "status": "failed",
                    "message": f"Pseudofile {filepath} already exists",
                    "changes": {}
                }
            
            # Create pseudofile entry as a dictionary
            pseudofile_entry = {}
            if filepath.startswith("/dev/mtd") and name:
                pseudofile_entry["name"] = name
            
            # Add pseudofile entry to the dictionary structure
            if "pseudofiles" not in self.config:
                self.config["pseudofiles"] = {}
            
            self.config["pseudofiles"][filepath] = pseudofile_entry
            
            if self._save_config():
                return {
                    "status": "success",
                    "message": f"Added pseudofile {filepath}",
                    "changes": {"pseudofile": filepath, "name": name}
                }
            else:
                return {
                    "status": "failed",
                    "message": "Failed to save config",
                    "changes": {}
                }
        except Exception as e:
            return {
                "status": "failed",
                "message": f"Error adding pseudofile: {e}",
                "changes": {}
            }
    
    def remove_pseudofile(self, filepath: str, reason: str) -> Dict[str, Any]:
        """
        Remove a pseudofile from the Penguin config.yaml.
        """
        try:
            # Check if pseudofiles section exists and contains the filepath
            pseudofiles = self.config.get("pseudofiles", {})
            if filepath in pseudofiles:
                del pseudofiles[filepath]
                if self._save_config():
                    return {
                        "status": "success",
                        "message": f"Removed pseudofile {filepath}",
                        "changes": {"removed_pseudofile": filepath}
                    }
                else:
                    return {
                        "status": "failed",
                        "message": "Failed to save config",
                        "changes": {}
                    }
            
            return {
                "status": "failed",
                "message": f"Pseudofile {filepath} not found",
                "changes": {}
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": f"Error removing pseudofile: {e}",
                "changes": {}
            }
    
    def set_file_read_behavior(self, filepath: str, model: str, value: str, reason: str) -> Dict[str, Any]:
        """
        Modify the READ model of a pseudofile if you have a specific value to return on 'reads'.
        
        Aka the content of the file.
        """
        try:
            if model not in ["return_zero", "const_buf"]:
                return {
                    "status": "failed",
                    "message": "Model must be 'return_zero' or 'const_buf'",
                    "changes": {}
                }
            
            # Find pseudofile and update its read behavior
            pseudofiles = self.config.get("pseudofiles", {})
            if filepath in pseudofiles:
                pseudofiles[filepath]["read_model"] = model
                if model == "const_buf":
                    pseudofiles[filepath]["read_value"] = value
                if self._save_config():
                    return {
                        "status": "success",
                        "message": f"Set read behavior for {filepath} to {model}",
                        "changes": {"filepath": filepath, "read_model": model, "value": value}
                    }
                else:
                    return {
                        "status": "failed",
                        "message": "Failed to save config",
                        "changes": {}
                    }
            
            return {
                "status": "failed",
                "message": f"Pseudofile {filepath} not found",
                "changes": {}
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": f"Error setting file read behavior: {e}",
                "changes": {}
            }
    
    def grep_strace_output(self, grep_command: str, reason: str) -> Dict[str, Any]:
        """
        Every process in the system will have its system calls traced (strace) and logged.
        
        Use this tool to grep that output and, for example, learn about a file's accesses.
        """
        try:
            # Look for strace output files in results directory
            results_dir = self.project_path / "results"
            if not results_dir.exists():
                return {
                    "status": "failed",
                    "message": "No results directory found",
                    "changes": {}
                }
            
            # Find the most recent results directory
            result_dirs = [d for d in results_dir.iterdir() if d.is_dir()]
            if not result_dirs:
                return {
                    "status": "failed",
                    "message": "No result directories found",
                    "changes": {}
                }
            
            latest_result = max(result_dirs, key=lambda d: d.name)
            strace_file = latest_result / "console.log"
            
            if not strace_file.exists():
                return {
                    "status": "failed",
                    "message": "No console.log found in results",
                    "changes": {}
                }
            
            # Execute grep command
            cmd = f"grep {grep_command} {strace_file}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            return {
                "status": "success",
                "message": f"Grep completed with exit code {result.returncode}",
                "changes": {
                    "grep_command": cmd,
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr
                }
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": f"Error running grep: {e}",
                "changes": {}
            }
    
    def replace_script_exit0(self, script_path: str, reason: str) -> Dict[str, Any]:
        """
        Replace a script with exit0.sh (script that just returns success: 0).
        
        For example, if something keeps trying to tell the system to turn off with shutdown script '/bin/killall', replace it with 'exit0.sh'.
        """
        try:
            # Create exit0.sh script
            exit0_script = "#!/bin/sh\nexit 0\n"
            
            # Create the replacement script
            script_file = self.project_path / script_path
            script_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(script_file, 'w') as f:
                f.write(exit0_script)
            
            # Make it executable
            script_file.chmod(0o755)
            
            return {
                "status": "success",
                "message": f"Replaced {script_path} with exit0.sh",
                "changes": {"replaced_script": script_path}
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": f"Error replacing script: {e}",
                "changes": {}
            }
    
    # Tool registry for easy access
    def get_tool(self, tool_name: str):
        """Get tool function by name."""
        tools = {
            "change_init_program": self.change_init_program,
            "add_environment_variable_placeholder": self.add_environment_variable_placeholder,
            "set_environment_variable_value": self.set_environment_variable_value,
            "remove_environment_variable": self.remove_environment_variable,
            "add_pseudofile": self.add_pseudofile,
            "remove_pseudofile": self.remove_pseudofile,
            "set_file_read_behavior": self.set_file_read_behavior,
            "grep_strace_output": self.grep_strace_output,
            "replace_script_exit0": self.replace_script_exit0,
        }
        return tools.get(tool_name)
    
    def list_tools(self) -> List[str]:
        """List available tool names."""
        return [
            "change_init_program",
            "add_environment_variable_placeholder",
            "set_environment_variable_value",
            "remove_environment_variable",
            "add_pseudofile",
            "remove_pseudofile",
            "set_file_read_behavior",
            "grep_strace_output",
            "replace_script_exit0",
        ]
    
    def _deep_copy_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Create a deep copy of the config for diff purposes."""
        return json.loads(json.dumps(config))
    
    def get_config_diff(self) -> str:
        """
        Generate a diff between original and current config.
        
        Returns:
            String representation of the diff
        """
        if not self.original_config:
            return "No original config to compare against"
        
        # Convert both configs to YAML strings for diff
        original_yaml = yaml.dump(self.original_config, default_flow_style=False, sort_keys=False)
        current_yaml = yaml.dump(self.config, default_flow_style=False, sort_keys=False)
        
        # Generate unified diff
        diff_lines = difflib.unified_diff(
            original_yaml.splitlines(keepends=True),
            current_yaml.splitlines(keepends=True),
            fromfile="original config.yaml",
            tofile="current config.yaml",
            lineterm=""
        )
        
        return "".join(diff_lines)
    
    def get_config_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the current configuration.
        
        Returns:
            Dictionary with config summary information
        """
        summary = {
            "file_path": str(self.config_file),
            "exists": self.config_file.exists(),
            "sections": list(self.config.keys()) if self.config else [],
            "has_changes": self.original_config != self.config if self.original_config else False
        }
        
        # Count items in each section
        for section, content in self.config.items():
            if isinstance(content, dict):
                summary[f"{section}_count"] = len(content)
            elif isinstance(content, list):
                summary[f"{section}_count"] = len(content)
            else:
                summary[f"{section}_type"] = type(content).__name__
        
        return summary
    
    def print_config_diff(self) -> None:
        """Print the config diff to console."""
        diff = self.get_config_diff()
        if diff.strip():
            print("\n" + "=" * 70)
            print("CONFIGURATION CHANGES")
            print("=" * 70)
            print(diff)
            print("=" * 70)
        else:
            print("\n📋 No configuration changes detected")
    
    def print_config_summary(self) -> None:
        """Print the config summary to console."""
        summary = self.get_config_summary()
        
        print("\n" + "=" * 70)
        print("CONFIGURATION SUMMARY")
        print("=" * 70)
        print(f"File: {summary['file_path']}")
        print(f"Exists: {summary['exists']}")
        print(f"Has Changes: {summary['has_changes']}")
        print(f"Sections: {', '.join(summary['sections'])}")
        
        # Show section details
        for section in summary['sections']:
            if f"{section}_count" in summary:
                print(f"  {section}: {summary[f'{section}_count']} items")
        
        print("=" * 70)