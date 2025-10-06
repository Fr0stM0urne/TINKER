# 🧩 Multi-Agent LangGraph System — Implementation Blueprint
 
**Purpose:** Define a modular, general-purpose multi-agent framework using **LangChain + LangGraph** to coordinate a **Planner**, **Evaluator**, and **Engineer** with a shared **RAG (Retrieval & Update)** backend.  
**Audience:** Engineering collaborator responsible for implementation.

---

## 1. System Overview

This framework generalizes multi-agent orchestration for LLM tasks.  
It can be customized by changing agent prompts, available tools, or task goals — no logic changes required.

**Core agents:**
1. **Planner** – decomposes the task into structured steps.  
2. **Evaluator** – reviews and critiques the plan or the Engineer’s results.  
3. **Engineer** – executes the plan using tool calls, APIs, or function invocations.  

**Shared subsystems:**
- **RAG (Retrieval & Update):** shared contextual knowledge base accessed by both Planner and Evaluator; continuously updated with post-execution feedback.  
- **Shared Memory (State/Scratchpad):** global state for plan, results, and decisions.  
- **Acceptance & Stop Checker:** deterministic gate to decide whether to stop or loop.  

**Primary library stack:**  
- `langgraph` for orchestration  
- `langchain-core` for prompt templates, retrievers, and tools  
- `pydantic` for structured state and validation  

---

## 2. High-Level Flow

```text
User → Orchestrator → Planner → Evaluator → Engineer → RAG → StopChecker → Orchestrator → User
```

1. **User / upstream agent** provides a goal or question.  
2. **Planner** decomposes into an executable plan (`Plan` object).  
3. **Evaluator** validates the plan for logic, feasibility, and safety.  
4. **Engineer** executes approved steps using available tools.  
5. **Evaluator** re-checks the outputs; if quality fails, sends patches to Planner.  
6. **Planner** may refine or extend the plan and continue execution.  
7. **Engineer** updates **RAG** with new findings, logs, or validated results.  
8. **Stop Checker** tests if acceptance criteria are met → stop or continue.  
9. **Orchestrator** returns the final response.

---

## 3. Graph Node Design

| Node | Responsibility | Input | Output |
|------|-----------------|--------|---------|
| **Planner** | Decompose the task into structured plan steps | `goal`, `state`, `rag_context` | `plan: Plan` |
| **Evaluator** | Critique or approve plans and results | `plan` or `action_result` | `critique`, `needs_revision` |
| **Engineer** | Execute plan steps using registered tools | `plan`, `state` | `action_record`, `tool_result` |
| **RAG (Retrieval & Update)** | Provide context + absorb new validated knowledge | `query` or `docs` | `docs[]` |
| **Stop Checker** | Determine if final conditions met | `state`, `metrics` | `done: bool` |
| **Orchestrator** | Manage state transitions and LangGraph execution | user input | final output |

---

## 4. State Schema (Pydantic)

```python
class Plan(BaseModel):
    id: str
    objectives: list[str]
    steps: list[dict]
    acceptance_criteria: dict
    revision_notes: list[str] = []

class Critique(BaseModel):
    needs_revision: bool
    issues: list[str]
    patches: list[dict]

class ActionRecord(BaseModel):
    step_id: str
    tool: str
    input: dict
    output_uri: str
    summary: str
    status: str

class State(BaseModel):
    goal: str
    plan: Plan | None = None
    critiques: list[Critique] = []
    actions: list[ActionRecord] = []
    rag_context: list[str] = []
    budget: dict = {}
    done: bool = False
```

---

## 5. RAG Interface

```python
class RAG:
    def __init__(self, retriever, index):
        self.retriever = retriever
        self.index = index

    def retrieve(self, query: str, k: int = 5):
        """Return top-k documents for Planner/Evaluator context."""
        return self.retriever.get_relevant_documents(query, k=k)

    def upsert(self, docs: list[dict]):
        """Insert/update new validated data or logs from Engineer/Evaluator."""
        self.index.add_documents(docs)
```

**Important:**  
- Deduplicate by content hash.  
- Include provenance metadata (`source_agent`, `timestamp`, `acceptance_passed`).  
- Consider a secondary, higher-quality embedder for post-run re-embedding.

---

## 6. LangGraph Structure

```python
graph = StateGraph(State)
graph.add_node("planner", planner_node)
graph.add_node("evaluator", evaluator_node)
graph.add_node("engineer", engineer_node)
graph.add_node("rag", rag_node)
graph.add_node("stop_checker", stop_checker_node)

graph.add_conditional_edges("planner", condition=plan_ready, path_map={
    "to_eval": "evaluator",
})

graph.add_conditional_edges("evaluator", condition=evaluation_result, path_map={
    "needs_revision": "planner",
    "approved": "engineer",
})

graph.add_conditional_edges("engineer", condition=execution_result, path_map={
    "requires_refinement": "planner",
    "quality_check": "evaluator",
    "done": "stop_checker",
})
```

---

## 7. Prompts & Roles

### Planner Prompt
> You are a planning agent. Given a user goal and prior state, produce a JSON plan with clear ordered steps, required tools, and acceptance criteria.

### Evaluator Prompt
> You are a critic and reviewer. Check if the plan or result is feasible, safe, and well-scoped. Return structured feedback (`needs_revision`, `issues`, `patches`).

### Engineer Prompt
> You are an executor. Follow the current approved plan step-by-step, invoking appropriate tools. Report each action in structured form (`ActionRecord`).

---

## 8. Tooling & Registry

- Use a **Tool Router** to dynamically select the right LangChain tool per plan step.  
- Validate tool inputs via Pydantic; handle invalid schema by rerouting to Planner.  
- Log results to the shared state, not the console.

---

## 9. Knowledge Update Loop

1. Engineer completes execution → generates structured notes.  
2. Evaluator confirms validity → extracts relevant excerpts.  
3. Both push updates to `rag.upsert()` to improve future retrieval quality.  
4. Store provenance in metadata:  
   ```json
   {"source_agent": "engineer", "task_id": "...", "validated": true}
   ```

---

## 10. Termination Logic

- **Stop Checker** compares outputs against the plan’s acceptance criteria:
  - Required keys present  
  - Metrics/thresholds met  
  - Budget/cost under limit  
- If success → `state.done=True`; else route back to Planner.

---

## 11. Next Steps for Implementation

1. Scaffold base repo:
   ```bash
   src/
     ├── agents/
     │   ├── planner.py
     │   ├── evaluator.py
     │   ├── engineer.py
     ├── graph/
     │   └── build_graph.py
     ├── rag/
     │   ├── retriever.py
     │   ├── index.py
     └── schemas/
         ├── plan.py
         ├── critique.py
         ├── state.py
   ```
2. Implement stubs for each node using LangGraph’s `Node` pattern.  
3. Integrate a basic retriever (FAISS or Qdrant) for RAG.  
4. Build simple example tasks (e.g., summarize documents, data analysis pipeline).  
5. Validate loop termination and persistence using LangGraph checkpoints.

---

## 12. Diagram Reference

See architecture diagram **v4** (`multi_agent_langgraph_architecture_v4.png`):  
Planner ↔ Evaluator ↔ Engineer, all sharing a single RAG, with feedback and updates flowing continuously.
