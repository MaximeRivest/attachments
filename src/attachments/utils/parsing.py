"""Path expression and command parsing utilities."""


def parse_commands(expr: str) -> dict:
    """Parse command string like 'key: value, key2: value2' into dict."""
    commands = {}
    if not expr.strip():
        return commands
    
    for part in expr.split(','):
        if ':' in part:
            key, value = part.split(':', 1)
            commands[key.strip()] = value.strip()
    return commands


def parse_path_expression(path: str) -> tuple[str, dict]:
    """Extract path and commands from 'path[key: value, ...]'."""
    if '[' in path and path.endswith(']'):
        actual_path, expr = path.split('[', 1)
        commands = parse_commands(expr[:-1])
        return actual_path, commands
    return path, {} 