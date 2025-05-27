"""Data summary and preview presenters."""

from ...core import Attachment, presenter


@presenter
def summary(att: Attachment) -> Attachment:
    """Fallback summary presenter for non-DataFrame objects."""
    try:
        summary_text = f"\n## Object Summary\n\n"
        summary_text += f"- **Type**: {type(att._obj).__name__}\n"
        if hasattr(att._obj, '__len__'):
            try:
                summary_text += f"- **Length**: {len(att._obj)}\n"
            except:
                pass
        summary_text += f"- **String representation**: {str(att._obj)[:100]}...\n"
        att.text += summary_text + "\n"
    except Exception as e:
        att.text += f"\n*Error generating summary: {e}*\n\n"
    return att


@presenter
def summary(att: Attachment, df: 'pandas.DataFrame') -> Attachment:
    """Add summary statistics to text."""
    try:
        summary_text = f"\n## Summary Statistics\n\n"
        summary_text += f"- **Rows**: {len(df)}\n"
        summary_text += f"- **Columns**: {len(df.columns)}\n"
        
        # Try to get memory usage (from legacy implementation)
        try:
            memory_usage = df.memory_usage(deep=True).sum()
            summary_text += f"- **Memory Usage**: {memory_usage} bytes\n"
        except:
            summary_text += f"- **Memory Usage**: Not available\n"
        
        # Get numeric columns (from legacy implementation)
        try:
            numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
            summary_text += f"- **Numeric Columns**: {numeric_cols}\n"
        except:
            summary_text += f"- **Numeric Columns**: Not available\n"
        
        att.text += summary_text + "\n"
    except Exception as e:
        att.text += f"\n*Error generating summary: {e}*\n\n"
    
    return att


@presenter
def head(att: Attachment) -> Attachment:
    """Fallback head presenter for non-DataFrame objects."""
    if hasattr(att._obj, 'head'):
        try:
            head_result = att._obj.head()
            att.text += f"\n## Preview\n\n{str(head_result)}\n\n"
        except:
            att.text += f"\n## Preview\n\n{str(att._obj)[:200]}\n\n"
    else:
        att.text += f"\n## Preview\n\n{str(att._obj)[:200]}\n\n"
    return att


@presenter
def head(att: Attachment, df: 'pandas.DataFrame') -> Attachment:
    """Add data preview to text (additive)."""
    try:
        head_text = f"\n## Data Preview\n\n"
        head_text += df.head().to_markdown(index=False)
        att.text += head_text + "\n\n"  # Additive: append to existing text
    except Exception as e:
        att.text += f"\n*Error generating preview: {e}*\n\n"
    
    return att 