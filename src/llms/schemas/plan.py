"""Plan schema for structured task decomposition."""

from pydantic import BaseModel, Field
from typing import List, Dict, Any


class Plan(BaseModel):
    """Structured plan created by the Planner agent."""
    
    id: str = Field(description="Unique identifier for this plan")
    objectives: List[str] = Field(description="High-level objectives to achieve")
    steps: List[Dict[str, Any]] = Field(
        description="Ordered list of executable steps with tool/action specifications"
    )
    acceptance_criteria: Dict[str, Any] = Field(
        description="Conditions that must be met for successful completion"
    )
    revision_notes: List[str] = Field(
        default_factory=list,
        description="History of revisions and feedback incorporated"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "plan_001",
                "objectives": ["Analyze firmware binary", "Identify entry points"],
                "steps": [
                    {
                        "step_id": "1",
                        "action": "load_binary",
                        "tool": "binary_loader",
                        "params": {"path": "/path/to/firmware.bin"}
                    }
                ],
                "acceptance_criteria": {
                    "required_outputs": ["entry_point", "architecture"],
                    "quality_threshold": 0.8
                },
                "revision_notes": []
            }
        }

