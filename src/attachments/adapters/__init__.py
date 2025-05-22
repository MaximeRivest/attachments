"""API adapters for different LLM services."""

# Import all adapters to auto-register them
from . import openai
from . import claude

__all__ = ['openai', 'claude'] 