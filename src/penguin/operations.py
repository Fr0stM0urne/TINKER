"""Core Penguin operations: initialization and execution."""

import subprocess
import re
import sys
import threading
from typing import Optional, Tuple, List
from pathlib import Path
from configparser import ConfigParser


class OutputCapture:
    """Capture subprocess output in real-time while displaying it."""

    def __init__(self):
        self.lines: List[str] = []
        self.lock = threading.Lock()

    def write(self, text: str) -> None:
        """Write text to both capture buffer and stdout."""
        with self.lock:
            self.lines.append(text)

        # Also write to stdout for real-time display
        sys.stdout.write(text)
        sys.stdout.flush()

    def flush(self) -> None:
        """Flush both capture buffer and stdout."""
        with self.lock:
            pass  # Lines are already captured
        sys.stdout.flush()

    def get_combined_output(self) -> str:
        """Get all captured output as a single string."""
        with self.lock:
            return ''.join(self.lines)


def _run_with_realtime_capture(cmd: List[str], description: str) -> Tuple[subprocess.CompletedProcess, str]:
    """
    Run command with real-time output capture.

    Args:
        cmd: Command to run as list
        description: Description for logging

    Returns:
        Tuple of (subprocess result, combined output)
    """
    print(f"\n===== Running {description} =====", flush=True)
    print(f"[cmd] {cmd}", flush=True)

    # Create output capture
    capture = OutputCapture()

    try:
        # Run with real-time output capture
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Merge stderr into stdout
            text=True,
            bufsize=1,  # Line buffered
        )

        # Process output line by line to capture while displaying
        if result.stdout:
            for line in result.stdout.splitlines(keepends=True):
                capture.write(line)

        # Get final combined output
        combined_output = capture.get_combined_output()

        # Add to result for LLM context
        result._merged_output = combined_output.strip()

        return result, combined_output

    except Exception as e:
        error_msg = f"Error running {description}: {e}"
        capture.write(error_msg)
        result = subprocess.CompletedProcess(cmd, 1, stdout=error_msg)
        result._merged_output = error_msg
        return result, error_msg


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
    image = config.get('Penguin', 'image')
    version = config.get('Penguin', 'version')
    image_version = f"{image}:{version}"
    cmd = ["penguin", "--image", image_version, "init", "--force", fw]

    # Run with real-time capture
    result, combined_output = _run_with_realtime_capture(cmd, "Penguin INIT")

    # Parse project path from output
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
    version = config.get('Penguin', 'version')
    image_version = f"{image}:{version}"
    
    
    timeout = int(iteration_timeout) * 60
    firmware_config = penguin_proj / "config.yaml"
    cmd = [
        "penguin",
        "--image", image_version,
        "run", str(firmware_config),
        "--timeout", str(timeout)
    ]

    # Run with real-time capture
    result, combined_output = _run_with_realtime_capture(cmd, f"Penguin for {iteration_timeout} minutes")

    return result

