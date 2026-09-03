#!/usr/bin/env python3
"""
Agent System (Enterprise++ v3.5) - Configuration Validation Script
CI/CD pipeline validation for YAML configuration files.

Validates:
- configs/system.yaml against SystemConfig schema
- configs/prompts/v3.5_core.yaml against PromptConfig schema
- configs/prompts/v2_fallback.yaml against PromptConfig schema

Usage: python3 validate_configs.py [--verbose]

Exit codes:
  0 - All configurations valid
  1 - Validation error (schema or parsing failure)
  2 - File not found or script error
"""

import sys
import os
import argparse
from pathlib import Path

import yaml
from pydantic import ValidationError

# Add project root to path
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from configs.schemas import SystemConfig, PromptConfig


def load_yaml_file(filepath: Path) -> dict:
    """Load and parse YAML file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"[ERROR] YAML parsing error in {filepath}: {e}")
        raise
    except FileNotFoundError:
        print(f"[ERROR] File not found: {filepath}")
        raise
    except Exception as e:
        print(f"[ERROR] Failed to load {filepath}: {e}")
        raise


def validate_system_config(filepath: Path) -> bool:
    """Validate system.yaml against SystemConfig schema."""
    print(f"Validating {filepath}...")
    try:
        data = load_yaml_file(filepath)
        config = SystemConfig(**data)
        print(f"  [PASS] SystemConfig validated successfully")
        print(f"  - Schema version: {config.schema_version}")
        print(f"  - Environment: {config.environment.value}")
        print(f"  - etcd endpoints: {len(config.etcd.endpoints)}")
        print(f"  - NATS endpoints: {len(config.nats.endpoints)}")
        print(f"  - GPU device: {config.gpu.device_id}")
        print(f"  - MPS allocation: vLLM={config.gpu.mps.allocation.vllm_percent}%, "
              f"Roboflow={config.gpu.mps.allocation.roboflow_percent}%, "
              f"Tools={config.gpu.mps.allocation.tools_percent}%")
        return True
    except ValidationError as e:
        print(f"  [FAIL] SystemConfig validation error:")
        for error in e.errors():
            print(f"    - {error['loc']}: {error['msg']}")
        return False
    except Exception as e:
        print(f"  [FAIL] Unexpected error: {e}")
        return False


def validate_prompt_config(filepath: Path, name: str) -> bool:
    """Validate prompt YAML against PromptConfig schema."""
    print(f"Validating {name} ({filepath})...")
    try:
        data = load_yaml_file(filepath)
        config = PromptConfig(**data)
        print(f"  [PASS] PromptConfig validated successfully")
        print(f"  - Version: {config.version}")
        print(f"  - Name: {config.name}")
        print(f"  - Context max_tokens: {config.context.max_tokens}")
        return True
    except ValidationError as e:
        print(f"  [FAIL] PromptConfig validation error:")
        for error in e.errors():
            print(f"    - {error['loc']}: {error['msg']}")
        return False
    except Exception as e:
        print(f"  [FAIL] Unexpected error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Validate Agent System v3.5 configuration files"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    args = parser.parse_args()

    configs_dir = PROJECT_ROOT / "configs"
    prompts_dir = configs_dir / "prompts"

    configs_to_check = [
        (configs_dir / "system.yaml", SystemConfig),
        (prompts_dir / "v3.5_core.yaml", PromptConfig),
        (prompts_dir / "v2_fallback.yaml", PromptConfig),
    ]

    print("=" * 60)
    print("Agent System v3.5 - Configuration Validation")
    print("=" * 60)
    print()

    all_valid = True

    for filepath, schema_class in configs_to_check:
        if not filepath.exists():
            print(f"[ERROR] File not found: {filepath}")
            all_valid = False
            continue

        if schema_class == SystemConfig:
            valid = validate_system_config(filepath)
        else:
            valid = validate_prompt_config(filepath, filepath.stem)

        if not valid:
            all_valid = False
        print()

    print("=" * 60)
    if all_valid:
        print("[SUCCESS] All configurations validated successfully")
        print("=" * 60)
        return 0
    else:
        print("[FAILURE] Configuration validation failed")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"[ERROR] Script error: {e}")
        sys.exit(2)
