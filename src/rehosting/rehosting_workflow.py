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

from rehosting.graph import create_rehosting_workflow
from src.penguin import PenguinClient
from src.settings import is_verbose, verbose_print


def _initialize_penguin(config: configparser.ConfigParser, firmware_path: str) -> tuple[PenguinClient, Optional[Path], Dict[str, Any]]:
    """Initialize Penguin and create project."""
    print("🐧 Penguin init...")
    penguin_client = PenguinClient(config)
    
    try:
        init_result, project_path = penguin_client.init(firmware_path)
        if init_result.returncode != 0 or not project_path:
            return penguin_client, None, {"returncode": init_result.returncode, "output": getattr(init_result, '_merged_output', '')}
        
        print(f"  ✓ Project initialized at: {project_path}")
        return penguin_client, project_path, {"returncode": 0, "output": getattr(init_result, '_merged_output', '')}
            
    except Exception as e:
        print(f"  ❌ Penguin init failed: {e}")
        return penguin_client, None, {"error": str(e)}


def _run_penguin_iteration(penguin_client: PenguinClient, project_path: Path, iteration: int) -> Dict[str, Any]:
    """
    Run a single Penguin iteration and collect results.
    
    Returns:
        Combined dict with run output and parsed results from client.run()
    """
    print(f"Iteration {iteration} Running Penguin...")
    combined_results = penguin_client.run(project_path)
    print(f"  ✓ Penguin run completed (exit code: {combined_results['returncode']})")
    
    if combined_results["success"]:
        print(f"  ✓ Results collected from run #{combined_results['run_number']}")
    else:
        print(f"  ⚠ Results collection incomplete")

    return combined_results


def _build_multi_agent_context(
    penguin_client,
    combined_results,
    init_result,
    firmware_path: str,
    project_path: str,
    iteration: int,
    accumulated_actions: list,
    accumulated_engineer_summaries: list
) -> dict[str, str]:
    """
    Build context for multi-agent workflow as a dictionary with source keys.
    
    This function extracts Penguin results as a dict and adds metadata,
    init/run outputs, and previous iteration context. The dict structure
    allows efficient filtering by the Planner (e.g., in discovery mode,
    only env_cmp.txt and console.log are needed).
    
    Args:
        penguin_client: PenguinClient instance
        combined_results: Combined dict from client.run() containing both
                         run output and parsed results
        init_result: Result object from Penguin init
        firmware_path: Path to firmware binary
        project_path: Path to Penguin project directory
        iteration: Current iteration number (0-indexed)
        accumulated_actions: List of all previous actions
        accumulated_engineer_summaries: List of all previous engineer summaries
        
    Returns:
        Dictionary with keys as source names (e.g., "console.log", "env_cmp.txt")
        and values as the content strings. Special keys:
        - "metadata": Firmware and project paths
        - "penguin_init": Init output
        - "penguin_run": Run output
        - "penguin_results": Summary with stats and errors
        - "previous_iterations": Summary of previous work (if iteration > 0)
    """
    import re
    
    def clean_output(output: str) -> str:
        """Remove ANSI escape codes from terminal output."""
        if not output:
            return output
        ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
        return ansi_escape.sub('', output)
    
    # Clean init output
    init_output = clean_output(getattr(init_result, '_merged_output', ''))
    
    # Run output is already cleaned in client.run()
    run_output = combined_results.get('output', '')
    
    # Start with metadata and init/run outputs
    context_dict = {
        "metadata": f"Firmware: {firmware_path}\nProject: {project_path}",
        "penguin_init": f"Exit code: {init_result.returncode}\n\nOutput:\n{init_output}",
        "penguin_run": f"Exit code: {combined_results['returncode']}\n\nOutput:\n{run_output}",
    }
    
    # Get Penguin results as dict - NO PARSING NEEDED!
    # This directly extracts: console.log, env_cmp.txt, env_missing.yaml,
    # pseudofiles_failures.yaml, and penguin_results summary
    penguin_context = penguin_client.get_context_dict(combined_results)
    context_dict.update(penguin_context)
    
    # Add accumulated context for iterations > 0
    if iteration > 0:
        previous_context_parts = []
        previous_context_parts.append(f"## Previous Iteration Context (Iteration {iteration}):")
        previous_context_parts.append(f"Total previous actions: {len(accumulated_actions)}")
        previous_context_parts.append(f"Total previous engineer summaries: {len(accumulated_engineer_summaries)}")
        
        if accumulated_actions:
            previous_context_parts.append("\nPrevious Actions Summary:")
            for j, action in enumerate(accumulated_actions[-5:], 1):
                previous_context_parts.append(f"  {j}. {action.tool} - {action.status} - {action.summary}")
        
        if accumulated_engineer_summaries:
            previous_context_parts.append("\nPrevious Engineer Summaries:")
            for j, summary in enumerate(accumulated_engineer_summaries[-3:], 1):
                if isinstance(summary, dict):
                    previous_context_parts.append(f"  {j}. {summary.get('status', 'unknown')} - {summary.get('message', 'no message')}")
                else:
                    previous_context_parts.append(f"  {j}. {summary}")
        
        context_dict["previous_iterations"] = "\n".join(previous_context_parts)
    
    return context_dict


def _check_discovery_mode_transitions(
    actions: list,
    discovery_mode: bool,
    discovery_variable: Optional[str],
    final_state: Dict[str, Any]
) -> tuple[bool, Optional[str]]:
    """
    Check for discovery mode entry/exit based on actions executed by Engineer.
    
    Discovery mode is a special workflow state where:
    - Entry: Engineer added a placeholder env var (value="DYNVALDYNVALDYNVAL")
    - Active: Next iteration will analyze env_cmp.txt for discovered values
    - Exit: Engineer applied discovered value or removed failed placeholder
    
    Args:
        actions: List of ActionRecord from current iteration
        discovery_mode: Current discovery mode state
        discovery_variable: Name of variable being discovered (if in discovery mode)
        final_state: Final state from multi-agent workflow
        
    Returns:
        Tuple of (new_discovery_mode, new_discovery_variable)
        - If entering: (True, "variable_name")
        - If exiting: (False, None)
        - If unchanged: (current_mode, current_variable)
    """
    was_in_discovery_mode = discovery_mode
    
    # Check if exiting discovery mode
    if was_in_discovery_mode and final_state.get("discovery_mode") == False:
        print(f"\n✅ EXITING DISCOVERY MODE for variable: {discovery_variable}")
        print(f"   Discovery process completed")
        return False, None
    
    # Check if entering discovery mode (only if not already in it)
    if not was_in_discovery_mode:
        if is_verbose():
            print(f"\n[DEBUG] Checking {len(actions)} actions for add_environment_variable_placeholder")
        
        for action in actions:
            if is_verbose():
                print(f"[DEBUG] Action tool: {action.tool}, input: {action.input}")
            
            if action.tool == "add_environment_variable_placeholder":
                var_name = action.input.get("name", "unknown") if isinstance(action.input, dict) else "unknown"
                print(f"\n🔍 ENTERING DISCOVERY MODE for variable: {var_name}")
                print(f"   Next iteration will focus on discovering value for this variable")
                return True, var_name
    
    return discovery_mode, discovery_variable


def _print_iteration_summary(config_plan: Any, actions: list, accumulated_actions: list):
    """Print summary for a single iteration."""
    print(f"  ✓ Multi-agent workflow completed")
    print(f"    Plan ID: {config_plan.id}")
    print(f"    Objectives: {len(config_plan.objectives)}")
    print(f"    Options executed: {len(config_plan.options)}")
    print(f"    Actions completed: {len(actions)}")
    print(f"    Total accumulated actions: {len(accumulated_actions)}")


def _print_final_summary(config: configparser.ConfigParser, workflow_state: Dict[str, Any], accumulated_actions: list):
    """Print final workflow summary."""
    print("=" * 70)
    print("✨ Multi-Agent Workflow Complete")
    print("=" * 70)
    print(f"Total iterations completed: {int(config['Penguin']['max_iter'])}")
    print(f"Total accumulated actions: {len(accumulated_actions)}")
    print()
    
    # Show final plan summary
    final_plan = workflow_state.get("config_update_plan")
    if final_plan:
        print("Final Plan Summary:")
        print(f"  ID: {final_plan.id}")
        print(f"  Objectives:")
        for i, obj in enumerate(final_plan.objectives, 1):
            print(f"    {i}. {obj}")
        print()
    
    # Show final execution summary
    final_summary = workflow_state.get("engineer_summary", [])
    if final_summary:
        print("Final Execution Summary:")
        for summary_item in final_summary:
            status_icon = "✅" if summary_item.get("status") == "success" else "❌"
            print(f"  {status_icon} {summary_item.get('description', 'N/A')}")
        print()
    
    # Show errors
    if workflow_state["errors"]:
        print("Errors encountered:")
        for error in workflow_state["errors"]:
            print(f"  ❌ {error}")
        print()


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
    
    # Validate inputs
    print("📋 Validating inputs...")
    if not _validate_inputs(firmware_path, config):
        workflow_state["errors"].append("Input validation failed")
        return workflow_state
    print("  ✓ Inputs validated")
    print()
    
    # Initialize Penguin
    penguin_client, project_path, init_info = _initialize_penguin(config, firmware_path)
    if not project_path:
        workflow_state["errors"].append("Penguin init failed")
        return workflow_state
    
    workflow_state["penguin_project"] = str(project_path)
    init_result_for_context = type('obj', (object,), {
        'returncode': init_info.get('returncode', 1),
        '_merged_output': init_info.get('output', '')
    })()
    print()

    # Initialize iteration state
    accumulated_actions = []
    accumulated_engineer_summaries = []
    discovery_mode = False
    discovery_variable = None
    
    # Main rehosting loop
    for i in range(int(config["Penguin"]["max_iter"])):
        print(f"Max Iterations: {config['Penguin']['max_iter']}, Current Iteration: {i+1}")

        # Run Penguin iteration
        combined_results = _run_penguin_iteration(penguin_client, project_path, i)
        workflow_state["initial_results"] = combined_results
    
        # Run multi-agent workflow (Planner + Engineer)
        print("🤖 Running multi-agent workflow (Planner → Engineer)...")
        try:
            # Build context for LLM (now returns dict with source keys)
            context_dict = _build_multi_agent_context(
                penguin_client, combined_results, init_result_for_context,
                firmware_path, project_path,
                i, accumulated_actions, accumulated_engineer_summaries
            )

            if is_verbose():
                verbose_print("=" * 70)
                verbose_print("WORKFLOW: BUILDING CONTEXT FOR MULTI-AGENT SYSTEM", prefix="[WORKFLOW]")
                verbose_print("=" * 70)
                verbose_print(f"Firmware: {firmware_path}", prefix="[WORKFLOW]")
                verbose_print(f"Project: {project_path}", prefix="[WORKFLOW]")
                verbose_print("=" * 70)

            # Create and run the multi-agent workflow
            workflow = create_rehosting_workflow(
                config=config,
                project_path=project_path,
                verbose=verbose
            )
            
            # Check if we're in discovery mode
            if discovery_mode:
                print(f"🔍 DISCOVERY MODE active for variable: {discovery_variable}")
            
            final_state = workflow.run(
                firmware_path=firmware_path,
                rag_context=context_dict,
                goal="Analyze Penguin rehosting results and generate configuration update plan that improves firmware execution",
                discovery_mode=discovery_mode,
                discovery_variable=discovery_variable
            )
            
            # Extract and store results
            config_plan = final_state.get("plan")
            actions = final_state.get("actions", [])
            engineer_summary = final_state.get("engineer_summary", [])

            if config_plan:
                workflow_state["config_update_plan"] = config_plan
                workflow_state["actions"] = actions
                workflow_state["engineer_summary"] = engineer_summary
                
                # Accumulate results
                accumulated_actions.extend(actions)
                accumulated_engineer_summaries.extend(engineer_summary)
                
                # Check for discovery mode transitions
                discovery_mode, discovery_variable = _check_discovery_mode_transitions(
                    actions, discovery_mode, discovery_variable, final_state
                )
                
                # Print iteration summary
                _print_iteration_summary(config_plan, actions, accumulated_actions)
                
                if is_verbose():
                    verbose_print("=" * 70)
                    verbose_print("WORKFLOW: MULTI-AGENT EXECUTION COMPLETE", prefix="[WORKFLOW]")
                    verbose_print("=" * 70)
                    verbose_print(f"Plan ID: {config_plan.id}", prefix="[WORKFLOW]")
                    verbose_print(f"Total actions: {len(actions)}", prefix="[WORKFLOW]")
                    verbose_print(f"Accumulated actions: {len(accumulated_actions)}", prefix="[WORKFLOW]")
                    verbose_print(f"Execution done: {final_state.get('done', False)}", prefix="[WORKFLOW]")
                    verbose_print("=" * 70)
            else:
                workflow_state["errors"].append("Multi-agent workflow failed to generate plan")
                print(f"  ❌ Multi-agent workflow failed to generate plan (iteration {i+1})")
                
        except Exception as e:
            workflow_state["errors"].append(f"Multi-agent workflow failed: {e}")
            print(f"  ❌ Multi-agent workflow exception (iteration {i+1}): {e}")
            import traceback
            traceback.print_exc()
        print()
    
    # Print final summary
    _print_final_summary(config, workflow_state, accumulated_actions)
    
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

