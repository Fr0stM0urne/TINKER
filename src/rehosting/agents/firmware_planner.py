"""
Extended Planner agent specialized for firmware rehosting configuration.

This extends the base PlannerAgent with firmware-specific knowledge and prompts.
"""

from typing import Dict, Any, List
from pydantic import BaseModel, Field
from src.llms.agents import PlannerAgent
from src.llms.schemas import State


class FirmwareConfigPlan(BaseModel):
    """Lightweight plan schema for firmware configuration updates."""

    id: str = Field(description="Unique identifier for this plan")
    objectives: List[str] = Field(description="High-level objectives to achieve")
    options: List[Dict[str, Any]] = Field(
        description="List of possible configuration update options for evaluator/engineer to prioritize"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": "fw_config_plan_001",
                "objectives": [
                    "Fix missing environment variables",
                    "Model failed peripheral devices"
                ],
                "options": [
                    {
                        "option_id": "1",
                        "description": "Add missing PATH environment variable",
                        "action": "update_config",
                        "tool": "yaml_editor",
                        "params": {
                            "file": "config.yaml",
                            "path": "hyperfiles./proc/self/environ",
                            "value": "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
                            "reason": "env_missing.yaml indicates PATH is required"
                        },
                        "priority": "high",
                        "impact": "critical"
                    },
                    {
                        "option_id": "2",
                        "description": "Model UART0 peripheral device",
                        "action": "add_hyperfile",
                        "tool": "peripheral_modeler",
                        "params": {
                            "device": "UART0",
                            "address": "0x40001000"
                        },
                        "priority": "medium",
                        "impact": "moderate"
                    }
                ]
            }
        }


class FirmwarePlannerAgent(PlannerAgent):
    """
    Planner agent specialized for firmware rehosting configuration updates.
    
    This agent understands:
    - Penguin configuration format (YAML)
    - Common firmware rehosting issues (missing env vars, failed peripherals, etc.)
    - Architecture-specific requirements (ARM, MIPS, x86)
    - Configuration sections: target, patches, hyperfiles, network
    """
    
    # Extended system prompt with firmware-specific knowledge
    SYSTEM_PROMPT = """You are a firmware rehosting planning agent specialized in Penguin configuration optimization.

Your role is to analyze firmware rehosting results and generate configuration update plans to improve execution success.

## Penguin Configuration Structure (YAML)

1. **target**: Architecture and entry point settings
   - arch: ARM, MIPS, x86, etc.
   - entry_point: Firmware entry address
   - memory_regions: Memory mapping

2. **patches**: Code modifications
   - root_shell: Enable shell access
   - auto_explore: Automatic exploration
   - lib_inject: Library injection
   - static.shims.*: Static shimming

3. **hyperfiles**: File system mocking
   - Model files the firmware expects
   - Provide missing /proc, /sys entries

4. **network**: Network configuration
   - Interfaces, IP addresses
   - Port bindings

## Common Issues and Solutions

### Missing Environment Variables
- Issue: env_missing.yaml shows missing vars
- Solution: Add to hyperfiles or patches to inject

### Peripheral Failures  
- Issue: pseudofiles_failures.yaml shows unmodeled devices
- Solution: Add hyperfile models for the devices

### Network Binding Failures
- Issue: netbinds.csv shows failed bindings
- Solution: Update network config, add port mappings

### Execution Crashes
- Issue: Console shows segfaults, crashes
- Solution: 
  * Check entry point correctness
  * Add memory region mappings
  * Enable relevant patches (root_shell, lib_inject)

## Your Task

Given rehosting results, create a plan with:
1. Clear objectives (what needs to be fixed)
2. List of configuration update options for prioritization
3. Specific YAML paths and values to modify
4. Each option should include priority and impact assessment

Your output MUST be valid JSON matching this schema:

```json
{
  "id": "fw_config_plan_001",
  "objectives": [
    "Fix missing environment variables",
    "Model failed peripheral devices"
  ],
  "options": [
    {
      "option_id": "1",
      "description": "Add missing PATH environment variable",
      "action": "update_config",
      "tool": "yaml_editor",
      "params": {
        "file": "config.yaml",
        "path": "hyperfiles./proc/self/environ",
        "value": "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
        "reason": "env_missing.yaml indicates PATH is required"
      },
      "priority": "high",
      "impact": "critical"
    }
  ]
}
```

## Option Prioritization

Assign priority levels to help evaluator/engineer prioritize:
- **critical**: Must-fix issues (crashes, missing core dependencies)
- **high**: Important fixes (missing env vars, failed peripherals)
- **medium**: Nice-to-have improvements (network config, optional peripherals)
- **low**: Optimization or minor enhancements

Focus on generating actionable configuration options with clear priorities."""

    def __init__(self, model: str = "llama3.3:latest"):
        """Initialize firmware-specific planner."""
        super().__init__(model, plan_schema=FirmwareConfigPlan)
        
    def plan(self, state: State) -> FirmwareConfigPlan:
        """
        Generate firmware configuration update plan.
        
        This extends the base planner with firmware-specific context building.
        """
        # TODO: Add firmware-specific context enhancement
        # - Parse Penguin results structure
        # - Extract specific errors/failures
        # - Identify configuration gaps
        # - Prioritize issues by impact
        
        # For now, use base planner logic
        return super().plan(state)
    
    def _build_context(self, state: State) -> str:
        """
        Build enhanced context with firmware-specific analysis.
        
        Extensions to add:
        1. Parse env_missing.yaml and list missing vars
        2. Parse pseudofiles_failures.yaml and list failed peripherals  
        3. Extract error patterns from console.log
        4. Identify network binding issues from netbinds.csv
        5. Suggest architecture-specific fixes
        """
        # Get base context
        base_context = super()._build_context(state)
        
        # TODO: Add firmware-specific context parsing
        # Example structure:
        """
        firmware_context = []
        
        # Parse RAG context for Penguin results
        for ctx in state.rag_context:
            if "env_missing_count:" in ctx:
                # Extract and analyze missing env vars
                firmware_context.append("Missing environment variables detected")
                firmware_context.append("Action: Add to hyperfiles or inject via patches")
                
            if "pseudofile_failures:" in ctx:
                # Extract peripheral failures
                firmware_context.append("Peripheral modeling failures detected")
                firmware_context.append("Action: Create hyperfile models for devices")
                
            if "Console errors:" in ctx:
                # Extract crash patterns
                firmware_context.append("Execution errors detected")
                firmware_context.append("Action: Review entry point and memory mappings")
        
        if firmware_context:
            base_context += "\n\n## Firmware-Specific Analysis:\n"
            base_context += "\n".join(firmware_context)
        """
        
        return base_context
    
    def _build_prompt(self, state: State, context: str) -> str:
        """
        Build planning prompt with firmware configuration focus.
        
        Extensions to add:
        1. Include current Penguin config (if available)
        2. Highlight specific sections that need updates
        3. Provide examples of successful configurations
        4. Add architecture-specific hints
        """
        base_prompt = super()._build_prompt(state, context)
        
        # TODO: Enhance with firmware-specific guidance
        """
        firmware_guidance = '''
        
## Additional Context for Configuration Updates

Current Penguin Configuration Sections to Review:
- target.arch: Verify architecture is correct
- target.entry_point: Check if entry point is valid
- patches: Consider enabling root_shell, auto_explore
- hyperfiles: Add models for missing files/devices
- network: Update bindings for detected services

Prioritize fixes in this order:
1. Critical: Entry point, architecture, memory regions
2. High: Missing environment variables, core peripherals
3. Medium: Network configuration, optional peripherals
4. Low: Performance optimizations, logging
'''
        base_prompt += firmware_guidance
        """
        
        return base_prompt
    
    def _suggest_config_updates(self, results: Dict[str, Any]) -> list:
        """
        Analyze results and suggest specific config updates.
        
        This would be a key method to implement:
        1. Parse all result files
        2. Identify root causes of failures
        3. Map failures to config changes
        4. Generate ordered update steps
        
        Returns:
            List of suggested configuration modifications
        """
        # TODO: Implement intelligent config analysis
        suggestions = []
        
        # Example logic (to be implemented):
        """
        # Check for missing env vars
        if results.get("parsed", {}).get("env_missing.yaml"):
            for var, value in results["parsed"]["env_missing.yaml"].items():
                suggestions.append({
                    "type": "hyperfile",
                    "path": "/proc/self/environ",
                    "action": "append",
                    "value": f"{var}={value}",
                    "priority": "high"
                })
        
        # Check for peripheral failures
        if results.get("parsed", {}).get("pseudofiles_failures.yaml"):
            for device in results["parsed"]["pseudofiles_failures.yaml"]:
                suggestions.append({
                    "type": "hyperfile",
                    "path": device,
                    "action": "create_model",
                    "priority": "medium"
                })
        
        # Check console for crashes
        console = results.get("files", {}).get("console.log", "")
        if "segmentation fault" in console.lower():
            suggestions.append({
                "type": "patch",
                "patch": "lib_inject",
                "action": "enable",
                "priority": "critical"
            })
        """
        
        return suggestions


# Convenience function for workflow integration
def create_firmware_planner(model: str = "llama3.3:latest") -> FirmwarePlannerAgent:
    """Create a firmware-specific planner instance."""
    return FirmwarePlannerAgent(model)

