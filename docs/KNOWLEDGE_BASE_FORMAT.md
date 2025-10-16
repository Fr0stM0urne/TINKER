# Knowledge Base Format

## Overview

The Knowledge Base system supports both built-in knowledge (hard-coded) and external knowledge loaded from JSON files. External KB files are merged with built-in knowledge.

## File Locations

### Single JSON File
```ini
[KnowledgeBase]
enabled = true
path = /path/to/my_kb.json
```

### Directory with Multiple Files
```ini
[KnowledgeBase]
enabled = true
path = /path/to/kb_directory/
```
All `*.json` files in the directory will be loaded and merged.

## JSON Format

Each KB file should contain a dictionary of issues:

```json
{
  "issue_id_1": {
    "title": "Issue Title",
    "severity": "high|medium|low|critical",
    "symptoms": [
      "Symptom description 1",
      "Symptom description 2"
    ],
    "solutions": {
      "planner_view": {
        "priority": "critical|high|medium|low",
        "impact": "critical|high|medium|low|requires_iteration",
        "description": "Strategic description for planner",
        "requires_rerun": true,
        "next_steps": "What to do next",
        "selection_criteria": "How to choose between options"
      },
      "engineer_view": {
        "tool": "yaml_editor|patch_manager|hyperfile_builder|core_config",
        "action": "update_config|enable_patch|create_hyperfile|update_core",
        "examples": [
          {
            "params": {
              "file": "config.yaml",
              "path": "yaml.path.to.value",
              "value": "value_to_set",
              "reason": "Why this change is needed"
            }
          }
        ],
        "notes": [
          "Additional guidance note 1",
          "Additional guidance note 2"
        ]
      }
    }
  },
  
  "issue_id_2": {
    ...
  }
}
```

## Field Descriptions

### Top Level
- `issue_id`: Unique identifier for the issue (key in JSON)
- `title`: Human-readable title
- `severity`: How severe the issue is (for filtering/sorting)
- `symptoms`: List of observable symptoms that indicate this issue

### Planner View (Strategic Information)
- `priority`: How urgently this should be addressed
- `impact`: What impact fixing this has
- `description`: High-level description for planning
- `requires_rerun`: Whether this requires re-running Penguin
- `next_steps`: What to do after implementing (optional)
- `selection_criteria`: How to choose between multiple options (optional)

### Engineer View (Tactical Information)
- `tool`: Which tool to use
- `action`: What action to perform
- `examples`: List of concrete implementation examples
  - `params`: Tool-specific parameters
    - `file`: Config file to modify
    - `path`: YAML path (for yaml_editor)
    - `value`: Value to set
    - `reason`: Explanation
- `notes`: Additional implementation guidance (optional)

## Example: Custom KB File

`my_custom_kb.json`:
```json
{
  "missing_ld_library_path": {
    "title": "Missing LD_LIBRARY_PATH Environment Variable",
    "severity": "high",
    "symptoms": [
      "env_missing.yaml shows LD_LIBRARY_PATH",
      "Library loading errors in console",
      "Cannot open shared object"
    ],
    "solutions": {
      "planner_view": {
        "priority": "high",
        "impact": "critical",
        "description": "LD_LIBRARY_PATH needed for dynamic library loading",
        "requires_rerun": true
      },
      "engineer_view": {
        "tool": "yaml_editor",
        "action": "update_config",
        "examples": [
          {
            "params": {
              "file": "config.yaml",
              "path": "env.LD_LIBRARY_PATH",
              "value": "/lib:/usr/lib:/usr/local/lib",
              "reason": "Set library search path for dynamic linker"
            }
          }
        ]
      }
    }
  }
}
```

## Merging Behavior

1. **Built-in KB is always loaded first**
2. External KB files are loaded and merged
3. If external KB has same `issue_id` as built-in, external overrides built-in
4. All issues from all sources are available to agents

## Loading Order

1. Built-in KB (from `knowledge_base.py`)
2. If `path` is a file: Load that single JSON file
3. If `path` is a directory: Load all `*.json` files in alphabetical order

## Validation

The system does basic validation:
- JSON must be valid
- Each issue should have required fields
- Warnings are printed for missing/invalid data
- Errors don't crash the system - invalid entries are skipped

## Best Practices

1. **Organize by topic**: Use separate files for different issue categories
2. **Use descriptive IDs**: `missing_env_var_path` not `issue1`
3. **Include examples**: Engineer needs concrete examples to learn from
4. **Add context**: Use `notes` field for edge cases and tips
5. **Test incrementally**: Add one issue at a time and test
6. **Version control**: Keep KB files in git for tracking changes

