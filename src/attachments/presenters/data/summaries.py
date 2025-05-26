"""Data summary and preview presenters."""

from ...core import Attachment, presenter


@presenter
def summary(att: Attachment) -> Attachment:
    """Fallback summary presenter."""
    return att


@presenter
def summary(att: Attachment, df: 'pandas.DataFrame') -> Attachment:
    """Generate summary statistics for DataFrame."""
    try:
        # Generate summary statistics
        summary_text = "## DataFrame Summary\n\n"
        summary_text += f"**Shape**: {df.shape[0]} rows × {df.shape[1]} columns\n\n"
        
        # Column info
        summary_text += "**Columns**:\n"
        for col in df.columns:
            dtype = str(df[col].dtype)
            non_null = df[col].count()
            total = len(df)
            summary_text += f"- `{col}` ({dtype}): {non_null}/{total} non-null\n"
        
        summary_text += "\n"
        
        # Basic statistics for numeric columns
        numeric_cols = df.select_dtypes(include=['number']).columns
        if len(numeric_cols) > 0:
            summary_text += "**Numeric Statistics**:\n"
            desc = df[numeric_cols].describe()
            summary_text += desc.to_string()
            summary_text += "\n\n"
        
        # Value counts for categorical columns (first few)
        categorical_cols = df.select_dtypes(include=['object', 'category']).columns
        if len(categorical_cols) > 0:
            summary_text += "**Categorical Columns**:\n"
            for col in categorical_cols[:3]:  # Limit to first 3 categorical columns
                value_counts = df[col].value_counts().head(5)
                summary_text += f"\n`{col}` (top 5 values):\n"
                for value, count in value_counts.items():
                    summary_text += f"- {value}: {count}\n"
        
        att.text += summary_text
        return att
        
    except Exception as e:
        att.metadata['summary_error'] = f"Error generating summary: {e}"
        return att


@presenter
def head(att: Attachment) -> Attachment:
    """Fallback head presenter."""
    return att


@presenter
def head(att: Attachment, df: 'pandas.DataFrame') -> Attachment:
    """Show first few rows of DataFrame."""
    try:
        # Get number of rows to show (default 5)
        n_rows = int(att.commands.get('head', 5))
        
        # Generate head display
        head_text = f"## DataFrame Head (first {n_rows} rows)\n\n"
        head_df = df.head(n_rows)
        head_text += head_df.to_string(index=True)
        head_text += "\n\n"
        
        att.text += head_text
        return att
        
    except Exception as e:
        att.metadata['head_error'] = f"Error generating head: {e}"
        return att 