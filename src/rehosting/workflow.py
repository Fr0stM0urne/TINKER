"""
Main workflow orchestrator for LLM-guided firmware rehosting.

This is the entry point for new rehosting experiments.
Input: New firmware binary
Output: Updated Penguin configuration file
"""

import configparser
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# Ensure parent directory is in path for imports
if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from rehosting.agents.firmware_planner import FirmwarePlannerAgent
from rehosting.graph import create_rehosting_workflow
from src.penguin import PenguinClient
from src.rehosting.schemas import State
from src.settings import is_verbose, verbose_print


def rehost_firmware(
    config: configparser.ConfigParser,
    firmware_path: str,
    output_config_path: Optional[str] = None,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Main entry point for firmware rehosting workflow.
    
    Args:
        config: Configuration from config.ini
        firmware_path: Path to firmware binary to rehost
        output_config_path: Optional path for updated config file
        verbose: Enable verbose output
        
    Returns:
        Dictionary with workflow results including updated config
    """
    workflow_state = {
        "firmware_path": firmware_path,
        "success": False,
        "penguin_project": None,
        "initial_results": None,
        "config_update_plan": None,
        "updated_config_path": None,
        "errors": []
    }
    
    print("=" * 70)
    print("🚀 LLM-GUIDED FIRMWARE REHOSTING WORKFLOW")
    print("=" * 70)
    print()
    
    # Step 1: Validate inputs
    print("📋 Step 1: Validating inputs...")
    if not _validate_inputs(firmware_path, config):
        workflow_state["errors"].append("Input validation failed")
        return workflow_state
    print("  ✓ Inputs validated")
    print()
    
    # Step 2: Initialize LLM agents
    print("🤖 Step 2: Initializing LLM agents...")
    try:
        # Use base planner for now (will be extended)
        model = config.get('Ollama', 'model')
        planner = FirmwarePlannerAgent(model=model)
        print(f"  ✓ Planner initialized with model: {model}")
    except Exception as e:
        workflow_state["errors"].append(f"LLM initialization failed: {e}")
        return workflow_state
    print()
    
    # Step 3: Run Penguin init and first rehost
    print("🐧 Step 3: Running Penguin init and first rehost...")
    penguin_client = PenguinClient(config)
    
    try:
        # Init
        init_result, project_path = penguin_client.init(firmware_path)
        if init_result.returncode != 0 or not project_path:
            workflow_state["errors"].append("Penguin init failed")
            return workflow_state
        
        workflow_state["penguin_project"] = str(project_path)
        print(f"  ✓ Project initialized at: {project_path}")
        
        # First run
        run_result = penguin_client.run(project_path)
        print(f"  ✓ First rehost completed (exit code: {run_result.returncode})")
        
        # Collect results
        results = penguin_client.get_results(project_path)
        workflow_state["initial_results"] = results

        if results["success"]:
            print(f"  ✓ Results collected from run #{results['run_number']}")
        else:
            print(f"  ⚠ Results collection incomplete")
            
    except Exception as e:
        workflow_state["errors"].append(f"Penguin execution failed: {e}")
        return workflow_state
    print()
    
    # Step 4: Run multi-agent workflow (Planner + Engineer)
    print("🤖 Step 4: Running multi-agent workflow (Planner → Engineer)...")
    try:
        # Get comprehensive formatted results from penguin client
        detailed_results = penguin_client.format_detailed(results)

        # Get command outputs for LLM context
        def clean_output(output: str) -> str:
            import re
            if not output:
                return output
            ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
            return ansi_escape.sub('', output)

        init_output = clean_output(getattr(init_result, '_merged_output', ''))
        run_output = clean_output(getattr(run_result, '_merged_output', ''))

        # Build context with command outputs and detailed results
        context_parts = [
            f"Firmware: {firmware_path}",
            f"Project: {project_path}",
            "",
            "=== PENGUIN INIT OUTPUT ===",
            "Exit code:", str(init_result.returncode),
            "Combined output:", init_output,
            "",
            "=== PENGUIN RUN OUTPUT ===",
            "Exit code:", str(run_result.returncode),
            "Combined output:", run_output,
            "",
            "=== DETAILED PENGUIN RESULTS ===",
            detailed_results,
        ]

        if is_verbose():
            verbose_print("=" * 70)
            verbose_print("WORKFLOW: BUILDING CONTEXT FOR MULTI-AGENT SYSTEM", prefix="[WORKFLOW]")
            verbose_print("=" * 70)
            verbose_print(f"Firmware: {firmware_path}", prefix="[WORKFLOW]")
            verbose_print(f"Project: {project_path}", prefix="[WORKFLOW]")
            verbose_print(f"Context parts: {len(context_parts)} items", prefix="[WORKFLOW]")
            verbose_print("=" * 70)

        # Create and run the multi-agent workflow
        workflow = create_rehosting_workflow(
            config=config,
            project_path=project_path,
            verbose=verbose
        )
        
        final_state = workflow.run(
            firmware_path=firmware_path,
            rag_context=context_parts,
            goal="Analyze Penguin rehosting results and generate configuration update plan that improves firmware execution"
        )
        
        # Extract results from final state
        config_plan = final_state.get("plan")
        actions = final_state.get("actions", [])
        engineer_summary = final_state.get("engineer_summary", [])

        if config_plan:
            workflow_state["config_update_plan"] = config_plan
            workflow_state["actions"] = actions
            workflow_state["engineer_summary"] = engineer_summary
            
            print(f"  ✓ Multi-agent workflow completed")
            print(f"    Plan ID: {config_plan.id}")
            print(f"    Objectives: {len(config_plan.objectives)}")
            print(f"    Options executed: {len(config_plan.options)}")
            print(f"    Actions completed: {len(actions)}")
            
            if is_verbose():
                verbose_print("=" * 70)
                verbose_print("WORKFLOW: MULTI-AGENT EXECUTION COMPLETE", prefix="[WORKFLOW]")
                verbose_print("=" * 70)
                verbose_print(f"Plan ID: {config_plan.id}", prefix="[WORKFLOW]")
                verbose_print(f"Total actions: {len(actions)}", prefix="[WORKFLOW]")
                verbose_print(f"Execution done: {final_state.get('done', False)}", prefix="[WORKFLOW]")
                verbose_print("=" * 70)
        else:
            workflow_state["errors"].append("Multi-agent workflow failed to generate plan")
            return workflow_state
            
    except Exception as e:
        workflow_state["errors"].append(f"Multi-agent workflow failed: {e}")
        import traceback
        traceback.print_exc()
        return workflow_state
    print()
    
    # TODO: Step 5: Validate with Evaluator (future enhancement)
    # TODO: Step 6: Run Penguin again to verify improvements (future enhancement)
    # TODO: Step 7: Iterate until success (future enhancement)
    
    print("=" * 70)
    print("✨ Multi-Agent Workflow Complete")
    print("=" * 70)
    print()
    print("Plan Summary:")
    print(f"  ID: {config_plan.id}")
    print(f"  Objectives:")
    for i, obj in enumerate(config_plan.objectives, 1):
        print(f"    {i}. {obj}")
    print()
    print("Execution Summary:")
    for summary_item in engineer_summary:
        status_icon = "✅" if summary_item.get("status") == "success" else "❌"
        print(f"  {status_icon} {summary_item.get('description', 'N/A')}")
    print()
    
    workflow_state["success"] = True
    return workflow_state


def _validate_inputs(firmware_path: str, config: configparser.ConfigParser) -> bool:
    """Validate inputs before starting workflow."""
    
    # Check firmware file exists
    if not Path(firmware_path).exists():
        print(f"  ✗ Firmware file not found: {firmware_path}")
        return False
    
    # Check required config sections
    required_sections = ['Penguin', 'Ollama']
    for section in required_sections:
        if not config.has_section(section):
            print(f"  ✗ Missing config section: {section}")
            return False
    
    # Check required Penguin keys
    penguin_keys = ['image', 'iteration_timeout', 'output_dir']
    for key in penguin_keys:
        if not config.has_option('Penguin', key):
            print(f"  ✗ Missing Penguin config: {key}")
            return False
    
    # Check required Ollama keys
    if not config.has_option('Ollama', 'model'):
        print(f"  ✗ Missing Ollama model config")
        return False
    
    return True


# Note: Main entry point is now in src/main.py
# This module can still be imported and used directly:
#
# from src.rehosting.workflow import rehost_firmware
# result = rehost_firmware(config, firmware_path)

