"""Critique schema for Evaluator feedback."""

from pydantic import BaseModel, Field
from typing import List, Dict, Any


class Critique(BaseModel):
    """Structured feedback from the Evaluator agent."""
    
    needs_revision: bool = Field(
        description="Whether the plan or result requires changes"
    )
    issues: List[str] = Field(
        default_factory=list,
        description="Identified problems or concerns"
    )
    patches: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Suggested modifications or improvements"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "needs_revision": True,
                "issues": [
                    "Step 2 lacks error handling",
                    "Missing validation for input parameters"
                ],
                "patches": [
                    {
                        "step_id": "2",
                        "add": "error_handler",
                        "reason": "Handle malformed binary files"
                    }
                ]
            }
        }

