"""
Extended Planner agent specialized for firmware rehosting configuration.

This extends the base PlannerAgent with firmware-specific knowledge and prompts.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from pathlib import Path
from src.rehosting.schemas import State
from src.rehosting.knowledge_base import KnowledgeBase, get_knowledge_base
import json
import uuid
from ollama import chat, ChatResponse
from src.settings import is_verbose, verbose_print


class FirmwareConfigPlan(BaseModel):
    """Lightweight plan schema for firmware configuration updates."""

    id: str = Field(description="Unique identifier for this plan")
    objectives: List[str] = Field(description="High-level objectives to achieve")
    options: List[Dict[str, Any]] = Field(
        description="List of possible configuration update options for evaluator/engineer to prioritize"
    )

class FirmwarePlannerAgent:
    """
    Planner agent specialized for firmware rehosting configuration updates.
    
    This agent understands:
    - Penguin configuration format (YAML)
    - Common firmware rehosting issues (missing env vars, failed peripherals, etc.)
    - Architecture-specific requirements (ARM, MIPS, x86)
    - Configuration sections: core, patches, env, pseudofiles, nvram, netdevs
    """
    
    # Override schema for firmware configuration plans
    EXPECTED_RESPONSE_SCHEMA = {
        "id": "fw_plan_<unique_id>",
        "objectives": ["<objective1>", "<objective2>"],
        "options": [
            {
                "option_id": "1",
                "description": "<brief_summary>",
                "problem": "<specific_problem>",
                "solution": "<solution_approach>",
                "priority": "critical|high|medium|low",
                "impact": "<expected_impact>",
                "metadata": {
                    "variable_name": "<var_name_if_env_var_issue>",
                    "config_path": "<path_if_applicable>",
                    "device_path": "<device_path_if_pseudofile>"
                }
            }
        ]
    }
    
    # System prompt - contains all instructions and guidelines
    SYSTEM_PROMPT = """You are a firmware rehosting planner analyzing Penguin configuration issues.

## Your Task
Analyze the provided goal, context, and constraints, then create a comprehensive plan to achieve the goal. Output the plan in JSON format following the schema provided at the end.

## Key Configuration Targets

**env** (environment variables): Main focus if env_missing.yaml or env_cmp.txt present
**pseudofiles** (device files): Add if pseudofiles_failures.yaml shows missing devices
**core/patches**: Rarely modified (auto-handled)

## Common Patterns

1. **Missing env vars WITHOUT known values**: Add ONE placeholder for discovery (⚠️ only ONE per cycle)
2. **Missing devices**: Add pseudofile entries for /dev/*, /proc/*, /sys/* paths
3. **Crashes/panics**: Check env vars and device dependencies first

## Discovery Constraint
⚠️ CRITICAL: Only ONE environment variable can use placeholder (DYNVALDYNVALDYNVAL) per rehosting cycle. If multiple unknowns exist, prioritize the most critical ONE.

## Important Notes
- **metadata field**: Include structured data for Engineer (e.g., variable_name="sxid", config_path="env.sxid" for env vars, or device_path="/dev/mtd1" for pseudofiles). Omit fields not applicable. IMPORTANT: Don't add metadata if not relevant to the option!
- Priority levels: critical (crashes) > high (missing critical data) > medium (nice-to-have) > low (optimization)
- Output ONLY valid JSON, no markdown."""

    RETRY_SYSTEM_PROMPT = """Your previous response was invalid JSON. Output ONLY valid JSON matching this schema:
{schema}

Required: id, objectives (array), options (array with option_id, description, problem, solution, priority, impact)
No markdown, no explanations, just the JSON object."""

    DISCOVERY_MODE_PROMPT = """🔍 DISCOVERY MODE: Resolve environment variable with discovered value

## What is Discovery Mode?
In the previous iteration, you added a placeholder environment variable with value "DYNVALDYNVALDYNVAL" to discover its actual value at runtime. The firmware has now run with this placeholder, and Penguin captured candidate values in env_cmp.txt by monitoring string comparisons.

## Your Task
Analyze env_cmp.txt results for variable "{variable_name}" and create a plan to either:
1. **Apply the discovered value** (if env_cmp.txt has candidates)
2. **Remove the placeholder** (if env_cmp.txt is empty - discovery failed)

⚠️ **CRITICAL**: Generate EXACTLY ONE option in your plan. No multiple options in discovery mode.

## Output Format
Generate a plan in JSON format following the standard schema with EXACTLY ONE option.

**If env_cmp.txt has candidate values:**
{{
  "id": "discovery_{variable_name}",
  "objectives": ["Apply discovered value for {variable_name}"],
  "options": [{{
    "option_id": "1",
    "description": "Set {variable_name} with discovered value",
    "problem": "Placeholder needs replacement with actual value",
    "solution": {{"action": "set_value", "path": "env.{variable_name}", "value": "<FIRST_CANDIDATE_FROM_ENV_CMP>"}},
    "priority": "critical",
    "impact": "Applies discovered value to environment variable",
    "metadata": {{"variable_name": "{variable_name}", "config_path": "env.{variable_name}"}}
  }}]
}}

**If env_cmp.txt is empty or has no relevant values:**
{{
  "id": "discovery_{variable_name}",
  "objectives": ["Remove failed discovery for {variable_name}"],
  "options": [{{
    "option_id": "1",
    "description": "Remove {variable_name} - discovery unsuccessful",
    "problem": "No candidate values discovered",
    "solution": {{"action": "remove_variable", "path": "env.{variable_name}", "value": null}},
    "priority": "high",
    "impact": "Removes placeholder that failed discovery",
    "metadata": {{"variable_name": "{variable_name}", "config_path": "env.{variable_name}"}}
  }}]
}}

Output ONLY valid JSON matching the schema."""

    def __init__(self, model: str = "llama3.3:latest", max_retries: int = 3, kb_path: Optional[Path] = None):
        """Initialize firmware-specific planner."""
        self.model = model
        self.plan_schema = FirmwareConfigPlan
        self.max_retries = max_retries
        self.kb = get_knowledge_base(kb_path)
    
    def plan(self, state: State) -> FirmwareConfigPlan:
        """Generate firmware configuration update plan."""
        context = self._build_context(state)
        user_prompt = self._build_prompt(state, context)
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                is_retry = attempt > 0
                response = self._call_llm(user_prompt, is_retry=is_retry, previous_error=last_error, state=state)
                plan = self._parse_plan(response)
                
                if attempt > 0:
                    print(f"[Planner] Successfully generated plan on retry attempt {attempt + 1}")
                
                if is_verbose():
                    verbose_print("=" * 70)
                    verbose_print("GENERATED PLAN (PARSED)", prefix="[PLANNER]")
                    verbose_print("=" * 70)
                    verbose_print(f"Plan ID: {plan.id}", prefix="[PLANNER]")
                    if hasattr(plan, 'model_dump'):
                        verbose_print(json.dumps(plan.model_dump(), indent=2))
                    else:
                        verbose_print(str(plan))
                    verbose_print("=" * 70)
                
                return plan
                
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                last_error = str(e)
                print(f"[Planner] Attempt {attempt + 1}/{self.max_retries} failed: {last_error}")
                
                if attempt == self.max_retries - 1:
                    print(f"[Planner] All {self.max_retries} attempts failed. Creating fallback plan.")
                    return self._create_fallback_plan(last_error, response if 'response' in locals() else "No response")
        
        return self._create_fallback_plan("Unknown error", "No response")
    
    def _parse_plan(self, response: str) -> FirmwareConfigPlan:
        """
        Parse LLM response into a firmware configuration plan.
        
        Overrides base parser to validate firmware-specific schema.
        
        Raises:
            json.JSONDecodeError: If response is not valid JSON
            ValueError: If JSON doesn't match expected schema
            KeyError: If required fields are missing
        """
        import json
        import uuid
        
        # First attempt: direct JSON parsing
        try:
            plan_data = json.loads(response)
        except json.JSONDecodeError as e:
            # Try to extract JSON from markdown code blocks
            if "```json" in response or "```" in response:
                try:
                    json_start = response.find("```json")
                    if json_start == -1:
                        json_start = response.find("```")
                    json_start = response.find("\n", json_start) + 1
                    json_end = response.find("```", json_start)
                    json_str = response[json_start:json_end].strip()
                    plan_data = json.loads(json_str)
                except (ValueError, json.JSONDecodeError) as extract_error:
                    raise json.JSONDecodeError(
                        f"Failed to parse JSON from response. Original error: {str(e)}, Extract error: {str(extract_error)}",
                        response, 0
                    )
            else:
                raise json.JSONDecodeError(f"Response is not valid JSON: {str(e)}", response, 0)
        
        # Validate required fields for firmware plans
        required_fields = ["objectives", "options"]
        missing_fields = [field for field in required_fields if field not in plan_data]
        if missing_fields:
            raise KeyError(f"Missing required fields: {', '.join(missing_fields)}")
        
        # Ensure we have a unique ID
        if "id" not in plan_data or not plan_data["id"]:
            plan_data["id"] = f"fw_plan_{uuid.uuid4().hex[:8]}"
        
        # Validate options structure
        if not isinstance(plan_data["options"], list):
            raise ValueError("'options' must be a list")
        
        for i, option in enumerate(plan_data["options"]):
            if not isinstance(option, dict):
                raise ValueError(f"Option {i} must be a dictionary")
            option_required = ["option_id", "description", "problem", "solution", "priority"]
            option_missing = [field for field in option_required if field not in option]
            if option_missing:
                raise KeyError(f"Option {i} missing required fields: {', '.join(option_missing)}")
            
            # Validate priority values
            valid_priorities = ["critical", "high", "medium", "low"]
            if option["priority"] not in valid_priorities:
                raise ValueError(f"Option {i} has invalid priority '{option['priority']}'. Must be one of: {', '.join(valid_priorities)}")
        
        # Create plan object using firmware schema
        try:
            plan = self.plan_schema(**plan_data)
            return plan
        except Exception as e:
            raise ValueError(f"Failed to instantiate firmware plan schema: {str(e)}")
    
    def _build_context(self, state: State) -> str:
        """
        Build contextual information from state, enriched with KB insights and previous execution context.
        
        Context building is MODE-DEPENDENT:
        - **Discovery Mode**: Only include env_cmp.txt and console.log (filtered context)
          Purpose: Focus LLM on discovered values, avoid distraction from other data
        
        - **Normal Mode**: Include everything (full context)
          - Previous config.yaml (converted to JSON)
          - All Penguin results (console, env_missing, pseudofiles_failures, etc.)
          - Previous action history
          - Knowledge Base insights
        
        Args:
            state: Current State with rag_context (dict), discovery_mode flag, etc.
            
        Returns:
            Formatted string with context sections for LLM prompt
        """
        context_parts = []
        
        # DISCOVERY MODE: Focus only on env_cmp.txt and console.log
        if state.discovery_mode:
            if is_verbose():
                verbose_print(f"[PLANNER] DISCOVERY MODE active for variable: {state.discovery_variable}", prefix="[CONTEXT]")
            
            context_parts.append(f"## 🔍 DISCOVERY MODE - Variable: {state.discovery_variable}")
            context_parts.append("Analyzing env_cmp.txt for candidate values and console output for errors.")
            context_parts.append("")
            
            # Extract only relevant sources using dict keys
            if "env_cmp.txt" in state.rag_context:
                context_parts.append("## env_cmp.txt (Discovered Candidates):")
                context_parts.append(state.rag_context["env_cmp.txt"])
                context_parts.append("")
            
            if "console.log" in state.rag_context:
                context_parts.append("## console.log (Error Context):")
                context_parts.append(state.rag_context["console.log"])
                context_parts.append("")
            
            if "env_cmp.txt" not in state.rag_context and "console.log" not in state.rag_context:
                context_parts.append("## Note: No env_cmp.txt or console.log found in context")
                if is_verbose():
                    verbose_print(f"[PLANNER] Warning: Available sources: {list(state.rag_context.keys())}", prefix="[CONTEXT]")
            
            return "\n".join(context_parts)
        
        # NORMAL MODE: Full context building
        # Add previous config.yaml from project if available
        if state.project_path:
            config_path = Path(state.project_path) / "config.yaml"
            if config_path.exists():
                try:
                    with open(config_path, 'r') as f:
                        config_content = f.read()
                    context_parts.append("## Previous Penguin Configuration (config.yaml):")
                    context_parts.append("This is the configuration used in the previous rehosting attempt.")
                    context_parts.append("```yaml")
                    context_parts.append(config_content)
                    context_parts.append("```")
                    context_parts.append("")  # Empty line for separation
                    
                    if is_verbose():
                        verbose_print(f"[PLANNER] Loaded config.yaml from: {config_path}", prefix="[CONTEXT]")
                except Exception as e:
                    context_parts.append(f"## Note: Could not read config.yaml: {str(e)}")
                    if is_verbose():
                        verbose_print(f"[PLANNER] Failed to load config.yaml: {e}", prefix="[CONTEXT]")
        
        if state.rag_context:
            context_parts.append("## Retrieved Context:")
            # Iterate through dict and format each source
            for source, content in state.rag_context.items():
                context_parts.append(f"\n### {source}:")
                context_parts.append(content)
        
        # Add previous execution context if available
        if hasattr(state, 'previous_actions') and state.previous_actions:
            context_parts.append("\n## Previous Execution History:")
            context_parts.append(f"Total previous actions: {len(state.previous_actions)}")
            
            # Group actions by iteration/option for better readability
            for i, action in enumerate(state.previous_actions[-10:], 1):  # Show last 10 actions
                context_parts.append(f"\nPrevious Action {i}:")
                context_parts.append(f"  Step ID: {action.step_id}")
                context_parts.append(f"  Tool: {action.tool}")
                context_parts.append(f"  Status: {action.status}")
                context_parts.append(f"  Summary: {action.summary}")
                if action.input:
                    context_parts.append(f"  Parameters: {action.input}")
        
        if hasattr(state, 'previous_engineer_summary') and state.previous_engineer_summary:
            context_parts.append("\n## Previous Engineer Summary:")
            if isinstance(state.previous_engineer_summary, list):
                for i, summary in enumerate(state.previous_engineer_summary[-3:], 1):  # Show last 3 summaries
                    context_parts.append(f"\nSummary {i}:")
                    if isinstance(summary, dict):
                        for key, value in summary.items():
                            context_parts.append(f"  {key}: {value}")
                    else:
                        context_parts.append(f"  {summary}")
            else:
                context_parts.append(f"  {state.previous_engineer_summary}")
        
        # Query Knowledge Base for strategic insights (if enabled)
        symptoms = self._extract_symptoms(state.rag_context)
        if symptoms and self.kb is not None:
            kb_insights = self.kb.query_for_planner(symptoms)
            
            if kb_insights:
                context_parts.append("\n## Knowledge Base Insights:")
                for insight in kb_insights:
                    context_parts.append(f"- Issue: {insight['title']}")
                    context_parts.append(f"  Severity: {insight['severity']}")
                    context_parts.append(f"  Priority: {insight.get('priority', 'medium')}")
                    context_parts.append(f"  Impact: {insight.get('impact', 'medium')}")
                    context_parts.append(f"  Description: {insight.get('description', '')}")
                    
                    # Add specific guidance from complete planner_view
                    if insight.get('requires_rerun'):
                        context_parts.append(f"  ⚠️  Requires iteration: {insight.get('next_steps', 'Re-run needed')}")
                    if insight.get('selection_criteria'):
                        context_parts.append(f"  Selection: {insight['selection_criteria']}")
                    context_parts.append("")
                
                if is_verbose():
                    verbose_print(f"[PLANNER] KB returned {len(kb_insights)} insights", prefix="[KB]")
        
        context = "\n".join(context_parts) if context_parts else "No additional context available."
        
        return context
    
    def _extract_symptoms(self, rag_context: Dict[str, str]) -> List[str]:
        """
        Extract symptoms from RAG context for Knowledge Base querying.
        
        Symptoms are high-level problem indicators that the KB can match against
        to provide relevant guidance (e.g., "env_missing.yaml shows unknown variable"
        triggers KB entry about discovery mode workflow).
        
        Args:
            rag_context: Dict with source names as keys (e.g., "console.log", "env_cmp.txt")
            
        Returns:
            List of symptom strings for KB matching
        """
        symptoms = []
        
        # Check for specific sources in the dict
        if "env_missing.yaml" in rag_context:
            symptoms.append("env_missing.yaml shows unknown variable")
        
        if "env_cmp.txt" in rag_context:
            symptoms.append("env_cmp.txt contains dynamic discovery candidate values")
        
        if "console.log" in rag_context:
            console_content = rag_context["console.log"].lower()
            if "no configuration" in console_content or "missing configuration" in console_content:
                symptoms.append("Console errors about missing configuration")
            
            if "/dev/" in console_content and ("not found" in console_content or "no such" in console_content):
                symptoms.append("/dev/* file not found")
        
        if "pseudofiles_failures.yaml" in rag_context:
            symptoms.append("pseudofiles_failures.yaml shows device failures")
        
        return symptoms
    
    def _build_prompt(self, state: State, context: str) -> str:
        """Construct the user prompt with goal, context, and constraints (no instructions)."""
        prompt_parts = [
            f"## Goal:\n{state.goal}",
            f"\n## Context:\n{context}",
        ]
        
        if state.budget:
            prompt_parts.append(f"\n## Constraints:\n{json.dumps(state.budget, indent=2)}")
        
        return "\n".join(prompt_parts)
    
    def _call_llm(self, user_prompt: str, is_retry: bool = False, previous_error: Optional[str] = None, state: Optional[State] = None) -> str:
        """Call Ollama LLM to generate the plan."""
        schema_str = json.dumps(self.EXPECTED_RESPONSE_SCHEMA, indent=2)
        
        if is_retry:
            system_prompt = self.RETRY_SYSTEM_PROMPT.format(schema=schema_str)
            retry_user_prompt = f"""Previous attempt failed with error: {previous_error}

{user_prompt}

REMEMBER: Output ONLY valid JSON matching the exact schema. No markdown, no explanations."""
            user_prompt = retry_user_prompt
        else:
            # Use discovery mode prompt if in discovery mode
            if state and state.discovery_mode:
                variable_name = state.discovery_variable or "unknown"
                system_prompt = self.DISCOVERY_MODE_PROMPT.format(variable_name=variable_name)
                
                if is_verbose():
                    verbose_print(f"[PLANNER] Using DISCOVERY MODE prompt for variable: {variable_name}", prefix="[LLM]")
            else:
                # Append schema at the END to highlight expected format
                system_prompt = f"""{self.SYSTEM_PROMPT}

## Expected JSON Output Format

{schema_str}"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        if is_verbose():
            verbose_print("=" * 70)
            verbose_print(f"CALLING LLM (Retry: {is_retry})", prefix="[PLANNER]")
            verbose_print("=" * 70)
            verbose_print(f"Model: {self.model}", prefix="[PLANNER]")
            verbose_print("\n--- SYSTEM PROMPT ---")
            verbose_print(system_prompt)
            verbose_print("\n--- USER PROMPT ---")
            verbose_print(user_prompt)
            verbose_print("=" * 70)
        
        response: ChatResponse = chat(
            model=self.model,
            messages=messages,
            format="json",
            options={
                "temperature": 0.3 if is_retry else 0.7,
                "num_predict": 2048,
            }
        )
        
        llm_response = response['message']['content']
        
        
        return llm_response
    
    def _create_fallback_plan(self, error: str, response: str) -> FirmwareConfigPlan:
        """
        Create a fallback firmware configuration plan when all parsing attempts fail.
        
        Args:
            error: The error message from the last attempt
            response: The raw LLM response
            
        Returns:
            A minimal fallback firmware plan object
        """
        import uuid
        
        fallback_data = {
            "id": f"fw_plan_{uuid.uuid4().hex[:8]}",
            "objectives": ["⚠️ Parse error - manual intervention needed"],
            "options": [
                {
                    "option_id": "1",
                    "description": f"Failed to parse LLM response after {self.max_retries} attempts",
                    "problem": f"LLM response parsing failed: {error}",
                    "solution": "Manual review and intervention required",
                    "priority": "critical",
                    "impact": "requires_manual_intervention"
                }
            ]
        }
        
        try:
            return self.plan_schema(**fallback_data)
        except Exception:
            # If even the fallback fails, return the dict itself
            return fallback_data
    
    def __call__(self, state: State) -> Dict[str, Any]:
        """LangGraph node interface - callable that updates state."""
        plan = self.plan(state)
        return {"plan": plan}

# Convenience function for workflow integration
def create_firmware_planner(model: str = "llama3.3:latest", kb_path: Optional[Path] = None) -> FirmwarePlannerAgent:
    """Create a firmware-specific planner instance."""
    return FirmwarePlannerAgent(model, kb_path=kb_path)

