"""Action record schema for Engineer execution tracking."""

from pydantic import BaseModel, Field
from typing import Dict, Any


class ActionRecord(BaseModel):
    """Record of an executed action by the Engineer agent."""
    
    step_id: str = Field(description="ID of the plan step being executed")
    tool: str = Field(description="Name of the tool or function used")
    input: Dict[str, Any] = Field(description="Input parameters provided to the tool")
    output_uri: str = Field(description="Reference to the output (file path, ID, etc.)")
    summary: str = Field(description="Human-readable summary of what was done")
    status: str = Field(description="Execution status: success, partial, failed")

