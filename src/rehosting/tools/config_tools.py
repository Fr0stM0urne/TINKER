"""
Tools for updating Penguin configuration files.

These tools allow the Engineer agent to modify YAML config files
based on the plan provided by the Planner.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class ConfigUpdateResult(BaseModel):
    """Result of a configuration update operation."""
    
    success: bool = Field(description="Whether the update was successful")
    message: str = Field(description="Human-readable message about the operation")
    file_path: str = Field(description="Path to the modified file")
    changes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Summary of changes made"
    )


class YAMLConfigEditor:
    """
    Tool for editing YAML configuration files.
    
    Supports:
    - Updating nested values using dot notation paths
    - Adding new entries to lists
    - Creating new sections
    - Validating changes before writing
    """
    
    def __init__(self, config_base_path: Optional[Path] = None):
        """
        Initialize the YAML editor.
        
        Args:
            config_base_path: Base directory for config files (defaults to current working dir)
        """
        self.config_base_path = config_base_path or Path.cwd()
    
    def update_value(
        self,
        file_path: str,
        yaml_path: str,
        value: Any,
        reason: str = ""
    ) -> ConfigUpdateResult:
        """
        Update a value in a YAML file using dot notation path.
        
        Args:
            file_path: Path to YAML file (relative to config_base_path)
            yaml_path: Dot-separated path to the value (e.g., "core.root_shell" or "env.PATH")
            value: New value to set
            reason: Explanation for why this change is needed
            
        Returns:
            ConfigUpdateResult with operation details
            
        Examples:
            >>> editor.update_value("config.yaml", "core.root_shell", True, "Enable shell access")
            >>> editor.update_value("config.yaml", "env.PATH", "/usr/bin:/bin", "Add PATH env var")
        """
        full_path = self.config_base_path / file_path
        
        try:
            # Load existing config
            if full_path.exists():
                with open(full_path, 'r') as f:
                    config = yaml.safe_load(f) or {}
            else:
                return ConfigUpdateResult(
                    success=False,
                    message=f"Config file not found: {full_path}",
                    file_path=str(full_path),
                    changes={}
                )
            
            # Navigate to the target location
            path_parts = yaml_path.split('.')
            target = config
            
            # Navigate to parent
            for part in path_parts[:-1]:
                if part not in target:
                    target[part] = {}
                target = target[part]
            
            # Get old value for change tracking
            old_value = target.get(path_parts[-1], None)
            
            # Set new value
            target[path_parts[-1]] = value
            
            # Write back to file
            with open(full_path, 'w') as f:
                yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
            
            return ConfigUpdateResult(
                success=True,
                message=f"Updated {yaml_path} in {file_path}. Reason: {reason}",
                file_path=str(full_path),
                changes={
                    "path": yaml_path,
                    "old_value": old_value,
                    "new_value": value,
                    "reason": reason
                }
            )
            
        except Exception as e:
            return ConfigUpdateResult(
                success=False,
                message=f"Failed to update {yaml_path}: {str(e)}",
                file_path=str(full_path),
                changes={}
            )
    
    def add_to_list(
        self,
        file_path: str,
        yaml_path: str,
        value: Any,
        reason: str = "",
        unique: bool = True
    ) -> ConfigUpdateResult:
        """
        Add a value to a list in the YAML file.
        
        Args:
            file_path: Path to YAML file
            yaml_path: Dot-separated path to the list
            value: Value to add to the list
            reason: Explanation for the change
            unique: Only add if value doesn't already exist
            
        Returns:
            ConfigUpdateResult with operation details
            
        Examples:
            >>> editor.add_to_list("config.yaml", "patches", "static_patches/new_patch.yaml", "Add new patch")
        """
        full_path = self.config_base_path / file_path
        
        try:
            # Load existing config
            if full_path.exists():
                with open(full_path, 'r') as f:
                    config = yaml.safe_load(f) or {}
            else:
                return ConfigUpdateResult(
                    success=False,
                    message=f"Config file not found: {full_path}",
                    file_path=str(full_path),
                    changes={}
                )
            
            # Navigate to the target list
            path_parts = yaml_path.split('.')
            target = config
            
            for part in path_parts[:-1]:
                if part not in target:
                    target[part] = {}
                target = target[part]
            
            # Ensure target is a list
            list_key = path_parts[-1]
            if list_key not in target:
                target[list_key] = []
            elif not isinstance(target[list_key], list):
                return ConfigUpdateResult(
                    success=False,
                    message=f"{yaml_path} is not a list",
                    file_path=str(full_path),
                    changes={}
                )
            
            # Add value to list
            if unique and value in target[list_key]:
                return ConfigUpdateResult(
                    success=True,
                    message=f"Value already exists in {yaml_path}, skipped. Reason: {reason}",
                    file_path=str(full_path),
                    changes={"path": yaml_path, "action": "skipped", "value": value}
                )
            
            target[list_key].append(value)
            
            # Write back to file
            with open(full_path, 'w') as f:
                yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
            
            return ConfigUpdateResult(
                success=True,
                message=f"Added value to {yaml_path} in {file_path}. Reason: {reason}",
                file_path=str(full_path),
                changes={
                    "path": yaml_path,
                    "action": "added",
                    "value": value,
                    "reason": reason
                }
            )
            
        except Exception as e:
            return ConfigUpdateResult(
                success=False,
                message=f"Failed to add to list {yaml_path}: {str(e)}",
                file_path=str(full_path),
                changes={}
            )
    
    def create_hyperfile(
        self,
        file_path: str,
        hyperfile_path: str,
        content: str,
        reason: str = ""
    ) -> ConfigUpdateResult:
        """
        Create a hyperfile entry in the config.
        
        Hyperfiles are virtual files that the firmware expects but don't exist.
        
        Args:
            file_path: Path to config YAML file
            hyperfile_path: Path of the hyperfile (e.g., "/proc/self/environ")
            content: Content of the hyperfile
            reason: Explanation for creating this hyperfile
            
        Returns:
            ConfigUpdateResult with operation details
        """
        # For now, hyperfiles are stored under the "pseudofiles" section
        # This adds an entry to pseudofiles mapping
        return self.update_value(
            file_path=file_path,
            yaml_path=f"pseudofiles.{hyperfile_path.replace('/', '.')}",
            value=content,
            reason=f"Create hyperfile {hyperfile_path}: {reason}"
        )
    
    def enable_patch(
        self,
        file_path: str,
        patch_name: str,
        reason: str = ""
    ) -> ConfigUpdateResult:
        """
        Enable a patch by adding it to the patches list.
        
        Args:
            file_path: Path to config YAML file
            patch_name: Name of the patch file (e.g., "static_patches/new_patch.yaml")
            reason: Explanation for enabling this patch
            
        Returns:
            ConfigUpdateResult with operation details
        """
        return self.add_to_list(
            file_path=file_path,
            yaml_path="patches",
            value=patch_name,
            reason=f"Enable patch: {reason}",
            unique=True
        )
    
    def update_core_setting(
        self,
        file_path: str,
        setting_name: str,
        value: Any,
        reason: str = ""
    ) -> ConfigUpdateResult:
        """
        Update a core configuration setting.
        
        Args:
            file_path: Path to config YAML file
            setting_name: Name of the core setting (e.g., "root_shell", "network")
            value: New value for the setting
            reason: Explanation for the change
            
        Returns:
            ConfigUpdateResult with operation details
        """
        return self.update_value(
            file_path=file_path,
            yaml_path=f"core.{setting_name}",
            value=value,
            reason=f"Update core.{setting_name}: {reason}"
        )
    
    def get_value(self, file_path: str, yaml_path: str) -> Optional[Any]:
        """
        Retrieve a value from the YAML file.
        
        Args:
            file_path: Path to YAML file
            yaml_path: Dot-separated path to the value
            
        Returns:
            The value at the specified path, or None if not found
        """
        full_path = self.config_base_path / file_path
        
        try:
            if not full_path.exists():
                return None
            
            with open(full_path, 'r') as f:
                config = yaml.safe_load(f) or {}
            
            # Navigate to the value
            path_parts = yaml_path.split('.')
            target = config
            
            for part in path_parts:
                if isinstance(target, dict) and part in target:
                    target = target[part]
                else:
                    return None
            
            return target
            
        except Exception:
            return None


class ConfigToolRegistry:
    """
    Registry of available configuration tools.
    
    Maps tool names from the plan to actual tool implementations.
    """
    
    def __init__(self, project_path: Path):
        """
        Initialize the tool registry.
        
        Args:
            project_path: Path to the Penguin project directory
        """
        self.project_path = project_path
        self.yaml_editor = YAMLConfigEditor(config_base_path=project_path)
        
        # Map tool names to methods
        self.tools = {
            "yaml_editor": self._handle_yaml_editor,
            "patch_manager": self._handle_patch_manager,
            "hyperfile_builder": self._handle_hyperfile_builder,
            "core_config": self._handle_core_config,
        }
    
    def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> ConfigUpdateResult:
        """
        Execute a tool with the given parameters.
        
        Args:
            tool_name: Name of the tool to execute
            params: Parameters for the tool
            
        Returns:
            ConfigUpdateResult with operation details
        """
        if tool_name not in self.tools:
            return ConfigUpdateResult(
                success=False,
                message=f"Unknown tool: {tool_name}",
                file_path="",
                changes={}
            )
        
        try:
            return self.tools[tool_name](params)
        except Exception as e:
            return ConfigUpdateResult(
                success=False,
                message=f"Tool execution failed: {str(e)}",
                file_path="",
                changes={}
            )
    
    def _handle_yaml_editor(self, params: Dict[str, Any]) -> ConfigUpdateResult:
        """Handle generic YAML editing operations."""
        action = params.get("action", "update")
        file_path = params.get("file", "config.yaml")
        path = params.get("path", "")
        value = params.get("value")
        reason = params.get("reason", "")
        
        if action == "update" or action == "update_config":
            return self.yaml_editor.update_value(file_path, path, value, reason)
        elif action == "add_to_list":
            return self.yaml_editor.add_to_list(file_path, path, value, reason)
        else:
            return ConfigUpdateResult(
                success=False,
                message=f"Unknown YAML editor action: {action}",
                file_path=file_path,
                changes={}
            )
    
    def _handle_patch_manager(self, params: Dict[str, Any]) -> ConfigUpdateResult:
        """Handle patch management operations."""
        file_path = params.get("file", "config.yaml")
        patch_name = params.get("patch", "")
        reason = params.get("reason", "")
        
        return self.yaml_editor.enable_patch(file_path, patch_name, reason)
    
    def _handle_hyperfile_builder(self, params: Dict[str, Any]) -> ConfigUpdateResult:
        """Handle hyperfile creation."""
        file_path = params.get("file", "config.yaml")
        hyperfile_path = params.get("hyperfile_path", "")
        content = params.get("content", "")
        reason = params.get("reason", "")
        
        return self.yaml_editor.create_hyperfile(file_path, hyperfile_path, content, reason)
    
    def _handle_core_config(self, params: Dict[str, Any]) -> ConfigUpdateResult:
        """Handle core configuration updates."""
        file_path = params.get("file", "config.yaml")
        setting = params.get("setting", "")
        value = params.get("value")
        reason = params.get("reason", "")
        
        return self.yaml_editor.update_core_setting(file_path, setting, value, reason)

