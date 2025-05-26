"""Directory and glob pattern loader."""

import os
from ...core import Attachment, loader
from ... import matchers
from .utils import (
    get_ignore_patterns, collect_files, collect_files_from_glob, 
    get_glob_base_path, get_directory_structure, get_directory_metadata,
    should_ignore
)


@loader(match=matchers.directory_or_glob_match)
def directory_to_structure(att: Attachment) -> Attachment:
    """Load directory or glob pattern structure and file list.
    
    DSL: [files:true] = process individual files, [files:false] = structure + metadata only (default)
    """
    # Get DSL parameters - simplified to just files:true/false
    ignore_cmd = att.commands.get('ignore', 'standard')  # Better defaults for all directories
    max_files = int(att.commands.get('max_files', '1000'))
    glob_pattern = att.commands.get('glob', '')
    recursive = att.commands.get('recursive', 'true').lower() == 'true'
    process_files = att.commands.get('files', 'false').lower() == 'true'
    dirs_only_with_files = att.commands.get('dirs_only_with_files', 'true').lower() == 'true'
    
    # Initialize ignore_patterns to avoid UnboundLocalError
    ignore_patterns = []
    
    # Handle glob patterns in the path itself
    if matchers.glob_pattern_match(att):
        # Path contains glob patterns - use glob to find files
        files = collect_files_from_glob(att.path, max_files)
        base_path = get_glob_base_path(att.path)
        # For glob patterns, we don't use ignore patterns since the pattern is explicit
        ignore_patterns = []
    else:
        # Regular directory
        base_path = os.path.abspath(att.path)
        ignore_patterns = get_ignore_patterns(base_path, ignore_cmd)
        
        if process_files:
            # For file processing mode, check total size FIRST before collecting files
            # Count ALL files in directory to prevent memory issues during collection
            total_size = 0
            file_count = 0
            size_limit_mb = 500
            size_limit_bytes = size_limit_mb * 1024 * 1024
            
            # Walk directory to calculate total size without loading files into memory
            # Count ALL files, not just processable ones, to prevent memory issues
            if recursive:
                for root, dirs, filenames in os.walk(base_path):
                    # DON'T filter directories during size check - we need to count everything
                    # dirs[:] = [d for d in dirs if not should_ignore(os.path.join(root, d), base_path, ignore_patterns)]
                    
                    for filename in filenames:
                        file_path = os.path.join(root, filename)
                        
                        # Count ALL files, even ignored ones, for total size calculation
                        try:
                            file_size = os.path.getsize(file_path)
                            total_size += file_size
                            file_count += 1
                            
                            # Early exit if size limit exceeded
                            if total_size > size_limit_bytes:
                                force_process = att.commands.get('force', 'false').lower() == 'true'
                                
                                if not force_process:
                                    warning_structure = {
                                        'type': 'size_warning',
                                        'path': base_path,
                                        'files': [],
                                        'structure': {},
                                        'metadata': get_directory_metadata(base_path),
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
                                    break
                        except OSError:
                            continue
                        
                        # DON'T limit file count during size check - we need to count everything
                        # if file_count >= max_files * 10:  # Use higher limit for total file count
                        #     break
                    
                    if total_size > size_limit_bytes and att.commands.get('force', 'false').lower() != 'true':
                        break
            else:
                # Non-recursive size check
                total_size = 0 # Initialize for this non-recursive scope
                file_count = 0 # Initialize for this non-recursive scope
                try:
                    for filename in os.listdir(base_path):
                        file_path = os.path.join(base_path, filename)
                        
                        # Skip directories in non-recursive mode
                        if os.path.isdir(file_path):
                            continue
                        
                        # Skip if ignored
                        if should_ignore(file_path, base_path, ignore_patterns):
                            continue
                        
                        try:
                            file_size = os.path.getsize(file_path)
                            total_size += file_size
                            file_count += 1
                        except OSError:
                            continue
                        
                        # DON'T limit file count during size check - we need to count everything
                        # if file_count >= max_files * 10:  # Use higher limit for total file count
                        #     break
                except OSError:
                    pass
        else:
            # Non-recursive size check
            total_size = 0 # Initialize for this non-recursive scope
            file_count = 0 # Initialize for this non-recursive scope
            try:
                for filename in os.listdir(base_path):
                    file_path = os.path.join(base_path, filename)
                    
                    # Skip directories in non-recursive mode
                    if os.path.isdir(file_path):
                        continue
                    
                    # Skip if ignored
                    if should_ignore(file_path, base_path, ignore_patterns):
                        continue
                    
                    try:
                        file_size = os.path.getsize(file_path)
                        total_size += file_size
                        file_count += 1
                    except OSError:
                        continue
                    
                    # DON'T limit file count during size check - we need to count everything
                    # if file_count >= max_files * 10:  # Use higher limit for total file count
                    #     break
            except OSError:
                pass
    
    # If we get here, either:
    # 1. Not processing files (structure only)
    # 2. Size is under limit
    # 3. User forced processing with force:true
    
    # Now collect files normally (but only if not already collected via glob)
    if matchers.glob_pattern_match(att):
        # Files already collected via glob pattern
        all_files = files
    else:
        # Collect files from directory
        all_files = collect_files(base_path, ignore_patterns, max_files, glob_pattern, recursive, include_binary=True)
    
    if process_files:
        files = all_files
    else:
        files = all_files
    
    # Create directory structure object
    dir_structure = {
        'type': 'directory',
        'path': base_path,
        'files': files,
        'ignore_patterns': ignore_patterns,
        'structure': get_directory_structure(base_path, files, include_all_dirs=not process_files, only_dirs_with_files=dirs_only_with_files, ignore_patterns=ignore_patterns),
        'metadata': get_directory_metadata(base_path),
        'process_files': process_files  # Store the mode for later use
    }
    
    # Store the structure as the object
    att._obj = dir_structure
    
    # Store file paths for simple API access only if processing files
    if process_files:
        att._file_paths = files
    
    # Update attachment metadata
    att.metadata.update(dir_structure['metadata'])
    att.metadata.update({
        'file_count': len(files),
        'is_git_repo': False,
        'process_files': process_files
    })
    
    return att 