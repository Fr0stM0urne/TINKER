#!/usr/bin/env python3
"""
Main entry point for TINKER firmware rehosting system.
"""

import argparse
import configparser
import sys
from pathlib import Path

# Add current directory to path for module imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.rehosting.workflow import rehost_firmware
from src.settings import set_verbose


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="tinker",
        description="TINKER - LLM-guided firmware rehosting system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic firmware rehosting
  python -m src.main firmware.bin
  
  # Use custom config
  python -m src.main firmware.bin --config custom.ini
  
  # Specify output path for updated config
  python -m src.main firmware.bin --output updated_config.yaml
  
  # Verbose mode
  python -m src.main firmware.bin --verbose
        """
    )
    
    parser.add_argument(
        "firmware_path",
        nargs="?",
        default="",
        help="Path to firmware binary to rehost (required for rehosting, optional for help)"
    )
    
    parser.add_argument(
        "-c", "--config",
        default="config.ini",
        help="Path to configuration file (default: config.ini)"
    )
    
    parser.add_argument(
        "-o", "--output",
        help="Path for updated Penguin configuration (optional)"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    parser.add_argument(
        "--model",
        help="Override LLM model from config"
    )
    
    return parser.parse_args()


def load_config(config_path: str) -> configparser.ConfigParser:
    """Load and validate configuration file."""
    config = configparser.ConfigParser()
    
    if not Path(config_path).exists():
        print(f"✗ Error: Config file not found: {config_path}")
        sys.exit(1)
    
    config.read(config_path)
    
    # Validate required sections
    required_sections = ['Penguin', 'Ollama']
    for section in required_sections:
        if not config.has_section(section):
            print(f"✗ Error: Missing required config section: [{section}]")
            sys.exit(1)
    
    return config


def main():
    """Main entry point for TINKER."""
    args = parse_args()
    
    # Banner
    print("=" * 70)
    print("🔧 TINKER - LLM-Guided Firmware Rehosting System")
    print("=" * 70)
    print()
    

    # Validate firmware path exists
    if args.firmware_path == "" or not Path(args.firmware_path).exists():
        print(f"✗ Error: Firmware file not found: {args.firmware_path}")
        print('Use default firmware path: /home/renze/workplace/TINKER/resources/firmware/stride.rootfs.tar.gz')
                # get the firmware path from the config
        #debugging    
        args.firmware_path = "/home/renze/workplace/TINKER/resources/firmware/stride.rootfs.tar.gz"

        
    # Load configuration
    config = load_config(args.config)
    
    # Set verbose mode globally (CLI flag overrides config)
    verbose_enabled = args.verbose
    if not verbose_enabled and config.has_option('General', 'verbose'):
        verbose_enabled = config.getboolean('General', 'verbose', fallback=False)
    set_verbose(verbose_enabled)
    
    if verbose_enabled:
        print("🔊 Verbose mode: ENABLED")
        print()
    
    # Override model if specified
    if args.model:
        config.set('Ollama', 'model', args.model)
        print(f"📝 Using model override: {args.model}")
        print()
    
    # Run workflow
    result = rehost_firmware(
        config=config,
        firmware_path=args.firmware_path,
        output_config_path=args.output,
        verbose=verbose_enabled
    )
    
    # Report results
    print()
    print("=" * 70)
    if result["success"]:
        print("✅ WORKFLOW COMPLETED SUCCESSFULLY")
        print("=" * 70)
        print()
        
        if result.get("penguin_project"):
            print(f"  📁 Project: {result['penguin_project']}")
        
        if result.get("config_update_plan"):
            plan = result["config_update_plan"]
            print(f"  📋 Plan ID: {plan.id}")
            print(f"  🎯 Objectives: {len(plan.objectives)}")
            print(f"  📍 Options: {len(plan.options)}")
        
        if result.get("updated_config_path"):
            print(f"  💾 Updated config: {result['updated_config_path']}")
        
        print()
        sys.exit(0)
    else:
        print("❌ WORKFLOW FAILED")
        print("=" * 70)
        print()
        print("Errors:")
        for error in result.get("errors", []):
            print(f"  • {error}")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()

