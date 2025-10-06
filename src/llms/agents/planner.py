"""Planner agent for task decomposition."""

import json
import uuid
from typing import Dict, Any, List
from ollama import chat, ChatResponse
from ..schemas import Plan, State


class PlannerAgent:
    """
    Planner agent that decomposes user goals into structured, executable plans.
    
    Responsibilities:
    - Analyze the user goal and current state
    - Decompose tasks into ordered, actionable steps
    - Define clear acceptance criteria
    - Incorporate feedback from the Evaluator to refine plans
    """
    
    SYSTEM_PROMPT = """You are a planning agent in a multi-agent system. Your role is to decompose complex tasks into structured, executable plans.

Given a user goal and the current state, you must:
1. Identify high-level objectives needed to achieve the goal
2. Break down the task into clear, ordered steps
3. Specify which tools or actions each step requires
4. Define measurable acceptance criteria for success
5. Consider any feedback or constraints from previous iterations

Your output MUST be valid JSON matching this schema:
{
    "id": "unique_plan_id",
    "objectives": ["objective 1", "objective 2", ...],
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
    "revision_notes": ["incorporated feedback from evaluator", ...]
}

Think carefully about dependencies between steps and ensure the plan is both comprehensive and achievable."""

    def __init__(self, model: str = "llama3.3:latest"):
        """
        Initialize the Planner agent.
        
        Args:
            model: Ollama model name to use for planning
        """
        self.model = model
        
    def plan(self, state: State) -> Plan:
        """
        Generate or refine a plan based on the current state.
        
        Args:
            state: Current system state including goal, critiques, and context
            
        Returns:
            A structured Plan object
        """
        # Build context from state
        context = self._build_context(state)
        
        # Construct the planning prompt
        user_prompt = self._build_prompt(state, context)
        
        # Call LLM to generate plan
        response = self._call_llm(user_prompt)
        
        # Parse and validate the plan
        plan = self._parse_plan(response)
        
        return plan
    
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
        
        return "\n".join(context_parts) if context_parts else "No additional context available."
    
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
            prompt_parts.append("Create a comprehensive plan to achieve the user goal. Output the plan in JSON format.")
        
        return "\n".join(prompt_parts)
    
    def _call_llm(self, user_prompt: str) -> str:
        """Call Ollama LLM to generate the plan."""
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]
        
        response: ChatResponse = chat(
            model=self.model,
            messages=messages,
            format="json",  # Request JSON output
            options={
                "temperature": 0.7,
                "num_predict": 2048,
            }
        )
        
        return response['message']['content']
    
    def _parse_plan(self, response: str) -> Plan:
        """Parse LLM response into a Plan object."""
        try:
            # Parse JSON response
            plan_data = json.loads(response)
            
            # Ensure we have a unique ID
            if "id" not in plan_data or not plan_data["id"]:
                plan_data["id"] = f"plan_{uuid.uuid4().hex[:8]}"
            
            # Validate and create Plan object
            plan = Plan(**plan_data)
            return plan
            
        except json.JSONDecodeError as e:
            # Fallback: try to extract JSON from markdown code blocks
            if "```json" in response:
                try:
                    json_start = response.index("```json") + 7
                    json_end = response.index("```", json_start)
                    json_str = response[json_start:json_end].strip()
                    plan_data = json.loads(json_str)
                    
                    if "id" not in plan_data or not plan_data["id"]:
                        plan_data["id"] = f"plan_{uuid.uuid4().hex[:8]}"
                    
                    return Plan(**plan_data)
                except (ValueError, json.JSONDecodeError):
                    pass
            
            # Last resort: create a minimal plan
            return Plan(
                id=f"plan_{uuid.uuid4().hex[:8]}",
                objectives=["Parse error - manual intervention needed"],
                steps=[
                    {
                        "step_id": "1",
                        "description": f"Failed to parse LLM response: {str(e)}",
                        "action": "manual_review",
                        "tool": "human",
                        "params": {"raw_response": response[:500]}
                    }
                ],
                acceptance_criteria={"manual_review": True},
                revision_notes=[f"Parse error: {str(e)}"]
            )
    
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

