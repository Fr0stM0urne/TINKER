#!/usr/bin/env python3
"""
Demo script showing how to use the Penguin module API with real firmware.
"""

import sys
import configparser
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.penguin import PenguinClient


def demo_step_by_step():
    """Demonstrate step-by-step workflow with real firmware."""
    
    # Load configuration
    config = configparser.ConfigParser()
    config.read("config.ini")
    
    print("=" * 60)
    print("PENGUIN CLIENT DEMO - Step by Step Workflow")
    print("=" * 60)
    print()
    
    # Initialize client
    client = PenguinClient(config)
    print(f"✓ Initialized PenguinClient")
    print(f"  Image: {config.get('Penguin', 'image')}")
    print(f"  Timeout: {config.get('Penguin', 'iteration_timeout')} minutes")
    print(f"  Output dir: {config.get('Penguin', 'output_dir')}")
    print()
    
    # Real firmware path
    firmware_path = "/home/renze/workplace/TINKER/resources/firmware/stride.rootfs.tar.gz"
    
    if not Path(firmware_path).exists():
        print(f"✗ Firmware file not found: {firmware_path}")
        print("  Please ensure the firmware file exists before running this demo.")
        return
    
    print(f"📦 Firmware: {firmware_path}")
    print()
    
    # Step 1: Initialize
    print("=" * 60)
    print("STEP 1: Initialize Firmware")
    print("=" * 60)
    print()
    
    try:
        result, project_path = client.init(firmware_path)
        
        if result.returncode == 0 and project_path:
            print(f"\n✓ Initialization successful!")
            print(f"  Project path: {project_path}")
            print()
        else:
            print(f"\n✗ Initialization failed with return code {result.returncode}")
            return
            
    except Exception as e:
        print(f"✗ Error during initialization: {e}")
        return
    
    # Step 2: Run rehosting
    print("=" * 60)
    print("STEP 2: Run Penguin Rehosting")
    print("=" * 60)
    print()
    
    try:
        run_result = client.run(project_path)
        
        if run_result.returncode == 0:
            print(f"\n✓ Rehosting completed!")
        else:
            print(f"\n⚠ Rehosting finished with return code {run_result.returncode}")
        print()
        
    except Exception as e:
        print(f"✗ Error during rehosting: {e}")
        # Continue to results collection anyway
        print("  Continuing to results collection...")
        print()
    
    # Step 3: Collect results
    print("=" * 60)
    print("STEP 3: Collect and Analyze Results")
    print("=" * 60)
    print()
    
    try:
        results = client.get_results(project_path)
        
        if results['success']:
            print(f"✓ Results collected successfully!")
            print(f"  Results directory: {results['results_dir']}")
            print(f"  Run number: {results['run_number']}")
            print()
            
            # Show summary
            print("📊 Summary:")
            print(f"  Files collected: {results['summary']['files_collected']}")
            print(f"  Files missing: {results['summary']['files_missing']}")
            print()
            
            if results['summary']['statistics']:
                print("📈 Statistics:")
                for key, value in results['summary']['statistics'].items():
                    print(f"  - {key}: {value}")
                print()
            
            # Show errors
            errors = client.get_errors(results)
            if errors and errors != ["No errors found"]:
                print("⚠ Errors found:")
                for error in errors[:3]:  # Show first 3
                    print(f"  - {error[:100]}...")
                print()
            else:
                print("✓ No errors found")
                print()
            
            # Format for LLM
            print("=" * 60)
            print("LLM-Formatted Summary:")
            print("=" * 60)
            llm_summary = client.format_for_llm(results)
            print(llm_summary)
            print()
            
        else:
            print(f"✗ Failed to collect results: {results.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"✗ Error collecting results: {e}")
        import traceback
        traceback.print_exc()


def demo_complete_workflow():
    """Demonstrate complete automated workflow."""
    
    # Load configuration
    config = configparser.ConfigParser()
    config.read("config.ini")
    
    print()
    print("=" * 60)
    print("PENGUIN CLIENT DEMO - Complete Workflow (Automated)")
    print("=" * 60)
    print()
    
    # Initialize client
    client = PenguinClient(config)
    
    # Real firmware path
    firmware_path = "/home/renze/workplace/TINKER/resources/firmware/stride.rootfs.tar.gz"
    
    if not Path(firmware_path).exists():
        print(f"✗ Firmware file not found: {firmware_path}")
        return
    
    print(f"📦 Running complete workflow for: stride.rootfs.tar.gz")
    print()
    
    # Execute complete workflow (auto-detects project path)
    try:
        workflow_results = client.execute_workflow(
            firmware_path=firmware_path
            # project_path is optional - will be auto-detected!
        )
        
        print()
        print("=" * 60)
        print("WORKFLOW RESULTS")
        print("=" * 60)
        print()
        
        if workflow_results['success']:
            print(f"✓ Workflow completed successfully!")
            print(f"  Project: {workflow_results['project_path']}")
            print()
            print("LLM Summary:")
            print("-" * 60)
            print(workflow_results['llm_summary'])
        else:
            print(f"✗ Workflow failed")
            print(f"  Errors: {workflow_results['errors']}")
            
    except Exception as e:
        print(f"✗ Workflow error: {e}")
        import traceback
        traceback.print_exc()


def demo_function_api():
    """Demonstrate low-level function API."""
    
    from src.penguin import (
        penguin_init,
        penguin_run,
        get_penguin_results,
        format_results_for_llm
    )
    
    # Load configuration
    config = configparser.ConfigParser()
    config.read("config.ini")
    
    print()
    print("=" * 60)
    print("PENGUIN MODULE DEMO - Low-Level Function API")
    print("=" * 60)
    print()
    
    firmware_path = "/home/renze/workplace/TINKER/resources/firmware/stride.rootfs.tar.gz"
    
    if not Path(firmware_path).exists():
        print(f"✗ Firmware file not found: {firmware_path}")
        print()
        print("Available low-level functions:")
        print("  - penguin_init(config, firmware_path)")
        print("  - penguin_run(config, project_path)")
        print("  - get_penguin_results(config, project_path, run_number=None)")
        print("  - format_results_for_llm(results)")
        return
    
    print(f"📦 Using firmware: stride.rootfs.tar.gz")
    print()
    
    try:
        # Direct function calls
        print("Calling penguin_init()...")
        result, project_path = penguin_init(config, firmware_path)
        
        if result.returncode == 0 and project_path:
            print(f"✓ Init successful: {project_path}")
            print()
            
            print("Calling penguin_run()...")
            run_result = penguin_run(config, project_path)
            print(f"✓ Run completed with code {run_result.returncode}")
            print()
            
            print("Calling get_penguin_results()...")
            results = get_penguin_results(config, project_path)
            
            if results['success']:
                print(f"✓ Results collected")
                print()
                
                print("Calling format_results_for_llm()...")
                llm_summary = format_results_for_llm(results)
                print(llm_summary[:300] + "...")
        else:
            print(f"✗ Init failed")
            
    except Exception as e:
        print(f"✗ Error: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Penguin Client Demo")
    parser.add_argument(
        "--mode",
        choices=["step", "workflow", "functions", "all"],
        default="step",
        help="Demo mode to run"
    )
    args = parser.parse_args()
    
    if args.mode == "step" or args.mode == "all":
        demo_step_by_step()
    
    if args.mode == "workflow" or args.mode == "all":
        demo_complete_workflow()
    
    if args.mode == "functions" or args.mode == "all":
        demo_function_api()
    
    print()
    print("=" * 60)
    print("✓ Demo complete!")
    print("=" * 60)
    print()
    print("Usage:")
    print("  python examples/penguin_client_demo.py --mode step       # Step-by-step (default)")
    print("  python examples/penguin_client_demo.py --mode workflow   # Complete workflow")
    print("  python examples/penguin_client_demo.py --mode functions  # Low-level API")
    print("  python examples/penguin_client_demo.py --mode all        # All demos")
    print()

