"""Planner agent for task decomposition."""

import json
import uuid
from typing import Dict, Any, List, Optional, Type
from ollama import chat, ChatResponse
from ..schemas import Plan, State
from src.settings import is_verbose, verbose_print


class PlannerAgent:
    """
    Planner agent that decomposes user goals into structured, executable plans.
    
    Responsibilities:
    - Analyze the user goal and current state
    - Decompose tasks into ordered, actionable steps
    - Define clear acceptance criteria
    - Incorporate feedback from the Evaluator to refine plans
    """
    
    EXPECTED_RESPONSE_SCHEMA = {
        "id": "unique_plan_id",
        "objectives": ["objective 1", "objective 2", "..."],
        "steps": [
            {
                "step_id": "1",
                "description": "what to do",
                "action": "action_name",
                "tool": "tool_name",
                "params": {"key": "value"}
            }
        ],
        "acceptance_criteria": {
            "required_outputs": ["output1", "output2"],
            "quality_threshold": 0.8,
            "constraints": {}
        },
        "revision_notes": ["incorporated feedback from evaluator", "..."]
    }
    
    SYSTEM_PROMPT = """You are a planning agent in a multi-agent system. Your role is to decompose complex tasks into structured, executable plans.

Given a user goal and the current state, you must:
1. Identify high-level objectives needed to achieve the goal
2. Break down the task into clear, ordered steps
3. Specify which tools or actions each step requires
4. Define measurable acceptance criteria for success
5. Consider any feedback or constraints from previous iterations

Your output MUST be valid JSON matching the expected schema provided.

Think carefully about dependencies between steps and ensure the plan is both comprehensive and achievable."""

    RETRY_SYSTEM_PROMPT = """CRITICAL: Your previous response did NOT follow the required JSON schema format.

You MUST output ONLY valid JSON that EXACTLY matches this schema:
{schema}

REQUIREMENTS:
- Output ONLY the JSON object, no explanations or markdown
- All required fields must be present: id, objectives, steps, acceptance_criteria, revision_notes
- Each step must have: step_id, description, action, tool, params
- Do NOT wrap the JSON in markdown code blocks
- Do NOT add any text before or after the JSON

Generate the plan again, following the schema EXACTLY."""

    def __init__(self, model: str = "llama3.3:latest", plan_schema: Optional[Type] = None, max_retries: int = 3):
        """
        Initialize the Planner agent.

        Args:
            model: Ollama model name to use for planning
            plan_schema: Custom plan schema class to use for parsing (defaults to Plan)
            max_retries: Maximum number of retry attempts for malformed responses
        """
        self.model = model
        self.plan_schema = plan_schema or Plan
        self.max_retries = max_retries
        
    def plan(self, state: State) -> Any:
        """
        Generate or refine a plan based on the current state.

        Args:
            state: Current system state including goal, critiques, and context

        Returns:
            A structured plan object using the custom schema
        """
        # Build context from state
        context = self._build_context(state)
        
        # Construct the planning prompt
        user_prompt = self._build_prompt(state, context)
        
        # Attempt to get valid plan with retries
        last_error = None
        for attempt in range(self.max_retries):
            try:
                # Call LLM to generate plan
                is_retry = attempt > 0
                response = self._call_llm(user_prompt, is_retry=is_retry, previous_error=last_error)
                
                # Parse and validate the plan
                plan = self._parse_plan(response)
                
                # Success - return the plan
                if attempt > 0:
                    print(f"[Planner] Successfully generated plan on retry attempt {attempt + 1}")
                
                # Verbose output for generated plan
                if is_verbose():
                    verbose_print("=" * 70)
                    verbose_print("GENERATED PLAN (PARSED)", prefix="[PLANNER]")
                    verbose_print("=" * 70)
                    verbose_print(f"Plan ID: {getattr(plan, 'id', 'N/A')}", prefix="[PLANNER]")
                    verbose_print(f"Plan Type: {type(plan).__name__}", prefix="[PLANNER]")
                    verbose_print("\n--- PLAN DETAILS ---")
                    if hasattr(plan, 'model_dump'):
                        # Pydantic v2
                        verbose_print(json.dumps(plan.model_dump(), indent=2))
                    elif hasattr(plan, 'dict'):
                        # Pydantic v1
                        verbose_print(json.dumps(plan.dict(), indent=2))
                    else:
                        # Fallback to string representation
                        verbose_print(str(plan))
                    verbose_print("=" * 70)
                
                return plan
                
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                last_error = str(e)
                print(f"[Planner] Attempt {attempt + 1}/{self.max_retries} failed: {last_error}")
                
                if attempt == self.max_retries - 1:
                    # Final attempt failed - return fallback plan
                    print(f"[Planner] All {self.max_retries} attempts failed. Creating fallback plan.")
                    return self._create_fallback_plan(last_error, response if 'response' in locals() else "No response")
        
        # This shouldn't be reached, but just in case
        return self._create_fallback_plan("Unknown error", "No response")
    
    def _build_context(self, state: State) -> str:
        """Build contextual information from state."""
        context_parts = []
        
        if state.rag_context:
            context_parts.append("## Retrieved Context:")
            context_parts.extend(state.rag_context)
        
        if state.critiques:
            context_parts.append("\n## Previous Feedback:")
            for i, critique in enumerate(state.critiques, 1):
                context_parts.append(f"Critique {i}:")
                context_parts.append(f"  Issues: {', '.join(critique.issues)}")
                if critique.patches:
                    context_parts.append(f"  Suggested patches: {len(critique.patches)}")
        
        if state.actions:
            context_parts.append(f"\n## Execution History: {len(state.actions)} actions completed")
        
        context = "\n".join(context_parts) if context_parts else "No additional context available."
        
        if is_verbose():
            verbose_print("=" * 70)
            verbose_print("CONTEXT BUILT FOR LLM", prefix="[PLANNER]")
            verbose_print("=" * 70)
            verbose_print(f"\n{context}\n")
            verbose_print("=" * 70)
        
        return context
    
    def _build_prompt(self, state: State, context: str) -> str:
        """Construct the full planning prompt."""
        prompt_parts = [
            f"## User Goal:\n{state.goal}",
            f"\n## Context:\n{context}",
        ]
        
        if state.budget:
            prompt_parts.append(f"\n## Constraints:\n{json.dumps(state.budget, indent=2)}")
        
        if state.plan:
            prompt_parts.append(f"\n## Current Plan (needs refinement):")
            prompt_parts.append(f"ID: {state.plan.id}")
            prompt_parts.append(f"Objectives: {state.plan.objectives}")
            prompt_parts.append(f"Steps: {len(state.plan.steps)}")
            if state.plan.revision_notes:
                prompt_parts.append(f"Previous revisions: {state.plan.revision_notes}")
        
        prompt_parts.append("\n## Task:")
        if state.plan:
            prompt_parts.append("Refine the current plan based on the feedback above. Output the complete revised plan in JSON format.")
        else:
            prompt_parts.append("Create a comprehensive plan to achieve the user goal. Output the plan in JSON format following the pre-defined schema by system.")
        
        return "\n".join(prompt_parts)
    
    def _call_llm(self, user_prompt: str, is_retry: bool = False, previous_error: Optional[str] = None) -> str:
        """
        Call Ollama LLM to generate the plan.
        
        Args:
            user_prompt: The user's planning request
            is_retry: Whether this is a retry attempt
            previous_error: Error message from previous attempt (if retry)
            
        Returns:
            LLM response string
        """
        # Use stricter system prompt on retry
        if is_retry:
            schema_str = json.dumps(self.EXPECTED_RESPONSE_SCHEMA, indent=2)
            system_prompt = self.RETRY_SYSTEM_PROMPT.format(schema=schema_str)
            
            # Add error context to user prompt
            retry_user_prompt = f"""Previous attempt failed with error: {previous_error}

{user_prompt}

REMEMBER: Output ONLY valid JSON matching the exact schema. No markdown, no explanations."""
            user_prompt = retry_user_prompt
        else:
            # Include schema in initial system prompt
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
            verbose_print(f"Temperature: {0.3 if is_retry else 0.7}", prefix="[PLANNER]")
            verbose_print("\n--- SYSTEM PROMPT ---")
            verbose_print(system_prompt)
            verbose_print("\n--- USER PROMPT ---")
            verbose_print(user_prompt)
            verbose_print("=" * 70)
        
        response: ChatResponse = chat(
            model=self.model,
            messages=messages,
            format="json",  # Request JSON output
            options={
                "temperature": 0.3 if is_retry else 0.7,  # Lower temperature on retry for more deterministic output
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
    
    def _parse_plan(self, response: str) -> Any:
        """
        Parse LLM response into a plan object using the configured schema.
        
        Raises:
            json.JSONDecodeError: If response is not valid JSON
            ValueError: If JSON doesn't match expected schema
            KeyError: If required fields are missing
        """
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
        
        # Validate required fields
        required_fields = ["objectives", "steps"]
        missing_fields = [field for field in required_fields if field not in plan_data]
        if missing_fields:
            raise KeyError(f"Missing required fields: {', '.join(missing_fields)}")
        
        # Ensure we have a unique ID
        if "id" not in plan_data or not plan_data["id"]:
            plan_data["id"] = f"plan_{uuid.uuid4().hex[:8]}"
        
        # Validate steps structure
        if not isinstance(plan_data["steps"], list):
            raise ValueError("'steps' must be a list")
        
        for i, step in enumerate(plan_data["steps"]):
            if not isinstance(step, dict):
                raise ValueError(f"Step {i} must be a dictionary")
            step_required = ["step_id", "description", "action"]
            step_missing = [field for field in step_required if field not in step]
            if step_missing:
                raise KeyError(f"Step {i} missing required fields: {', '.join(step_missing)}")
        
        # Create plan object using custom schema
        try:
            plan = self.plan_schema(**plan_data)
            return plan
        except Exception as e:
            raise ValueError(f"Failed to instantiate plan schema: {str(e)}")
    
    def _create_fallback_plan(self, error: str, response: str) -> Any:
        """
        Create a fallback plan when all parsing attempts fail.
        
        Args:
            error: The error message from the last attempt
            response: The raw LLM response
            
        Returns:
            A minimal fallback plan object
        """
        fallback_data = {
            "id": f"plan_{uuid.uuid4().hex[:8]}",
            "objectives": ["⚠️ Parse error - manual intervention needed"],
            "steps": [
                {
                    "step_id": "1",
                    "description": f"Failed to parse LLM response after {self.max_retries} attempts: {error}",
                    "action": "manual_review",
                    "tool": "human",
                    "params": {"raw_response": response[:500], "error": error}
                }
            ],
            "acceptance_criteria": {"manual_review": True},
            "revision_notes": [f"Parse error after {self.max_retries} attempts: {error}"]
        }
        
        try:
            return self.plan_schema(**fallback_data)
        except Exception:
            # If even the fallback fails, return the dict itself
            return fallback_data
    
    def __call__(self, state: State) -> Dict[str, Any]:
        """
        LangGraph node interface - callable that updates state.
        
        Args:
            state: Current state
            
        Returns:
            State updates to merge
        """
        plan = self.plan(state)
        return {"plan": plan}

