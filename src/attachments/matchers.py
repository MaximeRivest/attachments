from .core import Attachment
import re
import os
import glob

# --- MATCHERS ---

def url_match(att: 'Attachment') -> bool:
    """Check if the attachment path looks like a URL."""
    url_pattern = r'^https?://'
    return bool(re.match(url_pattern, att.path))

def webpage_match(att: 'Attachment') -> bool:
    """Check if the attachment is a webpage URL (not a downloadable file)."""
    if not att.path.startswith(('http://', 'https://')):
        return False
    
    # Exclude URLs that end with file extensions (those go to url_to_file)
    file_extensions = ['.pdf', '.pptx', '.ppt', '.docx', '.doc', '.xlsx', '.xls', 
                      '.csv', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.zip']
    
    return not any(att.path.lower().endswith(ext) for ext in file_extensions)

def csv_match(att: 'Attachment') -> bool:
    return att.path.endswith('.csv')

def pdf_match(att: 'Attachment') -> bool:
    return att.path.endswith('.pdf')

def pptx_match(att: 'Attachment') -> bool:
    return att.path.endswith(('.pptx', '.ppt'))

def docx_match(att: 'Attachment') -> bool:
    return att.path.endswith(('.docx', '.doc'))

def excel_match(att: 'Attachment') -> bool:
    return att.path.endswith(('.xlsx', '.xls'))

def image_match(att: 'Attachment') -> bool:
    return att.path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.heif'))

def text_match(att: 'Attachment') -> bool:
    return att.path.endswith(('.txt', '.md', '.log', '.json', '.py'))

def zip_match(att: 'Attachment') -> bool:
    """Check if the attachment path is a ZIP file."""
    return att.path.lower().endswith('.zip')

def git_repo_match(att: 'Attachment') -> bool:
    """Check if path is a Git repository."""
    # Convert to absolute path to handle relative paths like "."
    abs_path = os.path.abspath(att.path)
    
    if not os.path.isdir(abs_path):
        return False
    
    # Check for .git directory
    git_dir = os.path.join(abs_path, '.git')
    return os.path.exists(git_dir)

def directory_match(att: 'Attachment') -> bool:
    """Check if path is a directory (for recursive file collection)."""
    abs_path = os.path.abspath(att.path)
    return os.path.isdir(abs_path)

def glob_pattern_match(att: 'Attachment') -> bool:
    """Check if path contains glob patterns (* or ? or [])."""
    return any(char in att.path for char in ['*', '?', '[', ']'])

def directory_or_glob_match(att: 'Attachment') -> bool:
    """Check if path is a directory or contains glob patterns."""
    return directory_match(att) or glob_pattern_match(att)

