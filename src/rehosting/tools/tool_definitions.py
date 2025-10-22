"""
Tool definitions following the JSON format for Penguin rehosting tools.

This module provides structured tool definitions that match the format
used in tools.json for better parameter handling and validation.
"""

from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class ToolDefinition:
    """Definition of a tool following the JSON format."""
    name: str
    description: str
    parameters: Dict[str, Any]
    required: List[str]
    strict: bool = True


# Tool definitions following the JSON format from tools.json
TOOL_DEFINITIONS = {
    "change_init_program": ToolDefinition(
        name="change_init_program",
        description="Select a different system init program. Invoke if you see something like: Kernel panic - not syncing: Attempted to kill init! exitcode=0x00000000",
        parameters={
            "type": "object",
            "properties": {
                "error": {
                    "type": "string",
                    "description": "The error that led you to invoke this tool."
                }
            },
            "required": ["error"]
        },
        required=["error"],
        strict=True
    ),
    
    "add_environment_variable_placeholder": ToolDefinition(
        name="add_environment_variable_placeholder",
        description="Add a new environment variable with a magic placeholder value for dynamic discovery. This sets the variable to 'DYNVALDYNVALDYNVAL' so Penguin can detect what values it's compared against during rehosting. ⚠️ CRITICAL CONSTRAINT: This tool can ONLY be invoked ONCE per entire engineer execution cycle (across ALL options in the plan). Multiple placeholder variables will cause the rehosting to crash. If multiple variables need discovery, prioritize the most critical ONE and defer others to the next iteration. Never change the igloo_init env var. The env var name must be one that you see clear indication is missing. Do not make up fake arguments.",
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The name of the SINGLE environment variable to add for dynamic discovery. Only ONE variable can be discovered per rehosting cycle."
                },
                "reason": {
                    "type": "string",
                    "description": "A concise sentence explaining why THIS specific variable was chosen as the highest priority for discovery. What errors/signs did you see?"
                }
            },
            "required": ["name", "reason"],
            "additionalProperties": False
        },
        required=["name", "reason"],
        strict=True
    ),
    
    "set_environment_variable_value": ToolDefinition(
        name="set_environment_variable_value",
        description="Set the actual value for an environment variable that was previously added with a placeholder. Use this after dynamic discovery has found the real value.",
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The name of the environment variable to update."
                },
                "value": {
                    "type": "string",
                    "description": "The actual value to set for the environment variable."
                },
                "reason": {
                    "type": "string",
                    "description": "A concise sentence on why you are invoking this tool. What errors/signs did you see, if any?."
                }
            },
            "required": ["name", "value", "reason"],
            "additionalProperties": False
        },
        required=["name", "value", "reason"],
        strict=True
    ),
    
    "remove_environment_variable": ToolDefinition(
        name="remove_environment_variable",
        description="Remove an environment variable from the Penguin config.yaml. Never change the igloo_init env var. Do not make up any fake arguments.",
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The name of the environment variable to remove."
                },
                "reason": {
                    "type": "string",
                    "description": "A concise sentence on why you are invoking this tool. What errors/signs did you see, if any?."
                }
            },
            "required": ["name", "reason"],
            "additionalProperties": False
        },
        required=["name", "reason"],
        strict=True
    ),
    
    "add_pseudofile": ToolDefinition(
        name="add_pseudofile",
        description="Add a new pseudofile to the Penguin config.yaml modeling a device in /sys, /dev, or /proc (can only model files in these directories). If the file is an mtd (/dev/mtdX) device, specify the name of the MTD device as the <name> argument. We leave the devices unconfigured because we do not know what the system is trying to do with the device. The pseudofile path you provide must be one that you see indication is missing. Do not make up any fake arguments.",
        parameters={
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "The absolute filepath of the pseudofile. Should only include files in /sys, /dev, or /proc."
                },
                "name": {
                    "type": "string",
                    "description": "The name of the mtd device if this pseudofile path is an MTD."
                },
                "reason": {
                    "type": "string",
                    "description": "A concise sentence on why you are invoking this tool. What errors/signs did you see, if any?."
                }
            },
            "required": ["filepath", "name", "reason"],
            "additionalProperties": False
        },
        required=["filepath", "name", "reason"],
        strict=True
    ),
    
    "remove_pseudofile": ToolDefinition(
        name="remove_pseudofile",
        description="Remove a pseudofile from the Penguin config.yaml.",
        parameters={
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "The absolute filepath of the pseudofile to remove."
                },
                "reason": {
                    "type": "string",
                    "description": "A concise sentence on why you are invoking this tool. What errors/signs did you see, if any?."
                }
            },
            "required": ["filepath", "reason"],
            "additionalProperties": False
        },
        required=["filepath", "reason"],
        strict=True
    ),
    
    "set_file_read_behavior": ToolDefinition(
        name="set_file_read_behavior",
        description="Modify the READ model of a pseudofile if you have a specific value to return on 'reads'. Aka the content of the file.",
        parameters={
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "The absolute filepath of the pseudofile."
                },
                "model": {
                    "type": "string",
                    "enum": ["return_zero", "const_buf"],
                    "description": "The READ model to set. return_zero will just return 0 on a read. If you choose const_buf, specify the 'value' field of the string to return."
                },
                "value": {
                    "type": "string",
                    "description": "The value of the file buffer. This value will be returned when the file is read. Important if the model is 'const_buf'"
                },
                "reason": {
                    "type": "string",
                    "description": "A concise sentence on why you are invoking this tool. What errors/signs did you see, if any?."
                }
            },
            "required": ["filepath", "model", "value", "reason"],
            "additionalProperties": False
        },
        required=["filepath", "model", "value", "reason"],
        strict=True
    ),
    
    "grep_strace_output": ToolDefinition(
        name="grep_strace_output",
        description="Every process in the system will have its system calls traced (strace) and logged. Use this tool to grep that output and, for example, learn about a file's accesses.",
        parameters={
            "type": "object",
            "properties": {
                "grep_command": {
                    "type": "string",
                    "description": "The 'options' and 'pattern' part of the grep command to run (grep [options] pattern [files]). For example, to execute this command 'grep -c \"unix\" console.log' just provide '-c \"unix\"."
                },
                "reason": {
                    "type": "string",
                    "description": "A concise sentence on why you are invoking this tool. What errors/signs did you see, if any?."
                }
            },
            "required": ["grep_command", "reason"],
            "additionalProperties": False
        },
        required=["grep_command", "reason"],
        strict=True
    ),
    
    "replace_script_exit0": ToolDefinition(
        name="replace_script_exit0",
        description="Replace a script with exit0.sh (script that just returns success: 0). For example, if something keeps trying to tell the system to turn off with shutdown script '/bin/killall', replace it with 'exit0.sh'.",
        parameters={
            "type": "object",
            "properties": {
                "script_path": {
                    "type": "string",
                    "description": "The full path of the script to replace."
                },
                "reason": {
                    "type": "string",
                    "description": "A concise sentence on why you are invoking this tool. What errors/signs did you see, if any?."
                }
            },
            "required": ["script_path", "reason"],
            "additionalProperties": False
        },
        required=["script_path", "reason"],
        strict=False
    )
}


def get_tool_definition(tool_name: str) -> ToolDefinition:
    """Get tool definition by name."""
    return TOOL_DEFINITIONS.get(tool_name)


def list_available_tools() -> List[str]:
    """List all available tool names."""
    return list(TOOL_DEFINITIONS.keys())


def get_tool_schema(tool_name: str) -> Dict[str, Any]:
    """Get the JSON schema for a tool."""
    tool_def = get_tool_definition(tool_name)
    if not tool_def:
        return {}
    
    return {
        "type": "function",
        "function": {
            "name": tool_def.name,
            "description": tool_def.description,
            "parameters": tool_def.parameters
        }
    }


def get_all_tool_schemas() -> Dict[str, Any]:
    """Get all tool schemas in the format expected by the LLM."""
    return {
        tool_name: get_tool_schema(tool_name)
        for tool_name in list_available_tools()
    }
