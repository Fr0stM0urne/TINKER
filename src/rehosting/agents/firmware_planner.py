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
        "objectives": [
            "Fix missing environment variables",
            "Model failed peripheral devices"
        ],
        "options": [
            {
                "option_id": "1",
                "description": "<description of the option>",
                "problem": "<problem identified from the rehosting results>",
                "solution": "<solution to the problem>",
                "priority": "<priority level>",
                "impact": "<impact level>"
            },
            {
                "option_id": "2",
                "description": "<description of the option>",
                "problem": "<problem identified from the rehosting results>",
                "solution": "<solution to the problem>",
                "priority": "<priority level>",
                "impact": "<impact level>"
            }
        ]
    }
    
    # Extended system prompt with firmware-specific knowledge
    SYSTEM_PROMPT = """You are a firmware rehosting planning agent specialized in Penguin configuration optimization.

Your role is to analyze firmware rehosting results and generate configuration update plans to improve execution success.

## Penguin Configuration Structure (YAML)

The Penguin config.yaml file contains several key sections for firmware rehosting:

### 1. **core**: General rehosting parameters
   - `fs`: Path to filesystem archive (e.g., `./base/fs.tar.gz`)
   - `plugin_path`: Path to Python plugins directory
   - `root_shell`: Enable/disable root shell access
   - `strace`: Enable/disable system call tracing
   - `ltrace`: Enable/disable library call tracing
   - `force_www`: Force web server detection
   - `show_output`: Show execution output
   - `immutable`: Make filesystem immutable
   - `network`: Enable/disable network emulation
   - `version`: Penguin configuration version
   - `auto_patching`: Enable automatic patching
   - `guest_cmd`: Enable guest command execution
   - `mem`: Memory allocation (e.g., `2G`)
   - `kernel_quiet`: Suppress kernel messages

### 2. **patches**: Penguin's built-in patches (DO NOT MODIFY)
   - These are predefined patches that don't require updates during rehosting
   - Examples: `static_patches/base.yaml`, `static_patches/manual.yaml`
   - Includes patches for: netdevs, pseudofiles, lib_inject, static files, shims, nvram
   - **Important**: These patches are automatically applied and should not be modified

### 3. **env**: Environment variables (MAIN TARGET FOR UPDATES)
   - Contains environment variables that the firmware expects
   - May need patching with expected values during rehosting
   - Example: `sxid: DYNVALDYNVALDYNVAL` (placeholder for dynamic discovery)
   - Can include nested structures like `target.memory_regions[0].env_vars`   
   - **Important**: If you see candidates in `env_cmp.txt`, this means dynamic analysis found candidate values for environment variables. This is at the HIGHEST priority. -
   - For patching environment variables, you should INCLUDE the value to update in the `solution` field. This value will be used by the engineer to update the environment variable.
   
   
### 4. **pseudofiles**: Model missing files/devices (MAIN TARGET FOR UPDATES)
   - Dictionary structure where filepath is the key
   - Models files the firmware expects but are missing
   - Examples: `/dev/dsa`, `/proc/cpuinfo`, `/sys/class/net/eth0`
   - Can include device-specific configurations (e.g., MTD device names)
   - **Structure**: `pseudofiles: { "/dev/dsa": { "ioctl": { "*": { "model": "return_const", "val": 0 } } } }`

### 5. **Other sections** (less commonly modified):
   - `nvram`: NVRAM configuration
   - `netdevs`: Network device configurations
   - `blocked_signals`: Signals to block
   - `lib_inject`: Library injection settings
   - `static_files`: Static file configurations
   - `plugins`: Plugin configurations

## Common Issues and Solutions

### Missing Environment Variables
- **Issue**: `env_missing.yaml` shows missing environment variables
- **Solution**: Add variables to `env` section with appropriate values
- **Priority**: HIGH - especially if `env_cmp.txt` contains candidate values

### Missing Device Files
- **Issue**: `pseudofiles_failures.yaml` shows unmodeled devices
- **Solution**: Add device models to `pseudofiles` section
- **Priority**: HIGH - critical for device-dependent firmware

### Network Configuration Issues
- **Issue**: Network binding failures or missing network interfaces
- **Solution**: Update `netdevs` section or add network-related pseudofiles
- **Priority**: MEDIUM - depends on firmware's network requirements

### Execution Crashes
- **Issue**: Console shows segfaults, crashes, or kernel panics
- **Solution**: 
  * Check `core` section parameters (memory, patches)
  * Add missing pseudofiles for critical devices
  * Verify environment variables are properly set
- **Priority**: CRITICAL - prevents firmware from running

## Your Task

Given rehosting results, create a plan with:
1. Clear objectives (what needs to be fixed)
2. List of problems and their solutions for prioritization
3. Each option should include:
   - option_id: Sequential identifier
   - description: Brief summary of what needs to be done
   - problem: Specific problem identified from the rehosting results
   - solution: High-level solution approach
   - priority: critical/high/medium/low
   - impact: Expected impact level

Focus on identifying the root causes of failures and suggesting appropriate solutions without specifying implementation details.

## Option Prioritization

Assign priority levels to help evaluator/engineer prioritize:
- **critical**: Must-fix issues (crashes, missing core dependencies, kernel panics)
- **high**: Important fixes (missing env vars with candidates, failed peripherals)
- **medium**: Nice-to-have improvements (network config, optional peripherals)
- **low**: Optimization or minor enhancements

**IMPORTANT**: If we see candidates in `env_cmp.txt`, this means dynamic analysis found candidate values for environment variables. This is at the HIGHEST priority. Include the value to update in the `solution` field.

Your output MUST be valid JSON matching the expected schema provided.

Focus on generating actionable configuration options with clear priorities."""

    RETRY_SYSTEM_PROMPT = """CRITICAL: Your previous response did NOT follow the required JSON schema format for firmware configuration plans.

You MUST output ONLY valid JSON that EXACTLY matches this schema:
{schema}

REQUIREMENTS FOR FIRMWARE CONFIGURATION PLANS:
- Output ONLY the JSON object, no explanations or markdown
- Required fields: id, objectives, options
- Each option MUST have: option_id, description, problem, solution, priority, impact
- priority values: critical, high, medium, low
- Do NOT wrap the JSON in markdown code blocks
- Do NOT add any text before or after the JSON

Generate the firmware configuration plan again, following the schema EXACTLY."""

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
                response = self._call_llm(user_prompt, is_retry=is_retry, previous_error=last_error)
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
        """Build contextual information from state, enriched with KB insights and previous execution context."""
        context_parts = []
        
        if state.rag_context:
            context_parts.append("## Retrieved Context:")
            context_parts.extend(state.rag_context)
        
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
        
        if is_verbose():
            verbose_print("=" * 70)
            verbose_print("CONTEXT BUILT FOR LLM (with KB + Previous Execution)", prefix="[PLANNER]")
            verbose_print("=" * 70)
            verbose_print(f"\n{context}\n")
            verbose_print("=" * 70)
        
        return context
    
    def _extract_symptoms(self, rag_context: List[str]) -> List[str]:
        """Extract symptoms from RAG context for KB querying."""
        symptoms = []
        
        for ctx in rag_context:
            ctx_lower = ctx.lower()
            
            # Look for common symptom patterns
            if "env_missing" in ctx_lower or "environment variable" in ctx_lower:
                symptoms.append("env_missing.yaml shows unknown variable")
            
            if "env_cmp" in ctx_lower:
                symptoms.append("env_cmp.txt contains candidate values")
            
            if "no configuration" in ctx_lower or "missing configuration" in ctx_lower:
                symptoms.append("Console errors about missing configuration")
            
            if "/dev/" in ctx_lower and ("not found" in ctx_lower or "no such" in ctx_lower):
                symptoms.append("/dev/* file not found")
            
            if "pseudofiles_failures" in ctx_lower:
                symptoms.append("pseudofiles_failures.yaml shows device failures")
        
        return symptoms
    
    def _build_prompt(self, state: State, context: str) -> str:
        """Construct the full planning prompt."""
        prompt_parts = [
            f"## User Goal:\n{state.goal}",
            f"\n## Context:\n{context}",
        ]
        
        if state.budget:
            prompt_parts.append(f"\n## Constraints:\n{json.dumps(state.budget, indent=2)}")
        
        prompt_parts.append("\n## Task:")
        prompt_parts.append("Create a comprehensive plan to achieve the user goal. Output the plan in JSON format following the pre-defined schema by system.")
        
        return "\n".join(prompt_parts)
    
    def _call_llm(self, user_prompt: str, is_retry: bool = False, previous_error: Optional[str] = None) -> str:
        """Call Ollama LLM to generate the plan."""
        if is_retry:
            schema_str = json.dumps(self.EXPECTED_RESPONSE_SCHEMA, indent=2)
            system_prompt = self.RETRY_SYSTEM_PROMPT.format(schema=schema_str)
            retry_user_prompt = f"""Previous attempt failed with error: {previous_error}

{user_prompt}

REMEMBER: Output ONLY valid JSON matching the exact schema. No markdown, no explanations."""
            user_prompt = retry_user_prompt
        else:
            schema_str = json.dumps(self.EXPECTED_RESPONSE_SCHEMA, indent=2)
            system_prompt = f"""{self.SYSTEM_PROMPT}

Expected JSON Schema:
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
        
        if is_verbose():
            verbose_print("=" * 70)
            verbose_print("LLM RESPONSE RECEIVED", prefix="[PLANNER]")
            verbose_print("=" * 70)
            verbose_print(llm_response)
            verbose_print("=" * 70)
        
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

