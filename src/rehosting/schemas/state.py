"""State schema for the rehosting workflow."""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class State(BaseModel):
    """Shared state for rehosting agents."""
    
    goal: str = Field(description="The primary task or objective")
    plan: Optional[Any] = Field(default=None, description="Current plan from the Planner")
    rag_context: Dict[str, str] = Field(default_factory=dict, description="Context from Penguin results (key=source, value=content)")
    budget: Dict[str, Any] = Field(default_factory=dict, description="Resource constraints")
    done: bool = Field(default=False, description="Whether the task is complete")
    
    # Optional fields for previous execution context (added dynamically)
    previous_actions: Optional[List[Any]] = Field(default=None, description="Previous execution actions")
    previous_engineer_summary: Optional[List[Any]] = Field(default=None, description="Previous engineer summaries")
    project_path: Optional[str] = Field(default=None, description="Path to the Penguin project")
    
    # Discovery mode tracking
    discovery_mode: bool = Field(default=False, description="Whether in discovery mode for environment variable")
    discovery_variable: Optional[str] = Field(default=None, description="Name of variable being discovered")

