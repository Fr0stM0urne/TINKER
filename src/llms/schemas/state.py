"""Global state schema for the multi-agent system."""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from .plan import Plan
from .critique import Critique
from .action_record import ActionRecord


class State(BaseModel):
    """Shared state across all agents in the orchestration graph."""
    
    goal: str = Field(description="The primary task or objective from the user")
    plan: Optional[Plan] = Field(
        default=None,
        description="Current active plan from the Planner"
    )
    critiques: List[Critique] = Field(
        default_factory=list,
        description="History of evaluations and feedback"
    )
    actions: List[ActionRecord] = Field(
        default_factory=list,
        description="Execution history from the Engineer"
    )
    rag_context: List[str] = Field(
        default_factory=list,
        description="Retrieved context from the RAG system"
    )
    budget: Dict[str, Any] = Field(
        default_factory=dict,
        description="Resource constraints (tokens, time, cost, etc.)"
    )
    done: bool = Field(
        default=False,
        description="Whether the task has been completed successfully"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "goal": "Rehost firmware for analysis",
                "plan": None,
                "critiques": [],
                "actions": [],
                "rag_context": [],
                "budget": {"max_iterations": 10, "token_limit": 100000},
                "done": False
            }
        }

