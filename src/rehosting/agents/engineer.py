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
    
    # Available tools for the Engineer
    AVAILABLE_TOOLS = """
Available Tools:
1. yaml_editor: Update YAML configuration files
   - action: update_config
   - params: {file, path, value, reason}
   - Example: Update env.PATH to "/usr/bin:/bin"

2. patch_manager: Enable/disable configuration patches
   - action: enable_patch
   - params: {file, patch, reason}
   - Example: Enable "static_patches/root_shell.yaml"

3. hyperfile_builder: Create virtual file entries
   - action: create_hyperfile
   - params: {file, hyperfile_path, content, reason}
   - Example: Create /proc/version with content "Linux version 4.14.0"

4. core_config: Update core configuration settings
   - action: update_core
   - params: {file, setting, value, reason}
   - Example: Set core.root_shell to true
"""

    SYSTEM_PROMPT = """You are an Engineer agent specialized in implementing firmware rehosting configuration changes.

Your role:
1. Receive a high-level objective/option from the Planner
2. Reason about HOW to implement it using available tools
3. Generate specific tool calls with exact parameters

{tools}

Output Format:
You MUST return ONLY valid JSON with this structure:
{{
  "reasoning": "Brief explanation of your approach",
  "tool_calls": [
    {{
      "tool": "tool_name",
      "action": "action_name",
      "params": {{
        "file": "config.yaml",
        "path": "yaml.path.here",
        "value": "value_here",
        "reason": "why this change is needed"
      }}
    }}
  ]
}}

Rules:
- For environment variables: use yaml_editor with path "env.VARNAME"
- For core settings: use core_config with setting name
- For patches: use patch_manager with patch file path
- For missing files/devices: use hyperfile_builder
- Always provide clear reasons for each change
- Output ONLY the JSON, no markdown, no explanations outside JSON
"""

    def __init__(self, project_path: Path, model: str = "llama3.3:latest", max_retries: int = 2, kb_path: Optional[Path] = None):
        """
        Initialize the Engineer agent.
        
        Args:
            project_path: Path to the Penguin project directory
            model: LLM model to use for reasoning
            max_retries: Maximum retry attempts for invalid LLM responses
            kb_path: Path to knowledge base file (optional)
        """
        self.project_path = project_path
        self.model = model
        self.max_retries = max_retries
        self.kb = get_knowledge_base(kb_path)
        self.state = EngineerState()
    
    def execute_plan(self, plan: Any) -> Dict[str, Any]:
        """
        Execute all options in a plan sequentially.
        
        Args:
            plan: Plan object from the Planner (with 'options' field)
            
        Returns:
            Dictionary with execution results and summary
        """
        if is_verbose():
            verbose_print("=" * 70)
            verbose_print("ENGINEER: STARTING PLAN EXECUTION", prefix="[ENGINEER]")
            verbose_print("=" * 70)
            verbose_print(f"Plan ID: {plan.id}", prefix="[ENGINEER]")
            verbose_print(f"Total Options: {len(plan.options)}", prefix="[ENGINEER]")
            verbose_print("=" * 70)
        
        print(f"\n🔧 Engineer: Executing plan {plan.id} with {len(plan.options)} options...")
        
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
            
            # Record the action
            action_record = ActionRecord(
                step_id=option_id,
                tool=tool,
                input=params,
                output_uri=execution_result.get("file_path", ""),
                summary=execution_result.get("message", ""),
                status=execution_result.get("status", "unknown")
            )
            
            self.state.action_records.append(action_record)
            results["action_records"].append(action_record)
            
            # Update counters
            if execution_result.get("status") == "success":
                self.state.completed_options.append(option_id)
                results["completed"] += 1
                print(f"      ✅ Success: {execution_result.get('message', '')}")
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
            verbose_print(f"Failed: {results['failed']}", prefix="[ENGINEER]")
            verbose_print(f"Total Actions: {len(results['action_records'])}", prefix="[ENGINEER]")
            verbose_print("=" * 70)
        
        print(f"\n✨ Plan execution complete:")
        print(f"   ✅ Completed: {results['completed']}")
        print(f"   ❌ Failed: {results['failed']}")
        
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
            tool_calls = self._call_llm_for_implementation(description, option_data)
            
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
            
            # Execute each tool call (or print what would be done)
            all_changes = []
            messages = []
            
            for i, tool_call in enumerate(tool_calls, 1):
                tool = tool_call.get("tool", "unknown")
                action = tool_call.get("action", "unknown")
                params = tool_call.get("params", {})
                
                # Print what would be done
                file_path = params.get("file", "config.yaml")
                reason = params.get("reason", "")
                
                verbose_print(f"[WOULD EXECUTE {i}/{len(tool_calls)}] Tool: {tool}", prefix="[ENGINEER]")
                verbose_print(f"  File: {self.project_path / file_path}", prefix="[ENGINEER]")
                verbose_print(f"  Action: {action}", prefix="[ENGINEER]")
                
                if tool == "yaml_editor":
                    yaml_path = params.get("path", "")
                    value = params.get("value", "")
                    verbose_print(f"  Would update: {yaml_path} = {value}", prefix="[ENGINEER]")
                    all_changes.append(f"Update {yaml_path} = {value}")
                    
                elif tool == "patch_manager":
                    patch_name = params.get("patch", "")
                    verbose_print(f"  Would enable patch: {patch_name}", prefix="[ENGINEER]")
                    all_changes.append(f"Enable patch {patch_name}")
                    
                elif tool == "hyperfile_builder":
                    hyperfile_path = params.get("hyperfile_path", "")
                    content = params.get("content", "")
                    verbose_print(f"  Would create hyperfile: {hyperfile_path}", prefix="[ENGINEER]")
                    verbose_print(f"    Content: {content[:100]}...", prefix="[ENGINEER]")
                    all_changes.append(f"Create hyperfile {hyperfile_path}")
                    
                elif tool == "core_config":
                    setting = params.get("setting", "")
                    value = params.get("value", "")
                    verbose_print(f"  Would update core setting: {setting} = {value}", prefix="[ENGINEER]")
                    all_changes.append(f"Update core.{setting} = {value}")
                
                verbose_print(f"  Reason: {reason}", prefix="[ENGINEER]")
                messages.append(f"{action} via {tool}: {reason}")
            
            return {
                "option_id": option_id,
                "status": "success",
                "message": f"[DRY RUN] {len(tool_calls)} actions planned: " + "; ".join(messages[:2]),
                "file_path": str(self.project_path / "config.yaml"),
                "changes": {"simulated": True, "tool_calls": len(tool_calls), "changes": all_changes}
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
    ) -> List[Dict[str, Any]]:
        """
        Call LLM to determine specific tool calls for implementing this option.
        
        Includes retry mechanism for invalid responses.
        
        Args:
            description: High-level description of what to implement
            option_data: Full option data from planner
            
        Returns:
            List of tool calls to execute (empty list if all retries fail)
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                is_retry = attempt > 0
                
                # Query KB for implementation examples (if enabled)
                kb_examples = self.kb.query_for_engineer(description) if self.kb is not None else []
                
                # Build prompt with KB examples
                kb_context = ""
                if kb_examples:
                    kb_context = "\n\nKnowledge Base Examples:\n"
                    for i, example in enumerate(kb_examples[:3], 1):  # Max 3 examples
                        kb_context += f"\nExample {i}:\n{json.dumps(example, indent=2)}\n"
                    
                    if is_verbose():
                        verbose_print(f"[ENGINEER] Added {len(kb_examples)} KB examples to prompt", prefix="[KB]")
                
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

                system_prompt = self.SYSTEM_PROMPT.format(tools=self.AVAILABLE_TOOLS)
                
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
                tool_calls = result.get("tool_calls", [])
                reasoning = result.get("reasoning", "")
                
                # Validate we got tool calls
                if not tool_calls:
                    last_error = "Response missing 'tool_calls' array or it's empty"
                    verbose_print(f"[ENGINEER] Attempt {attempt + 1} failed: {last_error}")
                    continue
                
                # Validate each tool call has required fields
                for i, tc in enumerate(tool_calls):
                    if not isinstance(tc, dict):
                        last_error = f"Tool call {i} is not a dictionary"
                        verbose_print(f"[ENGINEER] Attempt {attempt + 1} failed: {last_error}")
                        raise ValueError(last_error)
                    
                    required = ["tool", "action", "params"]
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
                
                return tool_calls
                
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
        return []
    
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
        
        if not plan:
            print("[Engineer] Warning: No plan provided, skipping execution")
            return {
                "actions": [],
                "engineer_summary": "No plan to execute"
            }
        
        # Execute the plan
        results = self.execute_plan(plan)
        
        # Return state updates
        return {
            "actions": results["action_records"],
            "engineer_summary": results["summary"],
            "execution_complete": True
        }


# Convenience function for creating an engineer instance
def create_engineer(project_path: Path, model: str = "llama3.3:latest", max_retries: int = 2, kb_path: Optional[Path] = None) -> EngineerAgent:
    """
    Create an Engineer agent instance.
    
    Args:
        project_path: Path to the Penguin project directory
        model: LLM model to use for reasoning
        max_retries: Maximum retry attempts for invalid LLM responses
        kb_path: Path to knowledge base file (optional)
        
    Returns:
        Configured EngineerAgent instance
    """
    return EngineerAgent(project_path, model, max_retries, kb_path)

