"""
Engineer agent for executing configuration update plans.

The Engineer receives approved plans from the Planner and executes them
sequentially using available tools.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import json
from ollama import chat, ChatResponse

from src.rehosting.schemas import ActionRecord
from src.rehosting.knowledge_base import KnowledgeBase, get_knowledge_base
from src.rehosting.tools.config_tools import ConfigToolRegistry
from src.rehosting.tools.tool_definitions import get_all_tool_schemas, get_tool_definition
from src.settings import is_verbose, verbose_print


class EngineerState(BaseModel):
    """State specific to the Engineer agent (focused context, not shared with planner)."""
    
    current_option_id: Optional[str] = Field(
        default=None,
        description="ID of the option currently being executed"
    )
    completed_options: List[str] = Field(
        default_factory=list,
        description="List of option IDs that have been completed"
    )
    failed_options: List[str] = Field(
        default_factory=list,
        description="List of option IDs that failed"
    )
    action_records: List[ActionRecord] = Field(
        default_factory=list,
        description="Detailed records of all actions taken"
    )


class EngineerAgent:
    """
    Engineer agent that executes configuration update plans.
    
    The Engineer is an LLM agent that:
    1. Receives high-level options from the Planner
    2. Uses LLM to reason about HOW to implement each option
    3. Decides which specific tools to use and parameters
    4. Executes (or simulates) the actions
    5. Does NOT share full context with Planner - focuses only on execution
    
    Design:
    - LLM-powered reasoning about implementation details
    - Translates high-level objectives into concrete tool calls
    - Maintains its own state separate from planner
    - Reports results back to orchestrator
    """
    
    # Available tools for the Engineer (from tool definitions)
    AVAILABLE_TOOLS = get_all_tool_schemas()

    SYSTEM_PROMPT = """You are an Engineer implementing firmware rehosting config changes.

**Your Task:** Convert high-level objectives into specific tool calls.

**Available Tools:** {tools}

**Option Context:**
The planner provides options with optional "metadata" field containing structured data:
- variable_name: Env var name (e.g., "sxid")
- config_path: Path in config (e.g., "env.sxid")
- device_path: Device file path (e.g., "/dev/mtd1")

**Use metadata when available** - it provides precise parameters and avoids ambiguity.

**Output JSON:**
{{
  "reasoning": "Brief explanation",
  "action": "execute" | "skip",
  "tool_calls": [
    {{
      "tool": "tool_name",
      "params": {{"param1": "value1", "reason": "why needed"}}
    }}
  ],
  "skip_reason": "Why skipped (if action='skip')"
}}

**Key Rules:**
- ⚠️ add_environment_variable_placeholder: ONLY ONCE per execution cycle
- For env vars with known values: use set_environment_variable_value
- For missing devices: use add_pseudofile
- ONE action per option
- Output ONLY JSON, no markdown"""

    DISCOVERY_MODE_PROMPT = """🔍 DISCOVERY MODE: Apply or remove discovered environment variable.

## Context
The planner analyzed env_cmp.txt results and decided to either apply a discovered value or remove a failed discovery placeholder.

**Your Task:** Implement the planner's decision using the appropriate tool.

**Available Tools:** {tools}

**Option metadata (use this directly):**
- variable_name: "{variable_name}"
- config_path: "{config_path}"

**Planner's solution structure:**
- action: "set_value" OR "remove_variable"
- path: "env.<variable_name>"
- value: discovered value (if set_value) OR null (if remove)

**Implementation:**
- If solution.action="set_value": Use set_environment_variable_value(name=metadata.variable_name, value=solution.value, reason="Applied discovered value from env_cmp.txt")
- If solution.action="remove_variable": Use remove_environment_variable(name=metadata.variable_name, reason="Discovery failed, no candidates found")

⚠️ Use metadata.variable_name directly - don't parse from path string.

**Output JSON:**
{{
  "reasoning": "Brief explanation of what you're implementing",
  "action": "execute",
  "tool_calls": [{{
    "tool": "set_environment_variable_value" | "remove_environment_variable",
    "params": {{"name": "<variable_name>", "value": "<value_or_omit>", "reason": "<explanation>"}}
  }}]
}}

Output ONLY JSON, no markdown."""

    def __init__(self, project_path: Path, model: str = "llama3.3:latest", max_retries: int = 2, kb_path: Optional[Path] = None, max_options: int = 3):
        """
        Initialize the Engineer agent.
        
        Args:
            project_path: Path to the Penguin project directory
            model: LLM model to use for reasoning
            max_retries: Maximum retry attempts for invalid LLM responses
            kb_path: Path to knowledge base file (optional)
            max_options: Maximum number of options to execute (0 = execute all)
        """
        self.project_path = project_path
        self.model = model
        self.max_retries = max_retries
        self.max_options = max_options
        self.kb = get_knowledge_base(kb_path)
        self.state = EngineerState()
        self.tool_registry = ConfigToolRegistry(project_path)
        self.discovery_mode = False  # Track discovery mode
    
    def execute_plan(self, plan: Any, discovery_mode: bool = False) -> Dict[str, Any]:
        """
        Execute all options in a plan sequentially with LLM-guided tool selection.
        
        The Engineer uses LLM to reason about HOW to implement each option:
        1. Receives high-level option (description, problem, solution)
        2. Calls LLM to decide which tools to use and with what parameters
        3. Executes the tool calls via ConfigToolRegistry
        4. Records results for each action
        
        Discovery mode behavior:
        - In discovery mode: Typically only ONE option (apply or remove)
        - LLM uses specialized DISCOVERY_MODE_PROMPT
        - Option metadata provides variable_name directly
        
        Args:
            plan: Plan object from the Planner (with 'options' field)
            discovery_mode: Whether in discovery mode (affects prompts and max_options)
            
        Returns:
            Dictionary with:
            - "action_records": List of ActionRecord objects
            - "summary": List of execution summaries
            - "success": Boolean indicating overall success
        """
        self.discovery_mode = discovery_mode
        
        if is_verbose():
            verbose_print("=" * 70)
            verbose_print("ENGINEER: STARTING PLAN EXECUTION", prefix="[ENGINEER]")
            verbose_print("=" * 70)
            verbose_print(f"Plan ID: {plan.id}", prefix="[ENGINEER]")
            verbose_print(f"Total Options: {len(plan.options)}", prefix="[ENGINEER]")
            verbose_print(f"Discovery Mode: {discovery_mode}", prefix="[ENGINEER]")
            verbose_print("=" * 70)
        
        total_options = len(plan.options)
        print(f"\n🔧 Engineer: Executing plan {plan.id} with {total_options} options...")
        
        # Reset state for new plan
        self.state = EngineerState()
        
        # Sort options by priority (critical -> high -> medium -> low)
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_options = sorted(
            plan.options,
            key=lambda opt: priority_order.get(
                opt.get("priority") if isinstance(opt, dict) else getattr(opt, "priority", "low"),
                999
            )
        )
        
        # Limit number of options to execute
        if self.max_options > 0 and len(sorted_options) > self.max_options:
            if is_verbose():
                verbose_print(f"[ENGINEER] Limiting execution to {self.max_options} options (out of {len(sorted_options)} total)", prefix="[ENGINEER]")
            print(f"   ⚠️  Limiting to {self.max_options} highest priority options (out of {len(sorted_options)} total)")
            sorted_options = sorted_options[:self.max_options]
        
        results = {
            "plan_id": plan.id,
            "total_options": len(sorted_options),
            "completed": 0,
            "failed": 0,
            "skipped": 0,
            "action_records": [],
            "summary": []
        }
        
        # Execute each option in sequence
        for i, option in enumerate(sorted_options, 1):
            # Handle both dict and object formats
            if isinstance(option, dict):
                option_id = option.get("option_id", str(i))
                description = option.get("description", "No description")
                action = option.get("action", "unknown")
                tool = option.get("tool", "unknown")
                params = option.get("params", {})
                priority = option.get("priority", "medium")
            else:
                option_id = getattr(option, "option_id", str(i))
                description = getattr(option, "description", "No description")
                action = getattr(option, "action", "unknown")
                tool = getattr(option, "tool", "unknown")
                params = getattr(option, "params", {})
                priority = getattr(option, "priority", "medium")
            
            self.state.current_option_id = option_id
            
            if is_verbose():
                verbose_print(f"\n[Option {i}/{len(sorted_options)}]", prefix="[ENGINEER]")
                verbose_print(f"  ID: {option_id}", prefix="[ENGINEER]")
                verbose_print(f"  Priority: {priority}", prefix="[ENGINEER]")
                verbose_print(f"  Action: {action}", prefix="[ENGINEER]")
                verbose_print(f"  Tool: {tool}", prefix="[ENGINEER]")
                verbose_print(f"  Description: {description}", prefix="[ENGINEER]")
            
            print(f"\n  [{i}/{len(sorted_options)}] [{priority.upper()}] {description}")
            print(f"      Action: {action} | Tool: {tool}")
            
            # Use LLM to determine how to implement this option
            execution_result = self._implement_option(
                option_id=option_id,
                description=description,
                option_data=option if isinstance(option, dict) else {
                    "option_id": option_id,
                    "description": description,
                    "action": action,
                    "tool": tool,
                    "params": params,
                    "priority": priority
                }
            )
            
            # Extract tool information from execution result
            executed_tools = execution_result.get("executed_tools", [])
            # For ActionRecord, use the first tool if multiple were called
            actual_tool = executed_tools[0].get("tool", "unknown") if executed_tools else "unknown"
            actual_params = executed_tools[0].get("params", {}) if executed_tools else {}
            
            # Record the action
            action_record = ActionRecord(
                step_id=option_id,
                tool=actual_tool,
                input=actual_params,
                output_uri=execution_result.get("file_path", ""),
                summary=execution_result.get("message", ""),
                status=execution_result.get("status", "unknown")
            )
            
            self.state.action_records.append(action_record)
            results["action_records"].append(action_record)
            
            # Update counters
            status = execution_result.get("status")
            if status == "success":
                self.state.completed_options.append(option_id)
                results["completed"] += 1
                print(f"      ✅ Success: {execution_result.get('message', '')}")
            elif status == "skipped":
                results["skipped"] += 1
                print(f"      ⏭️  Skipped: {execution_result.get('message', '')}")
            else:
                self.state.failed_options.append(option_id)
                results["failed"] += 1
                print(f"      ❌ Failed: {execution_result.get('message', '')}")
            
            results["summary"].append({
                "option_id": option_id,
                "description": description,
                "status": execution_result.get("status"),
                "message": execution_result.get("message")
            })
        
        # Final summary
        if is_verbose():
            verbose_print("=" * 70)
            verbose_print("ENGINEER: PLAN EXECUTION COMPLETE", prefix="[ENGINEER]")
            verbose_print("=" * 70)
            verbose_print(f"Completed: {results['completed']}", prefix="[ENGINEER]")
            verbose_print(f"Skipped: {results['skipped']}", prefix="[ENGINEER]")
            verbose_print(f"Failed: {results['failed']}", prefix="[ENGINEER]")
            verbose_print(f"Total Actions: {len(results['action_records'])}", prefix="[ENGINEER]")
            verbose_print("=" * 70)
        
        print(f"\n✨ Plan execution complete:")
        print(f"   ✅ Completed: {results['completed']}")
        print(f"   ⏭️  Skipped: {results['skipped']}")
        print(f"   ❌ Failed: {results['failed']}")
        
        # Show configuration changes if any
        if results['completed'] > 0:
            self.tool_registry.print_config_summary()
            self.tool_registry.print_config_diff()
        
        return results
    
    def _implement_option(
        self,
        option_id: str,
        description: str,
        option_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Use LLM to determine how to implement this high-level option.
        
        Args:
            option_id: Unique identifier for this option
            description: Human-readable description of what to do
            option_data: Full option data from the plan
            
        Returns:
            Dictionary with execution results
        """
        try:
            if is_verbose():
                verbose_print(f"[LLM REASONING] Determining how to implement option {option_id}", prefix="[ENGINEER]")
                verbose_print(f"  Description: {description}", prefix="[ENGINEER]")
            
            # Call LLM to reason about implementation (with retries)
            llm_response = self._call_llm_for_implementation(description, option_data)
            
            # Check if LLM chose to skip this option
            if llm_response.get("action") == "skip":
                skip_reason = llm_response.get("skip_reason", "No reason provided")
                if is_verbose():
                    verbose_print(f"[SKIP] {skip_reason}", prefix="[ENGINEER]")
                
                return {
                    "option_id": option_id,
                    "status": "skipped",
                    "message": f"Skipped: {skip_reason}",
                    "file_path": "",
                    "changes": {"skipped": True, "reason": skip_reason}
                }
            
            # Get tool calls from response
            tool_calls = llm_response.get("tool_calls", [])
            
            # Check if we got valid tool calls
            if not tool_calls:
                return {
                    "option_id": option_id,
                    "status": "failed",
                    "message": "LLM failed to generate valid tool calls after retries",
                    "file_path": "",
                    "changes": {}
                }
            
            if is_verbose():
                verbose_print(f"[LLM RESULT] Generated {len(tool_calls)} tool calls", prefix="[ENGINEER]")
            
            # Execute each tool call
            all_changes = []
            messages = []
            successful_calls = 0
            placeholder_tool_used = False  # Track if we've used the placeholder tool
            
            for i, tool_call in enumerate(tool_calls, 1):
                tool_name = tool_call.get("tool", "unknown")
                params = tool_call.get("params", {})
                
                # CRITICAL SAFEGUARD: Prevent multiple placeholder calls
                if tool_name == "add_environment_variable_placeholder":
                    # Check if already used in previous options
                    for record in self.state.action_records:
                        if record.tool == "add_environment_variable_placeholder":
                            error_msg = "⚠️ BLOCKED: add_environment_variable_placeholder already called in a previous option. Only ONE placeholder variable allowed per rehosting cycle."
                            verbose_print(f"  🚫 {error_msg}", prefix="[ENGINEER]")
                            messages.append(error_msg)
                            continue
                    
                    # Check if already used in current option
                    if placeholder_tool_used:
                        error_msg = "⚠️ BLOCKED: Multiple add_environment_variable_placeholder calls detected. Only ONE allowed."
                        verbose_print(f"  🚫 {error_msg}", prefix="[ENGINEER]")
                        messages.append(error_msg)
                        continue
                    
                    placeholder_tool_used = True
                
                verbose_print(f"[EXECUTING {i}/{len(tool_calls)}] Tool: {tool_name}", prefix="[ENGINEER]")
                verbose_print(f"  Params: {json.dumps(params, indent=2)}", prefix="[ENGINEER]")
                
                # Get the tool function from registry
                tool_func = self.tool_registry.get_tool(tool_name)
                if not tool_func:
                    error_msg = f"Unknown tool: {tool_name}"
                    verbose_print(f"  ❌ {error_msg}", prefix="[ENGINEER]")
                    messages.append(f"Failed: {error_msg}")
                    continue
                
                try:
                    # Call the tool with parameters
                    result = tool_func(**params)
                    
                    if result.get("status") == "success":
                        successful_calls += 1
                        verbose_print(f"  ✅ Success: {result.get('message', '')}", prefix="[ENGINEER]")
                        messages.append(f"Success: {result.get('message', '')}")
                        
                        # Collect changes for summary
                        changes = result.get("changes", {})
                        if changes:
                            all_changes.append(changes)
                    else:
                        error_msg = result.get("message", "Unknown error")
                        verbose_print(f"  ❌ Failed: {error_msg}", prefix="[ENGINEER]")
                        messages.append(f"Failed: {error_msg}")
                        
                except Exception as e:
                    error_msg = f"Tool execution error: {str(e)}"
                    verbose_print(f"  ❌ {error_msg}", prefix="[ENGINEER]")
                    messages.append(f"Error: {error_msg}")
            
            # Determine overall status
            if successful_calls == len(tool_calls):
                status = "success"
                message = f"All {len(tool_calls)} tool calls executed successfully"
            elif successful_calls > 0:
                status = "partial"
                message = f"{successful_calls}/{len(tool_calls)} tool calls succeeded"
            else:
                status = "failed"
                message = "All tool calls failed"
            
            return {
                "option_id": option_id,
                "status": status,
                "message": message,
                "file_path": str(self.project_path / "config.yaml"),
                "changes": {"tool_calls": len(tool_calls), "successful": successful_calls, "changes": all_changes},
                "executed_tools": tool_calls  # Add the actual tool calls for ActionRecord
            }
            
        except Exception as e:
            error_msg = f"Exception during LLM reasoning: {str(e)}"
            verbose_print(error_msg, prefix="[ENGINEER]")
            import traceback
            if is_verbose():
                verbose_print(traceback.format_exc(), prefix="[ENGINEER]")
            
            return {
                "option_id": option_id,
                "status": "failed",
                "message": error_msg,
                "file_path": "",
                "changes": {}
            }
    
    def _call_llm_for_implementation(
        self,
        description: str,
        option_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call LLM to determine specific tool calls for implementing this option.
        
        Includes retry mechanism for invalid responses.
        
        Args:
            description: High-level description of what to implement
            option_data: Full option data from planner
            
        Returns:
            Dictionary with action, tool_calls, and optional skip_reason
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                is_retry = attempt > 0
                
                # Query KB for implementation guidance (if enabled)
                kb_guidance = self.kb.query_for_engineer(description) if self.kb is not None else []
                
                # Build prompt with KB guidance
                kb_context = ""
                if kb_guidance:
                    kb_context = "\n\nKnowledge Base Guidance:\n"
                    for i, guidance in enumerate(kb_guidance[:3], 1):  # Max 3 guidance items
                        kb_context += f"\nGuidance {i} - {guidance.get('title', 'Unknown Issue')}:\n"
                        kb_context += f"  Tool: {guidance.get('tool', 'unknown')}\n"
                        kb_context += f"  Action: {guidance.get('action', 'unknown')}\n"
                        if 'examples' in guidance and guidance['examples']:
                            kb_context += f"  Examples:\n"
                            for j, example in enumerate(guidance['examples'][:2], 1):  # Max 2 examples per guidance
                                kb_context += f"    Example {j}: {json.dumps(example, indent=4)}\n"
                        if 'notes' in guidance and guidance['notes']:
                            kb_context += f"  Notes: {'; '.join(guidance['notes'])}\n"
                        kb_context += "\n"
                    
                    if is_verbose():
                        verbose_print(f"[ENGINEER] Added {len(kb_guidance)} KB guidance items to prompt", prefix="[KB]")
                
                user_prompt = f"""Objective: {description}

Context from Planner:
{json.dumps(option_data, indent=2)}

Project Path: {self.project_path}
Config File: config.yaml
{kb_context}
Task: Determine the specific tool calls needed to implement this objective.
Consider what files need to be modified, what values to set, and why.
Use the Knowledge Base examples as reference for similar cases.

Generate the implementation plan as JSON."""

                if is_retry and last_error:
                    user_prompt += f"\n\nPREVIOUS ATTEMPT FAILED: {last_error}\nPlease output VALID JSON matching the schema exactly."

                # Format tools for the prompt
                tools_text = json.dumps(self.AVAILABLE_TOOLS, indent=2)
                
                # Use discovery mode prompt if in discovery mode
                if self.discovery_mode:
                    # Extract metadata for discovery mode prompt
                    metadata = option_data.get("metadata", {})
                    variable_name = metadata.get("variable_name", "unknown")
                    config_path = metadata.get("config_path", f"env.{variable_name}")
                    
                    system_prompt = self.DISCOVERY_MODE_PROMPT.format(
                        tools=tools_text,
                        variable_name=variable_name,
                        config_path=config_path
                    )
                    if is_verbose():
                        verbose_print("[ENGINEER] Using DISCOVERY MODE prompt", prefix="[LLM]")
                        verbose_print(f"[ENGINEER] Metadata: variable_name={variable_name}, config_path={config_path}", prefix="[LLM]")
                else:
                    system_prompt = self.SYSTEM_PROMPT.format(tools=tools_text)
                
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
                
                if is_verbose():
                    verbose_print("=" * 70)
                    verbose_print(f"CALLING LLM FOR IMPLEMENTATION (Attempt {attempt + 1}/{self.max_retries})", prefix="[ENGINEER]")
                    verbose_print("=" * 70)
                    verbose_print(f"Model: {self.model}", prefix="[ENGINEER]")
                    if is_retry:
                        verbose_print(f"Retry reason: {last_error}", prefix="[ENGINEER]")
                    verbose_print("\n--- USER PROMPT ---")
                    verbose_print(user_prompt)
                    verbose_print("=" * 70)
                
                # Call LLM
                response: ChatResponse = chat(
                    model=self.model,
                    messages=messages,
                    format="json",
                    options={
                        "temperature": 0.2 if is_retry else 0.3,  # Lower temp on retry
                        "num_predict": 1024,
                    }
                )
                
                llm_response = response['message']['content']
                
                if is_verbose():
                    verbose_print("=" * 70)
                    verbose_print("LLM RESPONSE", prefix="[ENGINEER]")
                    verbose_print("=" * 70)
                    verbose_print(llm_response)
                    verbose_print("=" * 70)
                
                # Parse response
                result = json.loads(llm_response)
                action = result.get("action", "execute")
                tool_calls = result.get("tool_calls", [])
                reasoning = result.get("reasoning", "")
                skip_reason = result.get("skip_reason", "")
                
                # Validate action
                if action not in ["execute", "skip"]:
                    last_error = f"Invalid action '{action}'. Must be 'execute' or 'skip'"
                    verbose_print(f"[ENGINEER] Attempt {attempt + 1} failed: {last_error}")
                    continue
                
                # If skipping, validate skip_reason
                if action == "skip":
                    if not skip_reason:
                        last_error = "Action is 'skip' but no skip_reason provided"
                        verbose_print(f"[ENGINEER] Attempt {attempt + 1} failed: {last_error}")
                        continue
                    # Return skip response
                    if is_verbose() and reasoning:
                        verbose_print(f"[LLM REASONING] {reasoning}", prefix="[ENGINEER]")
                    return {"action": "skip", "skip_reason": skip_reason, "reasoning": reasoning}
                
                # If executing, validate we got tool calls
                if not tool_calls:
                    last_error = "Action is 'execute' but no tool_calls provided"
                    verbose_print(f"[ENGINEER] Attempt {attempt + 1} failed: {last_error}")
                    continue
                
                # Validate each tool call has required fields
                for i, tc in enumerate(tool_calls):
                    if not isinstance(tc, dict):
                        last_error = f"Tool call {i} is not a dictionary"
                        verbose_print(f"[ENGINEER] Attempt {attempt + 1} failed: {last_error}")
                        raise ValueError(last_error)
                    
                    required = ["tool", "params"]
                    missing = [f for f in required if f not in tc]
                    if missing:
                        last_error = f"Tool call {i} missing fields: {missing}"
                        verbose_print(f"[ENGINEER] Attempt {attempt + 1} failed: {last_error}")
                        raise ValueError(last_error)
                
                # Success!
                if is_verbose() and reasoning:
                    verbose_print(f"[LLM REASONING] {reasoning}", prefix="[ENGINEER]")
                
                if is_retry:
                    verbose_print(f"[ENGINEER] Success on retry attempt {attempt + 1}", prefix="[ENGINEER]")
                
                return {"action": "execute", "tool_calls": tool_calls, "reasoning": reasoning}
                
            except json.JSONDecodeError as e:
                last_error = f"Invalid JSON: {str(e)}"
                verbose_print(f"[ENGINEER] Attempt {attempt + 1} failed: {last_error}")
                
            except ValueError as e:
                last_error = str(e)
                # Already logged above
                
            except Exception as e:
                last_error = f"Unexpected error: {str(e)}"
                verbose_print(f"[ENGINEER] Attempt {attempt + 1} failed: {last_error}")
        
        # All retries exhausted
        verbose_print(f"[ENGINEER] All {self.max_retries} attempts failed. Last error: {last_error}", prefix="[ENGINEER]")
        return {"action": "execute", "tool_calls": [], "reasoning": ""}
    
    def get_state(self) -> EngineerState:
        """Get the current state of the Engineer."""
        return self.state
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph node interface - callable that receives and updates state.
        
        Args:
            state: Current workflow state (expects 'plan' key)
            
        Returns:
            State updates to merge (includes action records)
        """
        plan = state.get("plan")
        discovery_mode = state.get("discovery_mode", False)
        
        if not plan:
            print("[Engineer] Warning: No plan provided, skipping execution")
            return {
                "actions": [],
                "engineer_summary": "No plan to execute",
                "discovery_mode": False  # Exit discovery mode if we were in it
            }
        
        # Execute the plan with discovery mode if applicable
        results = self.execute_plan(plan, discovery_mode=discovery_mode)
        
        # Return state updates
        # Exit discovery mode after execution
        return {
            "actions": results["action_records"],
            "engineer_summary": results["summary"],
            "execution_complete": True,
            "discovery_mode": False,  # Always exit discovery mode after engineer executes
            "discovery_variable": ""  # Clear the variable
        }


# Convenience function for creating an engineer instance
def create_engineer(project_path: Path, model: str = "llama3.3:latest", max_retries: int = 2, kb_path: Optional[Path] = None, max_options: int = 3) -> EngineerAgent:
    """
    Create an Engineer agent instance.
    
    Args:
        project_path: Path to the Penguin project directory
        model: LLM model to use for reasoning
        max_retries: Maximum retry attempts for invalid LLM responses
        kb_path: Path to knowledge base file (optional)
        max_options: Maximum number of options to execute (0 = execute all)
        
    Returns:
        Configured EngineerAgent instance
    """
    return EngineerAgent(project_path, model, max_retries, kb_path, max_options)

