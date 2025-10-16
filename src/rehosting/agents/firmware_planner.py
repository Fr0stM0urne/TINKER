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
    - Configuration sections: target, patches, hyperfiles, network
    """
    
    # Override schema for firmware configuration plans
    EXPECTED_RESPONSE_SCHEMA = {
        "id": "fw_config_plan_001",
        "objectives": [
            "Fix missing environment variables",
            "Model failed peripheral devices"
        ],
        "options": [
            {
                "option_id": "1",
                "description": "Add missing PATH environment variable",
                "action": "update_config",
                "tool": "yaml_editor",
                "params": {
                    "file": "config.yaml",
                    "path": "hyperfiles./proc/self/environ",
                    "value": "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
                    "reason": "env_missing.yaml indicates PATH is required"
                },
                "priority": "high",
                "impact": "critical"
            }
        ]
    }
    
    # Extended system prompt with firmware-specific knowledge
    SYSTEM_PROMPT = """You are a firmware rehosting planning agent specialized in Penguin configuration optimization.

Your role is to analyze firmware rehosting results and generate configuration update plans to improve execution success.

## Penguin Configuration Structure (YAML)

1. **target**: Architecture and entry point settings
   - arch: ARM, MIPS, x86, etc.
   - entry_point: Firmware entry address
   - memory_regions: Memory mapping

2. **patches**: Code modifications
   - root_shell: Enable shell access
   - auto_explore: Automatic exploration
   - lib_inject: Library injection
   - static.shims.*: Static shimming

3. **hyperfiles**: File system mocking
   - Model files the firmware expects
   - Provide missing /proc, /sys entries

4. **network**: Network configuration
   - Interfaces, IP addresses
   - Port bindings

## Common Issues and Solutions

### Missing Environment Variables
- Issue: env_missing.yaml shows missing vars
- Solution: Add to hyperfiles or patches to inject

### Peripheral Failures  
- Issue: pseudofiles_failures.yaml shows unmodeled devices
- Solution: Add hyperfile models for the devices

### Network Binding Failures
- Issue: netbinds.csv shows failed bindings
- Solution: Update network config, add port mappings

### Execution Crashes
- Issue: Console shows segfaults, crashes
- Solution: 
  * Check entry point correctness
  * Add memory region mappings
  * Enable relevant patches (root_shell, lib_inject)

## Your Task

Given rehosting results, create a plan with:
1. Clear objectives (what needs to be fixed)
2. List of configuration update options for prioritization
3. Specific YAML paths and values to modify
4. Each option should include:
   - option_id: Sequential identifier
   - description: What this option does
   - action: Type of action (update_config, add_patch, create_hyperfile)
   - tool: Tool to use (yaml_editor, patch_manager, hyperfile_builder)
   - params: Specific parameters including file, path, value, reason
   - priority: critical/high/medium/low
   - impact: Expected impact level

## Option Prioritization

Assign priority levels to help evaluator/engineer prioritize:
- **critical**: Must-fix issues (crashes, missing core dependencies)
- **high**: Important fixes (missing env vars, failed peripherals)
- **medium**: Nice-to-have improvements (network config, optional peripherals)
- **low**: Optimization or minor enhancements

Your output MUST be valid JSON matching the expected schema provided.

Focus on generating actionable configuration options with clear priorities."""

    RETRY_SYSTEM_PROMPT = """CRITICAL: Your previous response did NOT follow the required JSON schema format for firmware configuration plans.

You MUST output ONLY valid JSON that EXACTLY matches this schema:
{schema}

REQUIREMENTS FOR FIRMWARE CONFIGURATION PLANS:
- Output ONLY the JSON object, no explanations or markdown
- Required fields: id, objectives, options
- Each option MUST have: option_id, description, action, tool, params, priority, impact
- params MUST include: file, path, value, reason
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
            option_required = ["option_id", "description", "action", "tool", "params", "priority"]
            option_missing = [field for field in option_required if field not in option]
            if option_missing:
                raise KeyError(f"Option {i} missing required fields: {', '.join(option_missing)}")
            
            # Validate params structure
            if not isinstance(option["params"], dict):
                raise ValueError(f"Option {i} 'params' must be a dictionary")
            
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
        """Build contextual information from state, enriched with KB insights."""
        context_parts = []
        
        if state.rag_context:
            context_parts.append("## Retrieved Context:")
            context_parts.extend(state.rag_context)
        
        # Query Knowledge Base for strategic insights (if enabled)
        symptoms = self._extract_symptoms(state.rag_context)
        if symptoms and self.kb is not None:
            kb_insights = self.kb.query_for_planner(symptoms)
            
            if kb_insights:
                context_parts.append("\n## Knowledge Base Insights:")
                for insight in kb_insights:
                    context_parts.append(f"- Issue: {insight['issue']}")
                    context_parts.append(f"  Severity: {insight['severity']}")
                    context_parts.append(f"  Priority: {insight['priority']}")
                    context_parts.append(f"  Impact: {insight['impact']}")
                    context_parts.append(f"  Description: {insight['description']}")
                    
                    # Add specific guidance from KB
                    issue_details = self.kb.get_issue_details(insight['issue_id'])
                    if issue_details:
                        planner_view = issue_details['solutions']['planner_view']
                        if planner_view.get('requires_rerun'):
                            context_parts.append(f"  ⚠️  Requires iteration: {planner_view.get('next_steps', 'Re-run needed')}")
                        if planner_view.get('selection_criteria'):
                            context_parts.append(f"  Selection: {planner_view['selection_criteria']}")
                    context_parts.append("")
                
                if is_verbose():
                    verbose_print(f"[PLANNER] KB returned {len(kb_insights)} insights", prefix="[KB]")
        
        context = "\n".join(context_parts) if context_parts else "No additional context available."
        
        if is_verbose():
            verbose_print("=" * 70)
            verbose_print("CONTEXT BUILT FOR LLM (with KB)", prefix="[PLANNER]")
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
                    "description": f"Failed to parse LLM response after {self.max_retries} attempts: {error}",
                    "action": "manual_review",
                    "tool": "human",
                    "params": {
                        "raw_response": response[:500],
                        "error": error,
                        "file": "config.yaml",
                        "path": "manual_review_required",
                        "value": "see_error_details",
                        "reason": "LLM response parsing failed"
                    },
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

