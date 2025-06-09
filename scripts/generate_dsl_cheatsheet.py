#!/usr/bin/env python
"""
This script programmatically generates the DSL cheatsheet for the documentation.
It introspects the library's source code to find all DSL commands and
writes them to a Markdown file that can be included in the main documentation.

This script is automatically run during:
- Local MyST builds (via myst build)
- GitHub Pages deployment (via .github/workflows/deploy-docs.yml)
- Manual build script (scripts/build_and_verify_docs.sh)

The generated file is excluded from version control as it's auto-generated.
"""
import os
from attachments.dsl_info import get_dsl_info

def clean_for_table(text):
    """Clean text for safe inclusion in markdown table."""
    if text is None:
        return "—"
    
    # Convert to string and handle special cases
    text = str(text)
    
    # Replace problematic characters
    text = text.replace('|', '&#124;')  # Escape pipe characters
    text = text.replace('\n', ' ')      # Replace newlines with spaces
    text = text.replace('\r', ' ')      # Replace carriage returns
    text = text.strip()                 # Remove leading/trailing whitespace
    
    # Handle empty strings
    if not text:
        return "—"
    
    return text

def format_value(value):
    """Format a value for display in the table."""
    if value is None:
        return "—"
    elif isinstance(value, str):
        # Handle multi-line strings and special characters
        clean_value = clean_for_table(value)
        if not clean_value or clean_value == "—":
            return "—"
        # For very short strings that are just symbols, display them raw
        if len(clean_value) <= 10 and all(c in '=-_~*+#@!$%^&()<>[]{}|\\/:;.,' for c in clean_value.replace(' ', '')):
            # Show separator characters in a more readable way
            if clean_value.strip() == "---":
                return "`---`"
            elif clean_value.strip() == "":
                return "—"
            else:
                return f"`{clean_value}`"
        return f"`{clean_value}`"
    elif isinstance(value, bool):
        return f"`{str(value).lower()}`"
    else:
        return f"`{clean_for_table(str(value))}`"

def format_allowable_values(values):
    """Format allowable values list for display."""
    if not values:
        return "—"
    
    # Clean each value
    clean_values = []
    for v in values:
        clean_v = clean_for_table(str(v))
        if clean_v != "—":
            clean_values.append(clean_v)
    
    if not clean_values:
        return "—"
    
    if len(clean_values) <= 3:
        return ", ".join(f"`{v}`" for v in clean_values)
    else:
        # Show first 3 and count
        shown = ", ".join(f"`{v}`" for v in clean_values[:3])
        return f"{shown}, ... ({len(clean_values)} total)"

def generate_cheatsheet_content():
    """Generates the Markdown table content for the DSL cheatsheet."""
    dsl_info = get_dsl_info()
    
    lines = []
    lines.append("| Command | Type | Default | Allowable Values | Used In |")
    lines.append("|---|---|---|---|---|")
    
    for command in sorted(dsl_info.keys()):
        contexts = dsl_info[command]
        
        # Get information from the first context (they should be consistent)
        first_context = contexts[0]
        
        # Extract enhanced information
        inferred_type = first_context.get('inferred_type', 'unknown')
        default_value = first_context.get('default_value')
        allowable_values = first_context.get('allowable_values', [])
        description = first_context.get('description', '')
        
        # Format the "Used In" column
        used_in_parts = []
        for ctx in contexts:
            used_in_parts.append(f"`{clean_for_table(ctx['used_in'])}`")
        used_in_str = "<br>".join(used_in_parts)
        
        # Format table cells
        type_cell = f"`{clean_for_table(inferred_type)}`" if inferred_type != 'unknown' else "—"
        default_cell = format_value(default_value)
        allowable_cell = format_allowable_values(allowable_values)
        
        # Format command cell with optional description
        command_cell = f"`{clean_for_table(command)}`"
        if description and len(description.strip()) > 0:
            # Clean up description for better display
            clean_desc = clean_for_table(description)
            # Truncate very long descriptions
            if len(clean_desc) > 40:
                clean_desc = clean_desc[:37] + "..."
            # Only add description if it's meaningful and different from command
            if clean_desc and clean_desc != "—" and clean_desc.lower() != command.lower():
                command_cell = f"`{clean_for_table(command)}`<br><small><em>{clean_desc}</em></small>"
        
        # Build the table row
        row = f"| {command_cell} | {type_cell} | {default_cell} | {allowable_cell} | {used_in_str} |"
        lines.append(row)
        
    return "\n".join(lines)

def main():
    """Main function to generate and write the cheatsheet."""
    content = generate_cheatsheet_content()
    
    # The output path should be relative to the docs directory
    output_path = os.path.join(os.path.dirname(__file__), '..', 'docs', '_generated_dsl_cheatsheet.md')
    
    with open(output_path, 'w') as f:
        f.write(content)
        
    print(f"✅ DSL cheatsheet successfully generated at {output_path}")

if __name__ == "__main__":
    main() 