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
                    "requires_rerun": True,
                    "metadata_example": {
                        "variable_name": "sxid",
                        "config_path": "env.sxid"
                    }
                },
                "engineer_view": {
                    "tool": "add_environment_variable_placeholder",
                    "action": "add_environment_variable_placeholder",
                    "examples": [
                        {
                            "params": {
                                "name": "sxid",
                                "path": "env.sxid",
                                "reason": "Missing environment variable detected in logs - using magic value for dynamic discovery"
                            }
                        }
                    ],
                    "notes": [
                        "Use add_environment_variable_placeholder to set magic value: DYNVALDYNVALDYNVAL",
                        "Re-run Penguin to collect env_cmp.txt",
                        "Check env_cmp.txt for candidate values",
                        "This is an iterative step - requires follow-up rehosting attempt to find the actual value from the results",
                        "Extract variable name from option metadata if available"
                    ]
                }
            }
        }, 
        "missing_env_var_found_candidates": {
            "title": "Missing Environment Variable - Candidates Found (Step 2: Apply Value After Dynamic Analysis Has Found the Actual Value)",
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
                    "description": "Candidate values found via dynamic analysis. Select and apply one. If we see candidates in env_cmp.txt, this action is at the highest priority.",
                    "selection_criteria": "Usually first non-empty candidate is correct",
                    "requires_rerun": True,
                    "metadata_example": {
                        "variable_name": "sxid",
                        "config_path": "env.sxid"
                    }
                },
                "engineer_view": {
                    "tool": "set_environment_variable_value",
                    "action": "set_environment_variable_value",
                    "examples": [
                        {
                            "params": {
                                "name": "sxid",
                                "path": "env.sxid",
                                "value": "<actual_value_from_env_cmp.txt>",
                                "reason": "Candidate value from env_cmp.txt - replacing magic value with actual value"
                            }
                        }
                    ],
                    "notes": [
                        "Read env_cmp.txt from latest results directory",
                        "Pick first valid candidate (non-empty, non-garbage)",
                        "Use set_environment_variable_value to replace magic value with selected candidate",
                        "Re-run to verify new errors appear (progress indicator)",
                        "Compare console.log differences to confirm progress",
                        "Variable name is provided in option metadata - use metadata.variable_name directly"
                    ]
                }
            }
        }
    }
    
    def __init__(self, kb_path: Optional[Path] = None):
        """
        Initialize knowledge base.
        
        Always loads built-in knowledge, then merges with external KB if provided.
        
        Args:
            kb_path: Path to external KB file or directory containing JSON files
        """
        self.kb_path = kb_path
        
        # Start with built-in knowledge (always available)
        self.issues = dict(self.COMMON_ISSUES)
        
        # Load and merge external KB if path provided
        if kb_path:
            self._load_external_kb(kb_path)
    
    def _load_external_kb(self, kb_path: Path):
        """
        Load external knowledge base from file or directory.
        
        Args:
            kb_path: Path to JSON file or directory with JSON files
        """
        import json
        
        try:
            if kb_path.is_file():
                # Load single JSON file
                self._load_kb_file(kb_path)
            elif kb_path.is_dir():
                # Load all JSON files from directory
                json_files = list(kb_path.glob("*.json"))
                for json_file in json_files:
                    self._load_kb_file(json_file)
                print(f"[KB] Loaded {len(json_files)} external KB files from {kb_path}")
            else:
                print(f"[KB] Warning: Path not found: {kb_path}")
        except Exception as e:
            print(f"[KB] Error loading external KB: {e}")
    
    def _load_kb_file(self, file_path: Path):
        """
        Load a single KB JSON file and merge with existing issues.
        
        Expected JSON format:
        {
          "issue_id": {
            "title": "...",
            "severity": "...",
            "symptoms": [...],
            "solutions": {...}
          },
          ...
        }
        
        Args:
            file_path: Path to JSON file
        """
        import json
        
        try:
            with open(file_path, 'r') as f:
                external_issues = json.load(f)
            
            # Merge with existing issues
            for issue_id, issue_data in external_issues.items():
                if issue_id in self.issues:
                    print(f"[KB] Warning: Overriding built-in issue '{issue_id}' with external definition from {file_path.name}")
                self.issues[issue_id] = issue_data
            
            print(f"[KB] Loaded {len(external_issues)} issues from {file_path.name}")
        except json.JSONDecodeError as e:
            print(f"[KB] Error parsing JSON in {file_path}: {e}")
        except Exception as e:
            print(f"[KB] Error loading {file_path}: {e}")
    
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
            List of complete planner_view information for matched issues
        """
        results = []
        
        for issue_id, issue_data in self.issues.items():
            # Check if symptoms match
            if self._symptoms_match(symptoms, issue_data["symptoms"]):
                # Return the complete planner_view plus issue metadata
                planner_view = issue_data["solutions"]["planner_view"].copy()
                planner_view.update({
                    "issue_id": issue_id,
                    "title": issue_data["title"],
                    "severity": issue_data["severity"],
                    "symptoms": issue_data["symptoms"]
                })
                results.append(planner_view)
        
        return results
    
    def query_for_engineer(self, objective: str, issue_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Query KB from Engineer's perspective: implementation details.
        
        Args:
            objective: High-level objective to implement
            issue_id: Known issue ID (if available)
            
        Returns:
            List of complete engineer_view information for matched issues
        """
        results = []
        
        # If issue_id provided, get specific engineer_view
        if issue_id and issue_id in self.issues:
            engineer_view = self.issues[issue_id]["solutions"]["engineer_view"].copy()
            engineer_view.update({
                "issue_id": issue_id,
                "title": self.issues[issue_id]["title"],
                "severity": self.issues[issue_id]["severity"],
                "symptoms": self.issues[issue_id]["symptoms"]
            })
            return [engineer_view]
        
        # Otherwise, search based on objective keywords
        for issue_id, issue_data in self.issues.items():
            if self._objective_matches(objective, issue_data):
                # Return the complete engineer_view plus issue metadata
                engineer_view = issue_data["solutions"]["engineer_view"].copy()
                engineer_view.update({
                    "issue_id": issue_id,
                    "title": issue_data["title"],
                    "severity": issue_data["severity"],
                    "symptoms": issue_data["symptoms"]
                })
                results.append(engineer_view)
        
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
        return list(self.issues.keys())
    
    def get_issue_details(self, issue_id: str) -> Optional[Dict[str, Any]]:
        """Get complete details for a specific issue."""
        return self.issues.get(issue_id)
    
    def get_kb_stats(self) -> Dict[str, Any]:
        """Get statistics about the loaded knowledge base."""
        built_in_count = len(self.COMMON_ISSUES)
        total_count = len(self.issues)
        external_count = total_count - built_in_count
        
        return {
            "total_issues": total_count,
            "built_in": built_in_count,
            "external": external_count,
            "kb_path": str(self.kb_path) if self.kb_path else None
        }


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

