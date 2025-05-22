"""API adapters for different LLM services."""

# Import all adapters to auto-register them
from . import openai

__all__ = ['openai'] 