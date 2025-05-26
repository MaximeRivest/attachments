"""Git repository loader."""

import os
from ...core import Attachment, loader
from ... import matchers
from .utils import (
    get_ignore_patterns, collect_files, get_directory_structure, 
    get_repo_metadata
)


@loader(match=matchers.git_repo_match)
def git_repo_to_structure(att: Attachment) -> Attachment:
    """Load Git repository structure and file list.
    
    DSL: [files:true] = process individual files, [files:false] = structure + metadata only (default)
         [mode:content|metadata|structure] = processing mode
    """
    # Get DSL parameters
    ignore_cmd = att.commands.get('ignore', 'standard')
    max_files = int(att.commands.get('max_files', '1000'))
    glob_pattern = att.commands.get('glob', '')
    
    # Determine process_files based on 'files' command, 'mode' command, or default to True for repos
    explicit_files_command = att.commands.get('files')
    mode_command = att.commands.get('mode')

    if explicit_files_command is not None:
        process_files = explicit_files_command.lower() == 'true'
    elif mode_command is not None:
        # 'content' mode implies processing files.
        # 'structure' or 'metadata' modes imply process_files = False for loader's file content access.
        process_files = mode_command.lower() == 'content'
    else:
        # Default for git_repo_to_structure: process files, aligning with README "Default mode: content"
        process_files = True
    
    # Convert to absolute path for consistent handling
    repo_path = os.path.abspath(att.path)
    
    # Get ignore patterns
    ignore_patterns = get_ignore_patterns(repo_path, ignore_cmd)
    
    if process_files:
        # For file processing mode, check total size FIRST before collecting files
        # Count ALL files in directory to prevent memory issues during collection
        total_size = 0
        file_count = 0
        size_limit_mb = 500
        size_limit_bytes = size_limit_mb * 1024 * 1024
        
        # Walk directory to calculate total size without loading files into memory
        # Count ALL files, not just processable ones, to prevent memory issues
        for root, dirs, filenames in os.walk(repo_path):
            # DON'T filter directories during size check - we need to count everything
            # dirs[:] = [d for d in dirs if not should_ignore(os.path.join(root, d), repo_path, ignore_patterns)]
            
            for filename in filenames:
                file_path = os.path.join(root, filename)
                
                # Count ALL files, even ignored ones, for total size calculation
                try:
                    file_size = os.path.getsize(file_path)
                    total_size += file_size
                    file_count += 1
                    
                    # Early exit if size limit exceeded
                    if total_size > size_limit_bytes:
                        # Check if user explicitly opted in
                        force_process = att.commands.get('force', 'false').lower() == 'true'
                        
                        if not force_process:
                            # Create warning without collecting all files
                            warning_structure = {
                                'type': 'size_warning',
                                'path': repo_path,
                                'files': [],  # Don't collect files to save memory
                                'structure': {},  # Don't build structure to save memory
                                'metadata': get_repo_metadata(repo_path),
                                'total_size_mb': total_size / (1024 * 1024),
                                'file_count': file_count,
                                'size_limit_mb': size_limit_mb,
                                'process_files': False,
                                'size_check_stopped_early': True
                            }
                            att._obj = warning_structure
                            att.metadata.update(warning_structure['metadata'])
                            att.metadata.update({
                                'size_warning': True,
                                'total_size_mb': warning_structure['total_size_mb'],
                                'file_count': file_count,
                                'size_limit_exceeded': True,
                                'stopped_early': True
                            })
                            return att
                        else:
                            # User opted in with force:true, break size check and continue
                            break
                except OSError:
                    continue
                
                # DON'T limit file count during size check - we need to count everything
                # if file_count >= max_files * 10:  # Use higher limit for total file count
                #     break
        
    else:
        pass # process_files is false, size check is skipped.
    
    # If we get here, either:
    # 1. Not processing files (structure only)
    # 2. Size is under limit
    # 3. User forced processing with force:true
    
    # Now collect files normally
    all_files = collect_files(repo_path, ignore_patterns, max_files, glob_pattern, include_binary=True)
    files = all_files
    
    # Create repository structure object
    repo_structure = {
        'type': 'git_repository',
        'path': repo_path,
        'files': files,
        'ignore_patterns': ignore_patterns,
        'structure': get_directory_structure(repo_path, files),
        'metadata': get_repo_metadata(repo_path),
        'process_files': process_files  # Store the mode for later use
    }
    
    # Store the structure as the object
    att._obj = repo_structure
    
    # Store file paths for simple API access only if processing files
    if process_files:
        att._file_paths = files
    
    # Update attachment metadata
    att.metadata.update(repo_structure['metadata'])
    att.metadata.update({
        'file_count': len(files),
        'ignore_patterns': ignore_patterns,
        'is_git_repo': True,
        'process_files': process_files
    })
    
    return att 