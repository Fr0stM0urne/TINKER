"""Core Penguin operations: initialization and execution."""

import subprocess
import re
from typing import Optional, Tuple
from pathlib import Path
from configparser import ConfigParser


def _map_docker_to_host_path(docker_path: str, config: ConfigParser) -> Path:
    """
    Map Docker virtual path to actual host path.
    
    Penguin uses /host_projects/ in Docker which maps to the output_dir in config.
    
    Args:
        docker_path: Docker virtual path (e.g., "/host_projects/firmware_001")
        config: Configuration dictionary with output_dir
        
    Returns:
        Actual host Path object
        
    Example:
        >>> _map_docker_to_host_path("/host_projects/netgearWAX615", config)
        Path("projects/netgearWAX615")
    """
    # Remove /host_projects prefix
    if docker_path.startswith("/host_projects/"):
        relative_path = docker_path.replace("/host_projects/", "")
    elif docker_path.startswith("/host_projects"):
        relative_path = docker_path.replace("/host_projects", "")
    else:
        # If not a docker path, return as-is
        return Path(docker_path)
    
    # Get output directory from config (ConfigParser object)
    output_dir = config.get('Penguin', 'output_dir', fallback='projects')
    
    # Combine to get actual host path
    return Path(output_dir) / relative_path


def _parse_project_path_from_output(output: str, config: ConfigParser) -> Optional[Path]:
    """
    Parse the project path from penguin init output.
    
    Looks for lines like:
    "Creating project at generated path: /host_projects/firmware_name"
    
    Args:
        output: Command output string
        config: Configuration dictionary for path mapping
        
    Returns:
        Actual host Path to the project, or None if not found
    """
    # Strip ANSI color codes that penguin outputs
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    clean_output = ansi_escape.sub('', output)
    
    # Look for the project path in output
    pattern = r"Creating project at generated path:\s+(/host_projects/[^\s]+)"
    match = re.search(pattern, clean_output)
    
    if match:
        docker_path = match.group(1)
        return _map_docker_to_host_path(docker_path, config)
    
    return None


def penguin_init(config: ConfigParser, fw: str) -> Tuple[subprocess.CompletedProcess, Optional[Path]]:
    """
    Initialize firmware with Penguin and extract the project path.
    
    Args:
        config: Configuration dictionary containing Penguin settings
        fw: Path to the firmware file to initialize
        
    Returns:
        Tuple of (subprocess.CompletedProcess, project_path)
        - CompletedProcess: execution results
        - project_path: Actual host path to the created project (None if parsing failed)
        
    Example:
        >>> result, project_path = penguin_init(config, "/path/to/firmware.bin")
        >>> if result.returncode == 0 and project_path:
        ...     print(f"Project created at: {project_path}")
    """
    print(f"\n===== Running Penguin INIT =====", flush=True)
    
    image = config.get('Penguin', 'image')
    cmd = ["penguin", "--image", image, "init", "--force", fw]
    print(f"[cmd] {cmd}", flush=True)
    
    # Capture output to parse project path
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )
    
    # Print output for visibility
    if result.stdout:
        print(result.stdout, end='', flush=True)
    if result.stderr:
        print(result.stderr, end='', flush=True)
    
    # Parse project path from output
    combined_output = (result.stdout or "") + (result.stderr or "")
    project_path = _parse_project_path_from_output(combined_output, config)
    
    if project_path:
        print(f"[Mapped] Docker path → Host path: {project_path}", flush=True)
    
    return result, project_path


def penguin_run(config: ConfigParser, penguin_proj: Path) -> subprocess.CompletedProcess:
    """
    Run Penguin rehosting for the specified timeout.
    
    Args:
        config: Configuration dictionary containing Penguin settings
        penguin_proj: Path to the Penguin project directory
        
    Returns:
        subprocess.CompletedProcess object with execution results
        
    Example:
        >>> from pathlib import Path
        >>> result = penguin_run(config, Path("projects/firmware_001"))
        >>> if result.returncode == 0:
        ...     print("Rehosting completed successfully")
    """
    iteration_timeout = config.get('Penguin', 'iteration_timeout')
    image = config.get('Penguin', 'image')
    
    print(f"\n===== Running Penguin for {iteration_timeout} minutes =====", flush=True)
    timeout = int(iteration_timeout) * 60
    firmware_config = penguin_proj / "config.yaml"
    cmd = [
        "penguin",
        "--image", image,
        "run", str(firmware_config),
        "--timeout", str(timeout)
    ]
    print(f"[cmd] {cmd}", flush=True)
    result = subprocess.run(cmd)
    return result

