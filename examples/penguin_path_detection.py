#!/usr/bin/env python3
"""
Demo script showing automatic project path detection from penguin init.
"""

import sys
import configparser
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.penguin import PenguinClient
from src.penguin.operations import _map_docker_to_host_path, _parse_project_path_from_output


def demo_path_mapping():
    """Demonstrate Docker to host path mapping."""
    
    # Load configuration
    config = configparser.ConfigParser()
    config.read("config.ini")
    
    print("=" * 60)
    print("DOCKER PATH MAPPING DEMO")
    print("=" * 60)
    print()
    
    # Example Docker paths
    docker_paths = [
        "/host_projects/netgearWAX615",
        "/host_projects/firmware_001",
        "/host_projects/my_firmware"
    ]
    
    output_dir = config['Penguin']['output_dir']
    print(f"Output directory from config: {output_dir}")
    print()
    
    for docker_path in docker_paths:
        host_path = _map_docker_to_host_path(docker_path, config)
        print(f"Docker: {docker_path}")
        print(f"  →  Host: {host_path}")
        print()


def demo_output_parsing():
    """Demonstrate parsing penguin init output."""
    
    # Load configuration
    config = configparser.ConfigParser()
    config.read("config.ini")
    
    print("=" * 60)
    print("OUTPUT PARSING DEMO")
    print("=" * 60)
    print()
    
    # Example penguin init output (based on your terminal selection)
    sample_output = """13:32:51 penguin INFO penguin v2.2.6
13:32:51 penguin INFO Note messages referencing /host paths reflect automatically-mapped shared directories based on your command line arguments
13:32:51 penguin INFO Creating project at generated path: /host_projects/netgearWAX615
13:32:54 penguin.gen_config INFO Generating new configuration for /host_firmware/netgearWAX615.rootfs.tar.gz...
13:33:07 penguin.gen_config INFO root_shell patch generated but disabled
13:33:10 penguin INFO Generated config at /host_projects/netgearWAX615/config.yaml"""
    
    print("Sample penguin init output:")
    print("-" * 60)
    print(sample_output[:200] + "...")
    print("-" * 60)
    print()
    
    # Parse the project path
    project_path = _parse_project_path_from_output(sample_output, config)
    
    if project_path:
        print(f"✓ Successfully parsed project path:")
        print(f"  Detected: {project_path}")
        print(f"  Type: {type(project_path)}")
        print(f"  Exists: {project_path.exists()}")
    else:
        print("✗ Failed to parse project path")


def demo_client_usage():
    """Demonstrate PenguinClient with auto-detection."""
    
    # Load configuration
    config = configparser.ConfigParser()
    config.read("config.ini")
    
    print()
    print("=" * 60)
    print("PENGUIN CLIENT AUTO-DETECTION DEMO")
    print("=" * 60)
    print()
    
    print("Usage with auto-detection:")
    print("-" * 60)
    print("""
from src.penguin import PenguinClient

client = PenguinClient(config)

# Initialize - returns (result, project_path)
result, project_path = client.init("resources/firmware/netgearWAX615.rootfs.tar.gz")

if result.returncode == 0 and project_path:
    print(f"✓ Project created at: {project_path}")
    
    # Now run rehosting on the detected path
    run_result = client.run(project_path)
    
    # Collect results
    results = client.get_results(project_path)
    llm_summary = client.format_for_llm(results)
""")
    print("-" * 60)
    print()
    
    print("Or use the simplified workflow (no project path needed):")
    print("-" * 60)
    print("""
# Workflow auto-detects project path from init
workflow_results = client.execute_workflow(
    firmware_path="resources/firmware/netgearWAX615.rootfs.tar.gz"
    # project_path parameter is now optional!
)

if workflow_results["success"]:
    print(f"Project: {workflow_results['project_path']}")
    print(workflow_results["llm_summary"])
""")
    print("-" * 60)


if __name__ == "__main__":
    demo_path_mapping()
    print("\n")
    demo_output_parsing()
    print("\n")
    demo_client_usage()
    print("\n✓ Demo complete!")
    print("\nKey points:")
    print("  1. penguin_init() now returns (result, project_path)")
    print("  2. Project path is auto-detected from Docker output")
    print("  3. /host_projects/ is mapped to config output_dir")
    print("  4. No need to manually specify project paths!")

