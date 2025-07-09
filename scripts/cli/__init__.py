"""
CLI package for the Attachments tool.

This package exposes the command‐line entry point for converting files
into LLM-ready text via the Attachments DSL.
"""

from .attachments_cli import main

__all__ = ["main"]
