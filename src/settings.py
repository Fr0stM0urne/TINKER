"""
Global settings and configuration for TINKER.

This module provides a centralized place to store runtime settings
that need to be accessed from anywhere in the project.
"""

from typing import Optional
import threading


class Settings:
    """Global settings singleton."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(Settings, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._verbose = False
        self._initialized = True
    
    @property
    def verbose(self) -> bool:
        """Get verbose mode flag."""
        return self._verbose
    
    @verbose.setter
    def verbose(self, value: bool):
        """Set verbose mode flag."""
        self._verbose = bool(value)
        if self._verbose:
            print("[Settings] Verbose mode: ENABLED")


# Global settings instance
_settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance."""
    return _settings


def set_verbose(enabled: bool):
    """Set verbose mode globally."""
    _settings.verbose = enabled


def is_verbose() -> bool:
    """Check if verbose mode is enabled."""
    return _settings.verbose


def verbose_print(message: str, prefix: str = ""):
    """Print message only if verbose mode is enabled.
    
    All messages are automatically prefixed with [VERBOSE].
    An additional prefix can be provided for component identification.
    Multi-line messages will have the prefix on every line.
    
    Example:
        verbose_print("Context built", prefix="[PLANNER]")
        # Output: [VERBOSE] [PLANNER] Context built
        
        verbose_print("Line 1\\nLine 2", prefix="[PLANNER]")
        # Output:
        # [VERBOSE] [PLANNER] Line 1
        # [VERBOSE] [PLANNER] Line 2
    """
    if is_verbose():
        # Split message into lines and add prefix to each
        lines = message.splitlines()
        
        if prefix:
            full_prefix = f"[VERBOSE] {prefix}"
        else:
            full_prefix = "[VERBOSE]"
        
        for line in lines:
            print(f"{full_prefix} {line}")

