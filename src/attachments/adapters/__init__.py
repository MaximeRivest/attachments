"""API adapters for different LLM services."""

# Import all adapters to auto-register them
from . import openai
from . import claude
from . import dspy
from . import langchain

__all__ = ['openai', 'claude', 'dspy', 'langchain'] 