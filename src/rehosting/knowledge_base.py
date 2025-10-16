"""
Knowledge base for firmware rehosting common issues and solutions.

This module provides access to documented solutions for common firmware
rehosting problems. Different agents query it for different purposes:
- Planner: Strategic information (issue severity, priority, patterns)
- Engineer: Tactical information (specific tool calls, parameters, examples)
"""

from typing import List, Dict, Any, Optional
from pathlib import Path


class KnowledgeBase:
    """
    Knowledge base containing common issues and their solutions.
    
    Can be queried by both Planner and Engineer agents for different perspectives.
    """
    
    # Example knowledge - in real implementation, load from files or vector DB
    COMMON_ISSUES = {
        "missing_env_var_unknown_value": {
            "title": "Missing Environment Variable - Unknown Value (Step 1: Dynamic Analysis)",
            "severity": "high",
            "symptoms": [
                "env_missing.yaml shows unknown variable",
                "Console errors about missing configuration",
                "No env_cmp.txt exists yet for this variable"
            ],
            "solutions": {
                "planner_view": {
                    "priority": "high",
                    "impact": "requires_iteration",
                    "description": "Use dynamic analysis with magic value to discover correct value. Requires re-running Penguin.",
                    "next_steps": "After re-run, check env_cmp.txt for candidate values",
                    "requires_rerun": True
                },
                "engineer_view": {
                    "tool": "yaml_editor",
                    "action": "update_config",
                    "examples": [
                        {
                            "params": {
                                "file": "config.yaml",
                                "path": "env.sxid",
                                "value": "DYNVALDYNVALDYNVAL",
                                "reason": "Magic value for dynamic detection - will be compared against in next run to find real value"
                            }
                        }
                    ],
                    "notes": [
                        "Set variable to magic value: DYNVALDYNVALDYNVAL",
                        "Re-run Penguin to collect env_cmp.txt",
                        "Check env_cmp.txt for candidate values",
                        "This is an iterative step - requires follow-up action"
                    ]
                }
            }
        },
        
        "missing_env_var_found_candidates": {
            "title": "Missing Environment Variable - Candidates Found (Step 2: Apply Value)",
            "severity": "high",
            "symptoms": [
                "env_cmp.txt contains candidate values",
                "Previous run used magic value DYNVALDYNVALDYNVAL",
                "Console shows comparison with magic value happened"
            ],
            "solutions": {
                "planner_view": {
                    "priority": "high",
                    "impact": "critical",
                    "description": "Candidate values found via dynamic analysis. Select and apply one.",
                    "selection_criteria": "Usually first non-empty candidate is correct",
                    "requires_rerun": True
                },
                "engineer_view": {
                    "tool": "yaml_editor",
                    "action": "update_config",
                    "examples": [
                        {
                            "params": {
                                "file": "config.yaml",
                                "path": "env.sxid",
                                "value": "0150_5MS-MDM-1",
                                "reason": "Candidate value from env_cmp.txt - replacing magic value with actual value"
                            }
                        }
                    ],
                    "notes": [
                        "Read env_cmp.txt from latest results directory",
                        "Pick first valid candidate (non-empty, non-garbage)",
                        "Replace magic value with selected candidate",
                        "Re-run to verify new errors appear (progress indicator)",
                        "Compare console.log differences to confirm progress"
                    ]
                }
            }
        }
    }
    
    def __init__(self, kb_path: Optional[Path] = None):
        """
        Initialize knowledge base.
        
        Args:
            kb_path: Path to external knowledge base file (optional)
        """
        self.kb_path = kb_path
        # In real implementation, load from file or vector DB
    
    def detect_case(self, results_data: Dict[str, Any]) -> Optional[str]:
        """
        Automatically detect which case applies based on Penguin results.
        
        Args:
            results_data: Dictionary containing Penguin results (env_missing, env_cmp, etc.)
            
        Returns:
            issue_id of the detected case, or None if no match
        """
        # Check for env_cmp.txt with candidates
        if results_data.get("env_cmp_txt") and results_data["env_cmp_txt"].strip():
            # We have candidate values - this is Step 2
            return "missing_env_var_found_candidates"
        
        # Check for missing env vars without candidates
        if results_data.get("env_missing_yaml"):
            # We have missing vars but no candidates yet - this is Step 1
            return "missing_env_var_unknown_value"
        
        return None
    
    def query_for_planner(self, symptoms: List[str]) -> List[Dict[str, Any]]:
        """
        Query KB from Planner's perspective: strategic information.
        
        Args:
            symptoms: List of observed symptoms/issues
            
        Returns:
            List of issues with priority, impact, descriptions
        """
        results = []
        
        for issue_id, issue_data in self.COMMON_ISSUES.items():
            # Check if symptoms match
            if self._symptoms_match(symptoms, issue_data["symptoms"]):
                planner_info = issue_data["solutions"]["planner_view"]
                results.append({
                    "issue": issue_data["title"],
                    "severity": issue_data["severity"],
                    "priority": planner_info.get("priority", "medium"),
                    "impact": planner_info.get("impact", "medium"),
                    "description": planner_info.get("description", ""),
                    "issue_id": issue_id
                })
        
        return results
    
    def query_for_engineer(self, objective: str, issue_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Query KB from Engineer's perspective: implementation details.
        
        Args:
            objective: High-level objective to implement
            issue_id: Known issue ID (if available)
            
        Returns:
            List of implementation examples with tools and parameters
        """
        results = []
        
        # If issue_id provided, get specific examples
        if issue_id and issue_id in self.COMMON_ISSUES:
            engineer_view = self.COMMON_ISSUES[issue_id]["solutions"]["engineer_view"]
            return engineer_view.get("examples", [])
        
        # Otherwise, search based on objective keywords
        for issue_id, issue_data in self.COMMON_ISSUES.items():
            if self._objective_matches(objective, issue_data):
                engineer_view = issue_data["solutions"]["engineer_view"]
                results.extend(engineer_view.get("examples", []))
        
        return results
    
    def _symptoms_match(self, observed: List[str], known: List[str]) -> bool:
        """Check if observed symptoms match known symptoms."""
        # Simple keyword matching (can be improved with embeddings)
        for obs in observed:
            for kn in known:
                if any(word in obs.lower() for word in kn.lower().split()):
                    return True
        return False
    
    def _objective_matches(self, objective: str, issue_data: Dict[str, Any]) -> bool:
        """Check if objective relates to this issue."""
        # Simple keyword matching
        obj_lower = objective.lower()
        
        # Check title
        if any(word in obj_lower for word in issue_data["title"].lower().split()):
            return True
        
        # Check symptoms
        for symptom in issue_data["symptoms"]:
            if any(word in obj_lower for word in symptom.lower().split()):
                return True
        
        return False
    
    def get_all_issues(self) -> List[str]:
        """Get list of all known issue IDs."""
        return list(self.COMMON_ISSUES.keys())
    
    def get_issue_details(self, issue_id: str) -> Optional[Dict[str, Any]]:
        """Get complete details for a specific issue."""
        return self.COMMON_ISSUES.get(issue_id)


# Global instance (can be configured per workflow)
_default_kb = None
_kb_disabled = False

def get_knowledge_base(kb_path: Optional[Path] = None) -> Optional[KnowledgeBase]:
    """
    Get or create the default knowledge base instance.
    
    Args:
        kb_path: Path to custom KB file, or None to use built-in KB
        
    Returns:
        KnowledgeBase instance if enabled, None if disabled
    """
    global _default_kb, _kb_disabled
    
    # If kb_path is explicitly False, disable KB
    if kb_path is False:
        _kb_disabled = True
        return None
    
    if _kb_disabled:
        return None
    
    if _default_kb is None:
        _default_kb = KnowledgeBase(kb_path)
    return _default_kb

