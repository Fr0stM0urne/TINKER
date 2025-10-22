# TINKER Code Guide

**Target Audience**: Developers who want to understand and maintain the TINKER codebase.

**Last Updated**: October 21, 2025

---

## Table of Contents
1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Directory Structure](#directory-structure)
4. [Core Components](#core-components)
5. [Data Flow](#data-flow)
6. [Key Workflows](#key-workflows)
7. [Adding New Features](#adding-new-features)
8. [Debugging Tips](#debugging-tips)

---

## Project Overview

TINKER is an **LLM-guided firmware rehosting system** that uses multi-agent AI to automatically configure and improve firmware execution in the Penguin emulation framework.

**Main Goal**: Automatically discover missing configuration (environment variables, device files) needed for firmware to run successfully.

**Key Innovation**: Uses a **discovery mode** where the system adds placeholder values, runs the firmware, monitors what values it compares against, and then applies the discovered values.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              Main Entry Point (main.py)              │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│         Rehosting Workflow (rehosting_workflow.py)  │
│  • Penguin initialization                           │
│  • Iteration loop (3 iterations)                    │
│  • Context building (RAG dict)                      │
│  • Discovery mode tracking                          │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│      Multi-Agent Workflow (langgraph_workflow.py)   │
│  • LangGraph coordination                           │
│  • Planner → Engineer flow                          │
└──────────────┬────────────────────┬─────────────────┘
               │                    │
       ┌───────▼─────────┐  ┌──────▼──────────┐
       │  Planner Agent  │  │ Engineer Agent  │
       │  (planner.py)   │  │ (engineer.py)   │
       │                 │  │                 │
       │ • Analyze       │  │ • Execute plan  │
       │ • Generate plan │  │ • Use tools     │
       └─────────────────┘  └─────────────────┘
```

---

## Directory Structure

```
src/
├── main.py                          # CLI entry point
├── settings.py                      # Verbose mode configuration
├── penguin/                         # Penguin client wrapper
│   ├── client.py                    # PenguinClient for running firmware
│   ├── formatters.py                # Output formatting
│   └── results.py                   # Results parsing
│
└── rehosting/
    ├── rehosting_workflow.py        # Main orchestrator (iterative loop)
    │
    ├── agents/                      # LLM agents
    │   ├── __init__.py              # Exports
    │   ├── planner.py               # Planner agent (analyzes, generates plan)
    │   └── engineer.py              # Engineer agent (executes plan with tools)
    │
    ├── graph/                       # LangGraph workflow
    │   ├── __init__.py              # Exports
    │   └── langgraph_workflow.py   # Multi-agent coordination
    │
    ├── schemas/                     # Data models
    │   ├── __init__.py              # Exports
    │   ├── state.py                 # Shared state (goal, rag_context, discovery mode)
    │   └── action_record.py         # Action execution records
    │
    ├── tools/                       # Configuration tools
    │   ├── __init__.py              # Exports
    │   ├── config_tools.py          # Tool implementations (YAML modification)
    │   └── tool_definitions.py      # Tool schemas for LLM
    │
    └── knowledge_base.py            # Tactical/strategic guidance for agents
```

---

## Core Components

### 1. **main.py** - Entry Point
- Loads `config.ini`
- Validates firmware path
- Calls `rehost_firmware()`
- Handles errors and prints results

### 2. **rehosting_workflow.py** - Main Orchestrator
**Purpose**: Iterative rehosting loop that runs Penguin and invokes multi-agent workflow.

**Key Functions**:
- `rehost_firmware()`: Main entry point, orchestrates the full workflow
- `_build_multi_agent_context()`: Converts Penguin results into structured dict (key=source, value=content)
- `_check_discovery_mode_transitions()`: Detects when to enter/exit discovery mode
- `_initialize_penguin()`: Sets up Penguin project
- `_run_penguin_iteration()`: Executes one Penguin run

**Important**: Context is now a **dict** with keys like `"console.log"`, `"env_cmp.txt"`, `"pseudofiles_failures.yaml"` for efficient filtering.

### 3. **agents/planner.py** - Planner Agent
**Purpose**: Analyzes Penguin results and generates configuration update plans.

**Class**: `FirmwarePlannerAgent`

**Key Methods**:
- `plan(state)`: Main entry point, generates `FirmwareConfigPlan`
- `_build_context(state)`: Builds LLM prompt context
  - **Normal mode**: Full context (config.yaml, all results, KB insights)
  - **Discovery mode**: Only `env_cmp.txt` and `console.log`
- `_call_llm()`: Calls Ollama with appropriate prompt (normal or discovery)
- `_parse_plan()`: Parses JSON response into plan object

**Prompts**:
- `SYSTEM_PROMPT`: Normal mode instructions (analyze, generate options)
- `DISCOVERY_MODE_PROMPT`: Discovery mode instructions (apply/remove discovered value)
- `RETRY_SYSTEM_PROMPT`: Used on JSON parsing failures

**Important Notes**:
- Discovery mode has **HARD LIMIT: EXACTLY ONE option**
- Metadata field provides structured data to Engineer (variable_name, config_path, device_path)
- Config.yaml is converted to JSON before showing to LLM

### 4. **agents/engineer.py** - Engineer Agent
**Purpose**: Executes configuration update plans using tools.

**Class**: `EngineerAgent`

**Key Methods**:
- `execute_plan(plan)`: Executes all options in a plan
- `_execute_single_option()`: Executes one option with LLM reasoning
- `_call_llm_for_implementation()`: Gets tool call decisions from LLM
- `_execute_tool_calls()`: Actually runs the tools

**Prompts**:
- `SYSTEM_PROMPT`: Normal mode execution instructions
- `DISCOVERY_MODE_PROMPT`: Discovery mode execution instructions (set_value or remove)

**Tools Available**: (from `tool_definitions.py`)
- `add_environment_variable_placeholder`: Adds discovery placeholder (⚠️ ONLY ONCE)
- `set_environment_variable_value`: Sets env var with known value
- `remove_environment_variable`: Removes env var
- `add_pseudofile`: Adds device file entry

### 5. **graph/langgraph_workflow.py** - Multi-Agent Coordination
**Purpose**: LangGraph state machine that coordinates Planner → Engineer flow.

**Class**: `RehostingWorkflow`

**Graph Flow**:
```
START → planner_node → engineer_node → END
```

**Key Methods**:
- `run()`: Executes the workflow with initial state
- `planner_node()`: Calls planner agent
- `engineer_node()`: Calls engineer agent
- `should_continue()`: Always continues to engineer (no early exit)

**State Management**: Uses `RehostingState` (TypedDict) with accumulating action records.

### 6. **schemas/state.py** - Shared State
**Purpose**: Defines the state passed between agents.

**Key Fields**:
- `goal`: Task objective (string)
- `rag_context`: **Dict[str, str]** - Penguin results by source name
- `plan`: Current plan from Planner
- `discovery_mode`: Boolean flag
- `discovery_variable`: Name of variable being discovered
- `previous_actions`: Accumulated action history
- `project_path`: Path to Penguin project

### 7. **tools/config_tools.py** - Configuration Tools
**Purpose**: Implements tools that modify `config.yaml`.

**Class**: `ConfigToolRegistry`

**Available Tools**:
- `add_environment_variable_placeholder(name, reason)`
- `set_environment_variable_value(name, value, reason)`
- `remove_environment_variable(name, reason)`
- `add_pseudofile(device_path, content_type, reason)`

**Important**: All tools use `ruamel.yaml` to preserve YAML formatting and comments.

### 8. **knowledge_base.py** - Tactical Guidance
**Purpose**: Provides examples and patterns to agents based on symptoms.

**Functions**:
- `query_for_planner(symptoms)`: Returns strategic guidance (priorities, patterns)
- `query_for_engineer(query)`: Returns tactical guidance (tool examples, implementation notes)

**Structure**:
- `planner_view`: High-level patterns, priorities, metadata examples
- `engineer_view`: Tool usage examples, parameters, notes

---

## Data Flow

### Iteration Loop (Normal Mode)
```
1. Penguin runs firmware → generates results
2. Results parsed into dict: {"console.log": "...", "env_missing.yaml": "...", ...}
3. Planner receives dict, analyzes ALL sources
4. Planner generates plan with multiple options (env vars, pseudofiles, etc.)
5. Engineer executes options using tools (modifies config.yaml)
6. Repeat for next iteration
```

### Discovery Mode Flow
```
Iteration 1 (Normal):
  Planner: "Missing env var 'sxid', value unknown"
  → Generates option with add_environment_variable_placeholder
  Engineer: Adds "sxid=DYNVALDYNVALDYNVAL" to config.yaml
  → Sets discovery_mode=True, discovery_variable="sxid"

Iteration 2 (Discovery):
  Penguin runs with placeholder → env_cmp.txt contains discovered values
  Planner receives ONLY {"env_cmp.txt": "...", "console.log": "..."}
  → Analyzes env_cmp.txt
  → If candidates found: Generate "set_value" option
  → If empty: Generate "remove_variable" option
  Engineer: Executes the single option
  → Sets discovery_mode=False

Iteration 3 (Normal):
  Continue normal workflow with discovered value applied
```

---

## Key Workflows

### Adding an Environment Variable
1. Planner detects missing variable from `console.log` or `env_missing.yaml`
2. Generates option with metadata: `{"variable_name": "sxid", "config_path": "env.sxid"}`
3. If value unknown → uses `add_environment_variable_placeholder`
4. If value known → uses `set_environment_variable_value`

### Adding a Pseudofile (Device File)
1. Planner detects missing device from `pseudofiles_failures.yaml` or `console.log`
2. Generates option with metadata: `{"device_path": "/dev/mtd1"}`
3. Engineer calls `add_pseudofile` with device path and content type

### Discovery Mode Entry/Exit
- **Entry**: Engineer executes `add_environment_variable_placeholder`
- **Exit**: Engineer executes `set_environment_variable_value` or `remove_environment_variable`
- **Detection**: `_check_discovery_mode_transitions()` monitors action types

---

## Adding New Features

### Adding a New Tool
1. **Define schema** in `tools/tool_definitions.py`:
   ```python
   ToolDefinition(
       name="my_new_tool",
       description="What it does",
       parameters=[
           ToolParameter(name="param1", type="string", required=True, description="...")
       ]
   )
   ```

2. **Implement tool** in `tools/config_tools.py`:
   ```python
   def my_new_tool(self, param1: str, reason: str) -> Dict[str, Any]:
       """Implementation"""
       # Modify config.yaml
       # Return success/failure
   ```

3. **Update Engineer prompt** to mention the new tool capability.

### Adding New Context Sources
1. Update `_build_multi_agent_context()` in `rehosting_workflow.py` to parse new section
2. Add key to context_dict: `context_dict["new_source.txt"] = content`
3. Update Planner's `_extract_symptoms()` to detect new source
4. Update `SYSTEM_PROMPT` to mention when to use this source

### Extending Discovery Mode
Currently only supports environment variables. To extend:
1. Update `_check_discovery_mode_transitions()` to detect other placeholder types
2. Add new placeholder tool and corresponding set/remove tools
3. Update discovery mode prompts in both Planner and Engineer
4. Update Penguin to capture comparison data for new type

---

## Debugging Tips

### Enable Verbose Mode
```bash
python src/main.py --verbose > test_log.txt
```

**Shows**:
- Full LLM prompts (system + user)
- LLM responses (raw JSON)
- Context building details
- Tool execution details
- Discovery mode transitions

### Common Issues

#### "LLM returns invalid JSON"
- Check `test_log.txt` for LLM response
- Look for markdown code fences (```json)
- Verify schema matches `EXPECTED_RESPONSE_SCHEMA`
- Planner has 3 retry attempts with stricter prompt

#### "Discovery mode not triggering"
- Check if `add_environment_variable_placeholder` was called
- Look for `"ENTERING DISCOVERY MODE"` message
- Verify action.tool matches exactly
- Check action.input contains "name" field

#### "Context too large / missing data"
- In discovery mode, only `env_cmp.txt` and `console.log` should be in context
- Check `_build_context()` filtering logic
- Verify `rag_context` is dict with correct keys

#### "Config.yaml not updating"
- Check tool execution logs
- Verify `project_path` is correct
- Check file permissions
- Look for YAML parsing errors

### Useful Grep Searches
```bash
# Find where discovery mode is set
grep -r "discovery_mode.*True" src/

# Find tool definitions
grep -r "ToolDefinition" src/

# Find LLM calls
grep -r "chat(" src/

# Find state updates
grep -r "return {" src/rehosting/agents/
```

---

## Code Style Guidelines

### Comments
- **Functions**: Docstring with purpose, args, returns
- **Complex logic**: Inline comments explaining "why", not "what"
- **Constants**: Comment explaining purpose and constraints

### Naming
- **Functions**: Verb phrases (`build_context`, `execute_plan`)
- **Private functions**: Prefix with `_` (`_call_llm`, `_parse_plan`)
- **Classes**: Nouns (`FirmwarePlannerAgent`, `ConfigToolRegistry`)
- **Variables**: Descriptive (`discovery_variable`, not `dv`)

### Error Handling
- Use try/except with specific exceptions
- Log errors with context
- Return fallback values when possible
- Accumulate errors in workflow_state["errors"]

---

## Future Improvements

### Potential Enhancements
1. **Multi-variable discovery**: Support discovering multiple env vars in parallel
2. **Smarter context filtering**: Use embeddings to select relevant context
3. **Cost tracking**: Monitor LLM token usage
4. **Config rollback**: Save config.yaml versions, rollback on failures
5. **Tool validation**: Pre-execution validation of tool parameters
6. **Parallel agent execution**: Run multiple engineer options concurrently
7. **Human-in-the-loop**: Ask for confirmation on critical changes

### Known Limitations
- Discovery mode only supports one variable at a time
- No automatic recovery from bad config changes
- Limited to 3 iterations (configurable but hardcoded logic)
- No memory across separate rehosting sessions

---

## Getting Help

### Resources
- **Main README**: `/README.md` - Setup and usage
- **LangGraph Docs**: https://langchain-ai.github.io/langgraph/
- **Penguin Docs**: `penguin/docs/` - Penguin-specific features

### Debugging Workflow
1. Run with `--verbose`
2. Check `test_log.txt` for full execution trace
3. Look for error messages with `grep "❌\|Error\|Failed" test_log.txt`
4. Check LLM prompts and responses in verbose output
5. Verify config.yaml changes in project directory

---

## Quick Reference

### Important Files (Priority Order)
1. `src/main.py` - Start here
2. `src/rehosting/rehosting_workflow.py` - Main loop
3. `src/rehosting/agents/planner.py` - Analysis logic
4. `src/rehosting/agents/engineer.py` - Execution logic
5. `src/rehosting/graph/langgraph_workflow.py` - Coordination
6. `src/rehosting/tools/config_tools.py` - Tool implementations

### Key Constants
- **Max iterations**: `config['Penguin']['max_iter']` (default: 3)
- **Discovery placeholder**: `"DYNVALDYNVALDYNVAL"`
- **LLM model**: `config['Ollama']['model']` (default: llama3.3:latest)
- **Max retries**: 3 (planner), 2 (engineer)

### State Transitions
```
Normal → Discovery: add_environment_variable_placeholder executed
Discovery → Normal: set_environment_variable_value or remove_environment_variable executed
```

---

**End of Code Guide**

For questions or contributions, please refer to the main repository documentation.
