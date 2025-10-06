"""
Penguin firmware rehosting tool API wrapper.

This module provides a formal interface to interact with the Penguin
firmware rehosting framework, including initialization, execution,
and results collection.

Key features:
- Auto-detection of project paths from penguin init output
- Docker path mapping (/host_projects → config output_dir)
- LLM-optimized result formatting
"""

from .client import PenguinClient
from .operations import penguin_init, penguin_run
from .results import (
    get_penguin_results_dir,
    get_penguin_results,
    get_penguin_errors,
)
from .formatters import format_results_for_llm, format_results_detailed

__all__ = [
    "PenguinClient",
    "penguin_init",
    "penguin_run",
    "get_penguin_results_dir",
    "get_penguin_results",
    "get_penguin_errors",
    "format_results_for_llm",
    "format_results_detailed",
]

