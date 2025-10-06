"""LangGraph construction and orchestration logic."""

from typing import Dict, Any
from langgraph.graph import StateGraph, END
from ..schemas import State
from ..agents import PlannerAgent


def build_graph(model: str = "llama3.3:latest") -> StateGraph:
    """
    Build the multi-agent orchestration graph.
    
    Args:
        model: Ollama model to use for agents
        
    Returns:
        Compiled StateGraph ready for execution
    """
    # Initialize agents
    planner = PlannerAgent(model=model)
    
    # Create the graph with State schema
    graph = StateGraph(State)
    
    # Add nodes
    graph.add_node("planner", planner)
    # Note: evaluator and engineer nodes will be added later
    
    # Set entry point
    graph.set_entry_point("planner")
    
    # Conditional edges (simplified for now - will expand with evaluator/engineer)
    def plan_ready(state: State) -> str:
        """Determine next step after planning."""
        if state.plan is None:
            return "end"  # No plan generated, something went wrong
        # TODO: When evaluator is added, route to "to_eval"
        return "end"  # For now, just end after planning
    
    graph.add_conditional_edges(
        "planner",
        plan_ready,
        {
            "end": END,
            # "to_eval": "evaluator",  # Will uncomment when evaluator is ready
        }
    )
    
    # Compile the graph
    compiled_graph = graph.compile()
    
    return compiled_graph


def create_initial_state(
    goal: str,
    budget: Dict[str, Any] = None,
    rag_context: list = None
) -> State:
    """
    Helper to create an initial state for the graph.
    
    Args:
        goal: The user's task or objective
        budget: Optional resource constraints
        rag_context: Optional pre-loaded context
        
    Returns:
        Initialized State object
    """
    return State(
        goal=goal,
        budget=budget or {"max_iterations": 10},
        rag_context=rag_context or []
    )

