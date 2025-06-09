import sys
from typing import TextIO

class Config:
    """Global configuration for the attachments library."""
    def __init__(self):
        self.verbose: bool = True
        self.log_stream: TextIO = sys.stderr
        self.indent_level: int = 0
        self.indent_char: str = "  "

config = Config()

def set_verbose(verbose: bool = True, stream: TextIO = sys.stderr):
    """
    Set the verbosity for the library. Logging is ON by default.

    Args:
        verbose: Set to True to enable (default) or False to disable verbose logging.
        stream: The stream to write logs to (default: sys.stderr).
    """
    config.verbose = verbose
    config.log_stream = stream

def indent():
    """Increase the indentation level for logs."""
    config.indent_level += 1

def dedent():
    """Decrease the indentation level for logs."""
    config.indent_level = max(0, config.indent_level - 1)

def verbose_log(message: str):
    """
    Log a message if verbosity is enabled.
    """
    if config.verbose:
        prefix = config.indent_char * config.indent_level
        print(f"[Attachments] {prefix}{message}", file=config.log_stream) 