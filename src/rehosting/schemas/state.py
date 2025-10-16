"""State schema for the rehosting workflow."""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class State(BaseModel):
    """Shared state for rehosting agents."""
    
    goal: str = Field(description="The primary task or objective")
    plan: Optional[Any] = Field(default=None, description="Current plan from the Planner")
    rag_context: List[str] = Field(default_factory=list, description="Context from Penguin results")
    budget: Dict[str, Any] = Field(default_factory=dict, description="Resource constraints")
    done: bool = Field(default=False, description="Whether the task is complete")

