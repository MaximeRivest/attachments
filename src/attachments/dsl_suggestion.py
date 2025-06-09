"""
DSL Command Suggestion
======================

This module provides logic for suggesting corrections for mistyped
DSL (Domain-Specific Language) commands. It uses the Levenshtein distance
algorithm to find the closest match from a list of valid commands.
"""

from typing import Optional, Iterable

def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calculates the Levenshtein distance between two strings.
    This measures the number of edits (insertions, deletions, or
    substitutions) required to change one word into the other.
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]

def find_closest_command(mistyped_command: str, valid_commands: Iterable[str], max_distance: int = 2) -> Optional[str]:
    """
    Finds the closest valid command to a mistyped one.

    Args:
        mistyped_command: The command the user provided.
        valid_commands: An iterable of all valid DSL commands.
        max_distance: The maximum Levenshtein distance to consider a match.
                      A lower number means a stricter match. Defaults to 2.

    Returns:
        The closest command name, or None if no close match is found.
    """
    best_match: Optional[str] = None
    min_distance = max_distance + 1 

    for valid_cmd in valid_commands:
        distance = levenshtein_distance(mistyped_command, valid_cmd)
        if distance < min_distance:
            min_distance = distance
            best_match = valid_cmd

    if min_distance <= max_distance:
        return best_match
    
    return None 

VALID_FORMATS = ['plain', 'text', 'txt', 'markdown', 'md', 'html', 'code', 'xml', 'csv', 'structured']

def suggest_format_command(format_value: str) -> Optional[str]:
    """
    Finds the closest valid format command if the provided one is invalid.
    
    Args:
        format_value: The format value provided by the user.
        
    Returns:
        The closest valid format, or None if the input is already valid or no close match is found.
    """
    if format_value in VALID_FORMATS:
        return None # It's already valid

    return find_closest_command(format_value, VALID_FORMATS) 