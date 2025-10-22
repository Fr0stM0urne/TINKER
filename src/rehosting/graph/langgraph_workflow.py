"""
LangGraph workflow for coordinating Planner and Engineer agents.

This workflow orchestrates the multi-agent system where:
1. Planner analyzes results and generates configuration update plans
2. Plans are automatically approved (for now - can add Evaluator later)
3. Engineer executes the approved plan options in sequence
"""

import configparser
from pathlib import Path
from typing import Dict, Any, TypedDict, Annotated, Sequence
import operator

from langgraph.graph import StateGraph, END
from src.rehosting.agents import FirmwarePlannerAgent, EngineerAgent
from src.rehosting.schemas import State, ActionRecord
from src.settings import is_verbose, verbose_print


class RehostingState(TypedDict):
    """
    State for the rehosting workflow.
    
    This extends the base State with rehosting-specific fields.
    """
    # Base fields from State
    goal: str
    plan: Any  # FirmwareConfigPlan
    rag_context: dict[str, str]  # Changed from list to dict (key=source, value=content)
    budget: dict[str, Any]
    done: bool
    
    # Rehosting-specific fields
    firmware_path: str
    project_path: str
    
    # Execution tracking
    actions: Annotated[Sequence[ActionRecord], operator.add]  # Append-only list
    engineer_summary: list[dict]
    execution_complete: bool
    
    # Discovery mode tracking
    discovery_mode: bool
    discovery_variable: str
    
    # Results
    errors: list[str]


class RehostingWorkflow:
    """
    Multi-agent workflow for firmware rehosting configuration updates.
    
    Workflow:
    1. START → Planner
    2. Planner → Engineer (plan is automatically approved)
    3. Engineer → END (after executing all options)
    
    Future extensions:
    - Add Evaluator node between Planner and Engineer
    - Add feedback loop for plan refinement
    - Add Stop Checker for iterative improvements
    """
    
    def __init__(
        self,
        config: configparser.ConfigParser,
        project_path: Path,
        verbose: bool = False
    ):
        """
        Initialize the rehosting workflow.
        
        Args:
            config: Configuration from config.ini
            project_path: Path to the Penguin project
            verbose: Enable verbose logging
        """
        self.config = config
        self.project_path = project_path
        self.verbose = verbose
        
        # Initialize agents with shared knowledge base (if enabled)
        model = config.get('Ollama', 'model', fallback='llama3.3:latest')
        
        # Check if KB is enabled in config
        kb_enabled = config.getboolean('KnowledgeBase', 'enabled', fallback=True) if config.has_section('KnowledgeBase') else True
        kb_path = None
        
        if kb_enabled:
            # Get custom KB path if specified
            if config.has_option('KnowledgeBase', 'path'):
                kb_path_str = config.get('KnowledgeBase', 'path')
                if kb_path_str and kb_path_str.strip():
                    kb_path = Path(kb_path_str)
            
            if is_verbose():
                verbose_print("Knowledge Base: ENABLED", prefix="[WORKFLOW]")
                if kb_path:
                    verbose_print(f"  Custom KB path: {kb_path}", prefix="[WORKFLOW]")
                else:
                    verbose_print("  Using built-in KB", prefix="[WORKFLOW]")
        else:
            if is_verbose():
                verbose_print("Knowledge Base: DISABLED", prefix="[WORKFLOW]")
        
        # Get engineer configuration
        max_options = config.getint('Engineer', 'max_options', fallback=3) if config.has_section('Engineer') else 3
        
        self.planner = FirmwarePlannerAgent(model=model, kb_path=kb_path if kb_enabled else None)
        self.engineer = EngineerAgent(
            project_path=project_path, 
            model=model, 
            kb_path=kb_path if kb_enabled else None,
            max_options=max_options
        )
        
        # Build the graph
        self.graph = self._build_graph()
        self.app = self.graph.compile()
    
    def _build_graph(self) -> StateGraph:
        """
        Build the LangGraph workflow.
        
        Returns:
            Compiled StateGraph ready for execution
        """
        # Create graph with our state schema
        workflow = StateGraph(RehostingState)
        
        # Add nodes
        workflow.add_node("planner", self._planner_node)
        workflow.add_node("engineer", self._engineer_node)
        
        # Define edges
        workflow.set_entry_point("planner")
        
        # Planner → Engineer (automatic approval for now)
        workflow.add_edge("planner", "engineer")
        
        # Engineer → END
        workflow.add_edge("engineer", END)
        
        if is_verbose():
            verbose_print("=" * 70)
            verbose_print("WORKFLOW: GRAPH BUILT", prefix="[WORKFLOW]")
            verbose_print("=" * 70)
            verbose_print("Nodes: planner, engineer", prefix="[WORKFLOW]")
            verbose_print("Flow: START → planner → engineer → END", prefix="[WORKFLOW]")
            verbose_print("=" * 70)
        
        return workflow
    
    def _planner_node(self, state: RehostingState) -> Dict[str, Any]:
        """
        Planner node - generates configuration update plan.
        
        Args:
            state: Current workflow state
            
        Returns:
            State updates with the generated plan
        """
        if is_verbose():
            verbose_print("=" * 70)
            verbose_print("NODE: PLANNER", prefix="[WORKFLOW]")
            verbose_print("=" * 70)
        
        print("\n" + "=" * 70)
        print("🧠 PLANNER: Analyzing results and generating plan...")
        print("=" * 70)
        
        # Convert to State object for planner, including previous execution context
        planner_state = State(
            goal=state["goal"],
            rag_context=state["rag_context"],
            budget=state["budget"],
            project_path=state.get("project_path"),
            discovery_mode=state.get("discovery_mode", False),
            discovery_variable=state.get("discovery_variable")
        )
        
        # Add previous execution context for learning from past iterations
        if state.get("actions"):
            planner_state.previous_actions = state["actions"]
        if state.get("engineer_summary"):
            planner_state.previous_engineer_summary = state["engineer_summary"]
        
        # Call planner (returns {"plan": plan_object})
        updates = self.planner(planner_state)
        
        if is_verbose():
            verbose_print("Planner returned updates", prefix="[WORKFLOW]")
            verbose_print(f"Plan ID: {updates.get('plan').id if updates.get('plan') else 'None'}", prefix="[WORKFLOW]")
        
        return updates
    
    def _engineer_node(self, state: RehostingState) -> Dict[str, Any]:
        """
        Engineer node - executes the plan options in sequence.
        
        Args:
            state: Current workflow state
            
        Returns:
            State updates with execution results
        """
        if is_verbose():
            verbose_print("=" * 70)
            verbose_print("NODE: ENGINEER", prefix="[WORKFLOW]")
            verbose_print("=" * 70)
        
        print("\n" + "=" * 70)
        print("🔧 ENGINEER: Executing configuration updates...")
        print("=" * 70)
        
        # Call engineer (returns {"actions": [...], "engineer_summary": [...], ...})
        updates = self.engineer(state)
        
        if is_verbose():
            verbose_print("Engineer returned updates", prefix="[WORKFLOW]")
            verbose_print(f"Actions: {len(updates.get('actions', []))}", prefix="[WORKFLOW]")
            verbose_print(f"Complete: {updates.get('execution_complete', False)}", prefix="[WORKFLOW]")
        
        # Mark workflow as done
        updates["done"] = True
        
        return updates
    
    def run(
        self,
        firmware_path: str,
        rag_context: dict[str, str],
        goal: str = "Analyze Penguin rehosting results and generate configuration update plan",
        discovery_mode: bool = False,
        discovery_variable: str = None
    ) -> Dict[str, Any]:
        """
        Run the complete workflow.
        
        Args:
            firmware_path: Path to the firmware being rehosted
            rag_context: Context from Penguin results (dict with source keys)
            goal: Primary goal for the planner
            discovery_mode: Whether in discovery mode
            discovery_variable: Name of variable being discovered
            
        Returns:
            Final state after workflow completion
        """
        # Initialize state
        initial_state: RehostingState = {
            "goal": goal,
            "plan": None,
            "rag_context": rag_context,
            "budget": {
                "max_iterations": int(self.config.get('Penguin', 'max_iter', fallback=10))
            },
            "done": False,
            "firmware_path": firmware_path,
            "project_path": str(self.project_path),
            "actions": [],
            "engineer_summary": [],
            "execution_complete": False,
            "discovery_mode": discovery_mode,
            "discovery_variable": discovery_variable or "",
            "errors": []
        }
        
        if is_verbose():
            verbose_print("=" * 70)
            verbose_print("WORKFLOW: STARTING", prefix="[WORKFLOW]")
            verbose_print("=" * 70)
            verbose_print(f"Firmware: {firmware_path}", prefix="[WORKFLOW]")
            verbose_print(f"Project: {self.project_path}", prefix="[WORKFLOW]")
            verbose_print(f"Goal: {goal}", prefix="[WORKFLOW]")
            verbose_print(f"Context sources: {list(rag_context.keys())}", prefix="[WORKFLOW]")
            verbose_print("=" * 70)
        
        print("\n" + "=" * 70)
        print("🚀 MULTI-AGENT WORKFLOW: Starting")
        print("=" * 70)
        print(f"Firmware: {firmware_path}")
        print(f"Project: {self.project_path}")
        print("=" * 70)
        
        # Run the graph
        final_state = self.app.invoke(initial_state)
        
        if is_verbose():
            verbose_print("=" * 70)
            verbose_print("WORKFLOW: COMPLETED", prefix="[WORKFLOW]")
            verbose_print("=" * 70)
            verbose_print(f"Done: {final_state.get('done', False)}", prefix="[WORKFLOW]")
            verbose_print(f"Total actions: {len(final_state.get('actions', []))}", prefix="[WORKFLOW]")
            verbose_print("=" * 70)
        
        return final_state
    
    def get_plan(self, state: RehostingState) -> Any:
        """Extract the plan from the workflow state."""
        return state.get("plan")
    
    def get_actions(self, state: RehostingState) -> list[ActionRecord]:
        """Extract action records from the workflow state."""
        return state.get("actions", [])
    
    def get_summary(self, state: RehostingState) -> list[dict]:
        """Extract execution summary from the workflow state."""
        return state.get("engineer_summary", [])


def create_rehosting_workflow(
    config: configparser.ConfigParser,
    project_path: Path,
    verbose: bool = False
) -> RehostingWorkflow:
    """
    Create a rehosting workflow instance.
    
    Args:
        config: Configuration from config.ini
        project_path: Path to the Penguin project
        verbose: Enable verbose logging
        
    Returns:
        Configured RehostingWorkflow ready to run
    """
    return RehostingWorkflow(config, project_path, verbose)

