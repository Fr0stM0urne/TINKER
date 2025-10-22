"""High-level Penguin client for managing firmware rehosting workflows."""

import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from configparser import ConfigParser

from .operations import penguin_init, penguin_run
from .results import get_penguin_results_dir, get_penguin_results, get_penguin_errors


class PenguinClient:
    """
    High-level client for interacting with Penguin firmware rehosting tool.
    
    This client provides a clean, object-oriented interface for:
    - Initializing firmware projects
    - Running rehosting executions
    - Collecting and analyzing results
    - Formatting output for LLM agents
    
    Example:
        >>> from pathlib import Path
        >>> client = PenguinClient(config)
        >>> 
        >>> # Initialize firmware
        >>> result = client.init("/path/to/firmware.bin")
        >>> 
        >>> # Run rehosting
        >>> project = Path("projects/firmware_001")
        >>> result = client.run(project)
        >>> 
        >>> # Get results as dict for LLM workflow
        >>> results = client.get_results(project)
        >>> context_dict = client.get_context_dict(results)
    """
    
    def __init__(self, config: ConfigParser):
        """
        Initialize Penguin client with configuration.
        
        Args:
            config: Configuration dictionary containing Penguin settings
                    Expected keys: config['Penguin']['image'], 
                                  config['Penguin']['iteration_timeout']
        """
        self.config = config
        self._validate_config()
    
    def _validate_config(self):
        """Validate that required configuration is present."""
        if not self.config.has_section('Penguin'):
            raise ValueError("Configuration missing 'Penguin' section")
        
        required_keys = ['image', 'iteration_timeout']
        for key in required_keys:
            if not self.config.has_option('Penguin', key):
                raise ValueError(f"Configuration missing 'Penguin.{key}'")
    
    def init(self, firmware_path: str) -> Tuple[subprocess.CompletedProcess, Optional[Path]]:
        """
        Initialize a firmware project with Penguin and get the project path.
        
        Args:
            firmware_path: Path to the firmware binary file
            
        Returns:
            Tuple of (subprocess.CompletedProcess, project_path)
            - CompletedProcess: execution results
            - project_path: Actual host path to the created project (None if parsing failed)
            
        Raises:
            FileNotFoundError: If firmware file doesn't exist
            
        Example:
            >>> client = PenguinClient(config)
            >>> result, project_path = client.init("/path/to/firmware.bin")
            >>> if result.returncode == 0:
            ...     print(f"Project created at: {project_path}")
        """
        fw_path = Path(firmware_path)
        if not fw_path.exists():
            raise FileNotFoundError(f"Firmware file not found: {firmware_path}")
        
        return penguin_init(self.config, firmware_path)
    
    def run(self, project_path: Path) -> Dict[str, Any]:
        """
        Run Penguin rehosting on an initialized project and collect results.
        
        This method now returns a combined dictionary containing both the
        runtime execution info and the parsed result files.
        
        Args:
            project_path: Path to the Penguin project directory
            
        Returns:
            Dictionary containing:
            - "run_result": subprocess.CompletedProcess object
            - "returncode": exit code from Penguin run
            - "output": terminal output from run (cleaned of ANSI codes)
            - Plus all fields from get_results() (success, run_number, parsed, etc.)
            
        Raises:
            FileNotFoundError: If project directory or config doesn't exist
            
        Example:
            >>> combined = client.run(project_path)
            >>> print(f"Exit code: {combined['returncode']}")
            >>> print(f"Files collected: {combined['summary']['files_collected']}")
            >>> context = client.get_context_dict(combined)
        """
        import re
        
        if not project_path.exists():
            raise FileNotFoundError(f"Project directory not found: {project_path}")
        
        config_file = project_path / "config.yaml"
        if not config_file.exists():
            raise FileNotFoundError(f"Project config not found: {config_file}")
        
        # Execute Penguin run
        run_result = penguin_run(self.config, project_path)
        
        # Collect parsed results
        results = get_penguin_results(self.config, project_path, run_number=None)
        
        # Clean ANSI codes from terminal output
        output = getattr(run_result, '_merged_output', '')
        if output:
            ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
            output = ansi_escape.sub('', output)
        
        # Merge into single dict
        combined = {
            "run_result": run_result,
            "returncode": run_result.returncode,
            "output": output,
            **results  # Unpack all results fields (success, run_number, files, parsed, summary)
        }
        
        return combined
    
    def get_results(
        self,
        project_path: Path,
        run_number: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Collect results from a Penguin execution.
        
        Args:
            project_path: Path to the Penguin project directory
            run_number: Specific run number to retrieve, or None for latest
            
        Returns:
            Dictionary containing parsed results and metadata
        """
        return get_penguin_results(self.config, project_path, run_number)
    
    def get_results_dir(
        self,
        project_path: Path,
        run_number: Optional[int] = None
    ) -> Optional[Path]:
        """
        Get the results directory path for a Penguin execution.
        
        Args:
            project_path: Path to the Penguin project directory
            run_number: Specific run number to retrieve, or None for latest
            
        Returns:
            Path to results directory, or None if not found
        """
        return get_penguin_results_dir(self.config, project_path, run_number)
    
    def get_errors(self, results: Dict[str, Any]) -> list:
        """
        Extract errors from Penguin results.
        
        Args:
            results: Results dictionary from get_results()
            
        Returns:
            List of error messages
        """
        return get_penguin_errors(results)
    
    def get_context_dict(self, results: Dict[str, Any]) -> Dict[str, str]:
        """
        Extract context as a dictionary ready for multi-agent workflow.
        
        This method provides direct dict access to Penguin results, avoiding
        the need to format as string and then parse back to dict.
        
        Args:
            results: Results dictionary from get_results()
            
        Returns:
            Dictionary with keys as source names and values as content strings:
            - "console.log": cleaned console output
            - "env_cmp.txt": environment comparison data  
            - "env_missing.yaml": formatted YAML data
            - "pseudofiles_failures.yaml": formatted YAML data
            - "penguin_results": summary with stats and errors
            
        Example:
            >>> results = client.get_results(project_path)
            >>> context = client.get_context_dict(results)
            >>> # Access specific files directly
            >>> console_log = context.get("console.log", "")
            >>> env_cmp = context.get("env_cmp.txt", "")
        """
        import json
        
        if not results["success"]:
            return {"error": results.get("error", "Unknown error")}
        
        context = {}
        
        # Add penguin_results summary
        summary_parts = []
        summary_parts.append(f"Run #{results['run_number']}")
        summary_parts.append(f"Results directory: {results['results_dir']}")
        summary_parts.append(f"Files collected: {results['summary']['files_collected']}")
        summary_parts.append(f"Files missing: {results['summary']['files_missing']}")
        
        # Add statistics if available
        if results["summary"].get("statistics"):
            summary_parts.append("\nStatistics:")
            for key, value in results["summary"]["statistics"].items():
                summary_parts.append(f"  {key}: {value}")
        
        # Add errors
        errors = get_penguin_errors(results)
        if errors and errors != ["No errors found"]:
            summary_parts.append("\nErrors:")
            summary_parts.extend([f"  - {e}" for e in errors])
        
        context["penguin_results"] = "\n".join(summary_parts)
        
        # Add each parsed file as separate key
        for filename, content in results["parsed"].items():
            if content is None:
                continue
            
            # Format based on data type
            if isinstance(content, str):
                context[filename] = content
            elif isinstance(content, (dict, list)):
                # Convert YAML/JSON structures to readable format
                context[filename] = json.dumps(content, indent=2)
            else:
                context[filename] = str(content)
        
        return context

