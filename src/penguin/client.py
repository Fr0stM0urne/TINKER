"""High-level Penguin client for managing firmware rehosting workflows."""

import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from configparser import ConfigParser

from .operations import penguin_init, penguin_run
from .results import get_penguin_results_dir, get_penguin_results, get_penguin_errors
from .formatters import format_results_for_llm, format_results_detailed


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
        >>> # Get results
        >>> results = client.get_results(project)
        >>> summary = client.format_for_llm(results)
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
    
    def run(self, project_path: Path) -> subprocess.CompletedProcess:
        """
        Run Penguin rehosting on an initialized project.
        
        Args:
            project_path: Path to the Penguin project directory
            
        Returns:
            subprocess.CompletedProcess with execution results
            
        Raises:
            FileNotFoundError: If project directory or config doesn't exist
        """
        if not project_path.exists():
            raise FileNotFoundError(f"Project directory not found: {project_path}")
        
        config_file = project_path / "config.yaml"
        if not config_file.exists():
            raise FileNotFoundError(f"Project config not found: {config_file}")
        
        return penguin_run(self.config, project_path)
    
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
    
    def format_for_llm(self, results: Dict[str, Any]) -> str:
        """
        Format results for LLM consumption.
        
        Args:
            results: Results dictionary from get_results()
            
        Returns:
            Concise formatted string suitable for LLM analysis
        """
        return format_results_for_llm(results)
    
    def format_detailed(self, results: Dict[str, Any]) -> str:
        """
        Format results with full detail.
        
        Args:
            results: Results dictionary from get_results()
            
        Returns:
            Detailed formatted string with all available information
        """
        return format_results_detailed(results)
    
    def execute_workflow(
        self,
        firmware_path: str,
        project_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Execute complete workflow: init -> run -> collect results.
        
        Args:
            firmware_path: Path to firmware binary
            project_path: Optional path where project exists. If None, will be 
                         auto-detected from penguin init output.
            
        Returns:
            Dictionary with workflow results including:
            - firmware_path: input firmware path
            - project_path: actual project path (auto-detected or provided)
            - init_result: initialization subprocess result
            - run_result: execution subprocess result  
            - analysis: collected Penguin results
            - errors: extracted errors
            - llm_summary: formatted summary for LLM
            - success: overall workflow success status
        """
        workflow_results = {
            "firmware_path": firmware_path,
            "project_path": None,
            "success": False,
            "init_result": None,
            "run_result": None,
            "analysis": None,
            "errors": None,
            "llm_summary": None
        }
        
        try:
            # Initialize (get project path from init if not provided)
            if project_path is None:
                print(f"[Workflow] Step 1: Initializing firmware (auto-detecting project path)...")
                init_result, detected_project_path = self.init(firmware_path)
                workflow_results["init_result"] = init_result
                
                if detected_project_path is None:
                    workflow_results["errors"] = ["Failed to detect project path from penguin init output"]
                    return workflow_results
                
                project_path = detected_project_path
                workflow_results["project_path"] = str(project_path)
                print(f"[Workflow] Detected project path: {project_path}")
            else:
                print(f"[Workflow] Step 1: Initializing firmware at {project_path}...")
                init_result, _ = self.init(firmware_path)
                workflow_results["init_result"] = init_result
                workflow_results["project_path"] = str(project_path)
            
            if init_result.returncode != 0:
                workflow_results["errors"] = ["Initialization failed"]
                return workflow_results
            
            # Run
            print(f"[Workflow] Step 2: Running Penguin rehosting...")
            run_result = self.run(project_path)
            workflow_results["run_result"] = run_result
            
            # Collect results regardless of run success
            print(f"[Workflow] Step 3: Collecting results...")
            analysis = self.get_results(project_path)
            workflow_results["analysis"] = analysis
            
            # Extract errors
            errors = self.get_errors(analysis)
            workflow_results["errors"] = errors
            
            # Format for LLM
            workflow_results["llm_summary"] = self.format_for_llm(analysis)
            
            # Mark as successful if we got results
            workflow_results["success"] = analysis.get("success", False)
            
            print(f"[Workflow] Complete!")
            
        except Exception as e:
            workflow_results["errors"] = [f"Workflow exception: {str(e)}"]
            print(f"[Workflow] Error: {e}")
        
        return workflow_results

