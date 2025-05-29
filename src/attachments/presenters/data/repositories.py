"""Repository and directory structure presenters."""

from ...core import Attachment, presenter
import os

@presenter
def structure_and_metadata(att: Attachment, repo_structure: dict) -> Attachment:
    """Present repository/directory with combined structure + metadata information."""
    if repo_structure.get('type') == 'size_warning':
        # Handle size warning case
        # Set att.text directly to avoid additive duplication for warnings
        att.text = "" 
        structure = repo_structure['structure']
        path = repo_structure['path']
        total_size_mb = repo_structure['total_size_mb']
        file_count = repo_structure['file_count']
        size_limit_mb = repo_structure['size_limit_mb']
        stopped_early = repo_structure.get('size_check_stopped_early', False)
        
        att.text += f"# ⚠️ Large Directory: {os.path.basename(path)}\n\n"
        att.text += f"## Size Warning\n\n"
        # Modify the total size display if the check stopped early
        size_display = f"{total_size_mb:.1f} MB"
        if stopped_early:
            size_display = f">{total_size_mb:.1f} MB (stopped early at limit)"

        att.text += f"**Total Size**: {size_display} ({file_count:,} files)\n"
        att.text += f"**Size Limit**: {size_limit_mb} MB\n\n"
        att.text += f"🚨 **This directory is too large to process automatically.**\n\n"
        
        if stopped_early:
            att.text += f"⚡ **Size check stopped early** to prevent memory issues.\n\n" # Already added this part of the message, ensure no duplication
        
        att.text += f"**Options**:\n"
        att.text += f"- Use `[files:false]` or `[mode:structure]` to see directory structure only.\n"
        att.text += f"- Use `[files:true][force:true]` to process all files (if you understand the memory risk).\n"
        att.text += f"- **Filter files with `ignore`**: `[ignore:standard]` (default, recommended for code repos), `[ignore:*.log,*.tmp,build/,dist/]` (custom patterns). This can significantly reduce size by excluding large, unneeded files/folders.\n"
        att.text += f"- **Select specific files with `glob`**: `[glob:*.py,*.md]` (process only Python and Markdown files), `[glob:src/**/*.js]` (process JS files in src and its subdirectories). Use this to pinpoint exact files if the directory is too diverse.\n"
        att.text += f"- **Combine `ignore` and `glob`**: First, `ignore` broad categories, then `glob` for specifics. E.g., `[ignore:standard][glob:src/**/*.py]`\n"
        att.text += f"- Use `[max_files:XX]` to limit the number of files processed (e.g., `[max_files:100]`).\n\n"
        
        # Only show structure if we have it (not stopped early)
        if structure and not stopped_early:
            if repo_structure.get('metadata', {}).get('is_git_repo'):
                att.text += _format_structure_with_metadata(structure, path, repo_structure['metadata'])
            else:
                att.text += _format_directory_with_metadata(structure, path, repo_structure['metadata'])
        else:
            att.text += f"**Directory Path**: `{path}`\n\n"
            att.text += f"*Structure not shown to prevent memory issues. Use `[files:false]` to see structure safely.*\n\n"
        
        return att
        
    elif repo_structure.get('type') == 'git_repository':
        # Git repository with full metadata + structure
        structure = repo_structure['structure']
        repo_path = repo_structure['path']
        repo_metadata = repo_structure['metadata']
        
        # Set att.text directly if it's the primary representation for git_repository
        att.text = _format_structure_with_metadata(structure, repo_path, repo_metadata)
        
    elif repo_structure.get('type') == 'directory':
        # Regular directory with basic metadata + structure
        structure = repo_structure['structure']
        dir_path = repo_structure['path']
        dir_metadata = repo_structure['metadata']
        
        # Set att.text directly if it's the primary representation for directory
        att.text = _format_directory_with_metadata(structure, dir_path, dir_metadata)
    
    # For files mode, also store file paths for expansion
    if repo_structure.get('process_files', False):
        files = repo_structure['files']
        att.metadata['file_paths'] = files
        att.metadata['directory_map'] = _format_directory_map(repo_structure['path'], files)
        # Keep _file_paths for simple.py to detect file expansion
        att._file_paths = files
    
    return att


@presenter
def files(att: Attachment, repo_structure: dict) -> Attachment:
    """Present repository/directory as a directory map for file processing mode."""
    if repo_structure.get('type') in ('git_repository', 'directory'):
        base_path = repo_structure['path']
        files = repo_structure['files']
        
        # Add directory map
        att.text += _format_directory_map(base_path, files)
        
        # Store file paths for Attachments() to expand
        att.metadata['file_paths'] = files
        att.metadata['directory_map'] = _format_directory_map(base_path, files)
        
    return att


# Helper functions for repository formatting (moved from load.py)
def _format_structure_tree(structure: dict, base_path: str) -> str:
    """Format directory structure as a tree."""
    import os
    
    result = f"# Directory Structure: {os.path.basename(base_path)}\n\n"
    result += "```\n"
    result += f"{'Permissions':<11} {'Owner':<8} {'Group':<8} {'Size':<8} {'Modified':<19} Name\n"
    result += f"{'-' * 11} {'-' * 8} {'-' * 8} {'-' * 8} {'-' * 19} {'-' * 20}\n"
    result += f"drwxr-xr-x  {'root':<8} {'root':<8} {'':>8} {'':>19} {os.path.basename(base_path)}/\n"
    result += _format_tree_recursive(structure, "")
    result += "```\n\n"
    return result


def _format_tree_recursive(structure: dict, prefix: str = "", is_root: bool = False) -> str:
    """Recursively format directory tree structure with clear hierarchy."""
    result = ""
    
    # Separate directories and files
    directories = {}
    files = {}
    
    for name, item in structure.items():
        if isinstance(item, dict) and 'type' in item:
            # This is a file or directory metadata dict
            if item.get('type') == 'directory':
                directories[name] = item
            else:
                files[name] = item
        else:
            # This is a nested directory structure (dict without 'type' key)
            directories[name] = item
    
    # Sort directories and files separately
    sorted_dirs = sorted(directories.items(), key=lambda x: x[0].lower())
    sorted_files = sorted(files.items(), key=lambda x: x[0].lower())
    
    # Combine: directories first, then files
    all_items = sorted_dirs + sorted_files
    
    for i, (name, item) in enumerate(all_items):
        is_last = i == len(all_items) - 1
        current_prefix = "└── " if is_last else "├── "
        
        # Check if this is a file metadata dict or a nested directory structure
        if isinstance(item, dict) and 'type' in item:
            # This is a file or directory metadata dict
            permissions = item.get('permissions', '?---------')
            owner = item.get('owner', 'unknown')
            group = item.get('group', 'unknown')
            size = item.get('size', 0)
            modified_str = item.get('modified_str', 'unknown')
            
            if item.get('type') == 'file':
                # File with detailed metadata
                size_str = _format_file_size(size)
                result += f"{prefix}{current_prefix}{permissions} {owner:<8} {group:<8} {size_str:>8} {modified_str} {name}\n"
            else:
                # Directory with detailed metadata
                result += f"{prefix}{current_prefix}{permissions} {owner:<8} {group:<8} {'':>8} {modified_str} {name}/\n"
                
                # Check if this directory has nested contents (files/subdirectories)
                # Look for any keys that are not metadata keys
                nested_contents = {k: v for k, v in item.items() 
                                 if k not in ['type', 'size', 'modified', 'permissions', 'owner', 'group', 'mode_octal', 'inode', 'links', 'modified_str']}
                
                if nested_contents:
                    # Recursively add children with proper indentation
                    next_prefix = prefix + ("    " if is_last else "│   ")
                    result += _format_tree_recursive(nested_contents, next_prefix)
        else:
            # This is a nested directory structure (dict without 'type' key)
            result += f"{prefix}{current_prefix}{'drwxr-xr-x'} {'unknown':<8} {'unknown':<8} {'':>8} {'unknown':<19} {name}/\n"
            # Recursively add children with proper indentation
            next_prefix = prefix + ("    " if is_last else "│   ")
            result += _format_tree_recursive(item, next_prefix)
    
    return result


def _format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}TB"


def _format_structure_with_metadata(structure: dict, repo_path: str, metadata: dict) -> str:
    """Format Git repository structure with metadata."""
    import os
    
    result = f"# Git Repository: {os.path.basename(repo_path)}\n\n"
    
    # Add Git metadata
    result += "## Repository Information\n\n"
    if metadata.get('current_branch'):
        result += f"**Branch**: {metadata['current_branch']}\n"
    if metadata.get('remote_url'):
        result += f"**Remote**: {metadata['remote_url']}\n"
    if metadata.get('last_commit'):
        commit = metadata['last_commit']
        result += f"**Last Commit**: {commit['hash'][:8]} - {commit['message']}\n"
        result += f"**Author**: {commit['author']} ({commit['date']})\n"
    if metadata.get('commit_count'):
        result += f"**Total Commits**: {metadata['commit_count']}\n"
    
    result += "\n"
    
    # Add directory structure
    result += "## Directory Structure\n\n"
    result += "```\n"
    result += f"{os.path.basename(repo_path)}/\n"
    result += _format_tree_recursive(structure, "")
    result += "```\n\n"
    
    return result


def _format_directory_with_metadata(structure: dict, dir_path: str, metadata: dict) -> str:
    """Format directory structure with basic metadata."""
    import os
    
    result = f"# Directory: {os.path.basename(dir_path)}\n\n"
    
    # Add basic metadata
    result += "## Directory Information\n\n"
    result += f"**Path**: {dir_path}\n"
    if metadata.get('total_size'):
        result += f"**Total Size**: {_format_file_size(metadata['total_size'])}\n"
    if metadata.get('file_count'):
        result += f"**Files**: {metadata['file_count']}\n"
    if metadata.get('directory_count'):
        result += f"**Directories**: {metadata['directory_count']}\n"
    
    result += "\n"
    
    # Add directory structure
    result += "## Directory Structure\n\n"
    result += "```\n"
    result += f"{os.path.basename(dir_path)}/\n"
    result += _format_tree_recursive(structure, "")
    result += "```\n\n"
    
    return result


def _format_directory_map(base_path: str, files: list) -> str:
    """Format directory map showing file organization with detailed metadata."""
    import os
    import stat
    from datetime import datetime
    
    result = f"## Directory Map\n\n"
    result += f"**Base Path**: `{base_path}`\n\n"
    result += f"**Files Found**: {len(files)}\n\n"
    
    if files:
        result += "**Detailed File List** (like `ls -la`):\n\n"
        result += "```\n"
        result += f"{'Permissions':<11} {'Owner':<8} {'Group':<8} {'Size':<8} {'Modified':<19} File\n"
        result += f"{'-' * 11} {'-' * 8} {'-' * 8} {'-' * 8} {'-' * 19} {'-' * 40}\n"
        
        for file_path in sorted(files):  # Show all files with details
            rel_path = os.path.relpath(file_path, base_path)
            try:
                stat_info = os.stat(file_path)
                permissions = stat.filemode(stat_info.st_mode)
                
                # Get owner/group names
                try:
                    import pwd, grp
                    owner = pwd.getpwuid(stat_info.st_uid).pw_name
                    group = grp.getgrgid(stat_info.st_gid).gr_name
                except (KeyError, ImportError):
                    owner = str(stat_info.st_uid)
                    group = str(stat_info.st_gid)
                
                size_str = _format_file_size(stat_info.st_size)
                modified_str = datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                
                result += f"{permissions} {owner:<8} {group:<8} {size_str:>8} {modified_str} {rel_path}\n"
            except OSError:
                result += f"?--------- {'unknown':<8} {'unknown':<8} {'0B':>8} {'unknown':<19} {rel_path}\n"
        
        result += "```\n\n"
    
    return result

