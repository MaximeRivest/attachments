"""Utility functions for repository and directory processing."""

import os
import fnmatch
import glob
import re
from typing import List, Dict, Any


def get_ignore_patterns(base_path: str, ignore_command: str) -> List[str]:
    """Get ignore patterns based on DSL command."""
    if ignore_command == 'standard':
        return [
            # Hidden files and directories
            '.*', '.*/.*',
            # Git
            '.git', '.git/*', '**/.git/*',
            # Python
            '__pycache__', '__pycache__/*', '**/__pycache__/*',
            '*.pyc', '*.pyo', '*.pyd',
            # Virtual environments
            '.venv', '.venv/*', '**/.venv/*',
            'venv', 'venv/*', '**/venv/*',
            'env', 'env/*', '**/env/*',
            # Node.js
            'node_modules', 'node_modules/*', '**/node_modules/*',
            # Environment files
            '.env', '.env.*',
            # Logs and temporary files
            '*.log', '*.tmp', '*.cache',
            # OS files
            '.DS_Store', 'Thumbs.db',
            # Build directories
            'dist', 'build', 'target',
            # IDE files
            '.idea', '.vscode',
            # Test and coverage
            '.pytest_cache', '.coverage',
            # Package directories
            '*.egg-info', '*.dist-info'
        ]
    elif ignore_command == 'minimal':
        return [
            # Only the most essential ignores
            '.git', '.git/*', '**/.git/*',
            '__pycache__', '__pycache__/*', '**/__pycache__/*',
            '*.pyc', '*.pyo', '*.pyd',
            '.DS_Store', 'Thumbs.db'
        ]
    elif ignore_command == 'attachmentsignore':
        # Use .attachmentsignore file
        attachments_ignore_path = os.path.join(base_path, '.attachmentsignore')
        patterns = []
        if os.path.exists(attachments_ignore_path):
            try:
                with open(attachments_ignore_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            patterns.append(line)
            except Exception:
                pass
        return patterns
    elif ignore_command == 'gitignore':
        # Parse .gitignore file
        gitignore_path = os.path.join(base_path, '.gitignore')
        patterns = []
        if os.path.exists(gitignore_path):
            try:
                with open(gitignore_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            patterns.append(line)
            except Exception:
                pass
        return patterns
    elif ignore_command == 'auto':
        # Auto-detect: use .attachmentsignore if exists, otherwise .gitignore, otherwise standard
        attachments_ignore_path = os.path.join(base_path, '.attachmentsignore')
        if os.path.exists(attachments_ignore_path):
            return get_ignore_patterns(base_path, 'attachmentsignore')
        
        gitignore_path = os.path.join(base_path, '.gitignore')
        if os.path.exists(gitignore_path):
            return get_ignore_patterns(base_path, 'gitignore')
        
        return get_ignore_patterns(base_path, 'standard')
    elif ignore_command:
        # Custom comma-separated patterns
        return [pattern.strip() for pattern in ignore_command.split(',')]
    else:
        # No ignore patterns
        return []


def should_ignore(file_path: str, base_path: str, ignore_patterns: List[str]) -> bool:
    """Check if file should be ignored based on patterns."""
    # Get relative path from base
    try:
        rel_path = os.path.relpath(file_path, base_path)
    except ValueError:
        return True  # Outside base path, ignore
    
    # Normalize path separators
    rel_path = rel_path.replace('\\', '/')
    
    for pattern in ignore_patterns:
        # Handle different pattern types
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        if fnmatch.fnmatch(os.path.basename(rel_path), pattern):
            return True
        # Handle directory patterns
        if pattern.endswith('/') and rel_path.startswith(pattern):
            return True
        # Handle glob patterns
        if '**' in pattern:
            # Convert ** patterns to fnmatch
            glob_pattern = pattern.replace('**/', '*/')
            if fnmatch.fnmatch(rel_path, glob_pattern):
                return True
    
    return False


def collect_files(base_path: str, ignore_patterns: List[str], max_files: int = 1000, 
                  glob_pattern: str = '', recursive: bool = True, include_binary: bool = False) -> List[str]:
    """Collect all files in directory, respecting ignore patterns and glob filters."""
    files = []
    
    if recursive:
        # Recursive directory walk
        for root, dirs, filenames in os.walk(base_path):
            # Filter directories to avoid walking into ignored ones
            dirs[:] = [d for d in dirs if not should_ignore(os.path.join(root, d), base_path, ignore_patterns)]
            
            for filename in filenames:
                file_path = os.path.join(root, filename)
                
                # Skip if ignored
                if should_ignore(file_path, base_path, ignore_patterns):
                    continue
                
                # Skip binary files only if not including binary (for file processing mode)
                if not include_binary and is_likely_binary(file_path):
                    continue
                
                # Apply glob filter if specified
                if glob_pattern and not matches_glob_pattern(file_path, base_path, glob_pattern):
                    continue
                
                files.append(file_path)
                
                # Limit number of files to prevent overwhelming
                if len(files) >= max_files:
                    break
            
            if len(files) >= max_files:
                break
    else:
        # Non-recursive - just files in the directory
        try:
            for filename in os.listdir(base_path):
                file_path = os.path.join(base_path, filename)
                
                # Skip directories in non-recursive mode
                if os.path.isdir(file_path):
                    continue
                
                # Skip if ignored
                if should_ignore(file_path, base_path, ignore_patterns):
                    continue
                
                # Skip binary files only if not including binary
                if not include_binary and is_likely_binary(file_path):
                    continue
                
                # Apply glob filter if specified
                if glob_pattern and not matches_glob_pattern(file_path, base_path, glob_pattern):
                    continue
                
                files.append(file_path)
                
                if len(files) >= max_files:
                    break
        except OSError:
            pass
    
    return sorted(files)


def collect_files_from_glob(glob_path: str, max_files: int = 1000) -> List[str]:
    """Collect files using glob pattern."""
    files = []
    
    try:
        # Use glob to find matching files
        matches = glob.glob(glob_path, recursive=True)
        
        for file_path in matches:
            # Skip directories
            if os.path.isdir(file_path):
                continue
            
            # Skip binary files
            if is_likely_binary(file_path):
                continue
            
            files.append(os.path.abspath(file_path))
            
            if len(files) >= max_files:
                break
                
    except Exception:
        pass
    
    return sorted(files)


def get_glob_base_path(glob_path: str) -> str:
    """Extract base directory from glob pattern."""
    # Find the first directory part without glob characters
    parts = glob_path.split(os.sep)
    base_parts = []
    
    for part in parts:
        if any(char in part for char in ['*', '?', '[', ']']):
            break
        base_parts.append(part)
    
    if base_parts:
        # Handle absolute paths properly - preserve leading slash
        if glob_path.startswith(os.sep) and base_parts[0] == '':
            # Absolute path: ['', 'home', 'maxime', ...] -> '/home/maxime/...'
            if len(base_parts) > 1:
                return os.sep + os.path.join(*base_parts[1:])
            else:
                return os.sep
        else:
            # Relative path
            return os.path.join(*base_parts) if len(base_parts) > 1 else base_parts[0]
    else:
        return os.getcwd()


def matches_glob_pattern(file_path: str, base_path: str, glob_pattern: str) -> bool:
    """Check if file matches glob pattern."""
    rel_path = os.path.relpath(file_path, base_path)
    filename = os.path.basename(file_path)
    
    # Split multiple patterns by comma
    patterns_to_check = [p.strip() for p in glob_pattern.split(',')]
    
    for p_str in patterns_to_check:
        # fnmatch.translate converts glob to regex, handling **, *, ? etc.
        # The (?s) flag allows . to match newlines, useful for multi-line filenames (though rare)
        # \\Z ensures the whole string matches.
        regex = fnmatch.translate(p_str) 
        if re.match(regex, filename) or re.match(regex, rel_path):
            return True
    
    return False


def is_likely_binary(file_path: str) -> bool:
    """Basic heuristic to detect truly problematic binary files."""
    # Only skip files that are truly problematic to process
    problematic_extensions = {
        '.exe', '.dll', '.so', '.dylib', '.bin', '.obj', '.o',
        '.pyc', '.pyo', '.pyd', '.class',
        '.woff', '.woff2', '.ttf', '.otf', '.eot'
    }
    
    ext = os.path.splitext(file_path)[1].lower()
    if ext in problematic_extensions:
        return True
    
    # Try to read first few bytes to detect binary content
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(1024)
            # If chunk contains null bytes, likely binary
            if b'\x00' in chunk:
                return True
    except (OSError, UnicodeDecodeError):
        return True
    
    return False


def get_directory_structure(base_path: str, files: List[str], include_all_dirs: bool = False, only_dirs_with_files: bool = False, ignore_patterns: List[str] = None) -> Dict[str, Any]:
    """Generate tree structure representation with detailed file metadata."""
    import stat
    from datetime import datetime
    
    if ignore_patterns is None:
        ignore_patterns = []
    
    structure = {}
    
    # Collect directories from files
    directories = set()
    for file_path in files:
        rel_path = os.path.relpath(file_path, base_path)
        parts = rel_path.split(os.sep)
        
        # Collect all directory paths
        for i in range(len(parts) - 1):
            dir_path = os.path.join(base_path, *parts[:i+1])
            directories.add(dir_path)
    
    # If include_all_dirs is True, also add all directories in the base path
    # But if only_dirs_with_files is True, we skip this step
    if include_all_dirs and not only_dirs_with_files:
        try:
            for root, dirs, filenames in os.walk(base_path):
                # Filter out ignored directories during walk
                dirs[:] = [d for d in dirs if not should_ignore(os.path.join(root, d), base_path, ignore_patterns)]
                
                # Add the current directory
                if root != base_path:  # Don't add the base path itself
                    if not should_ignore(root, base_path, ignore_patterns):
                        directories.add(root)
                
                # Add all subdirectories
                for dirname in dirs:
                    dir_path = os.path.join(root, dirname)
                    if not should_ignore(dir_path, base_path, ignore_patterns):
                        directories.add(dir_path)
        except OSError:
            pass
    
    # Process directories first
    for dir_path in sorted(directories):
        # Skip ignored directories
        if should_ignore(dir_path, base_path, ignore_patterns):
            continue
            
        rel_path = os.path.relpath(dir_path, base_path)
        parts = rel_path.split(os.sep)
        
        current = structure
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        # Add directory info
        try:
            stat_info = os.stat(dir_path)
            current[parts[-1]] = {
                'type': 'directory',
                'size': stat_info.st_size,
                'modified': stat_info.st_mtime,
                'permissions': stat.filemode(stat_info.st_mode),
                'owner': get_owner_name(stat_info.st_uid),
                'group': get_group_name(stat_info.st_gid),
                'mode_octal': oct(stat_info.st_mode)[-3:],
                'inode': stat_info.st_ino,
                'links': stat_info.st_nlink,
                'modified_str': datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            }
        except OSError:
            current[parts[-1]] = {
                'type': 'directory', 
                'size': 0, 
                'modified': 0,
                'permissions': '?---------',
                'owner': 'unknown',
                'group': 'unknown',
                'mode_octal': '000',
                'inode': 0,
                'links': 0,
                'modified_str': 'unknown'
            }
    
    # Process files
    for file_path in files:
        rel_path = os.path.relpath(file_path, base_path)
        parts = rel_path.split(os.sep)
        
        current = structure
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        # Add file info with detailed metadata
        try:
            stat_info = os.stat(file_path)
            current[parts[-1]] = {
                'type': 'file',
                'size': stat_info.st_size,
                'modified': stat_info.st_mtime,
                'permissions': stat.filemode(stat_info.st_mode),
                'owner': get_owner_name(stat_info.st_uid),
                'group': get_group_name(stat_info.st_gid),
                'mode_octal': oct(stat_info.st_mode)[-3:],
                'inode': stat_info.st_ino,
                'links': stat_info.st_nlink,
                'modified_str': datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            }
        except OSError:
            current[parts[-1]] = {
                'type': 'file', 
                'size': 0, 
                'modified': 0,
                'permissions': '?---------',
                'owner': 'unknown',
                'group': 'unknown',
                'mode_octal': '000',
                'inode': 0,
                'links': 0,
                'modified_str': 'unknown'
            }
    
    return structure


def get_owner_name(uid: int) -> str:
    """Get username from UID."""
    try:
        import pwd
        return pwd.getpwuid(uid).pw_name
    except (KeyError, ImportError):
        return str(uid)


def get_group_name(gid: int) -> str:
    """Get group name from GID."""
    try:
        import grp
        return grp.getgrgid(gid).gr_name
    except (KeyError, ImportError):
        return str(gid)


def get_repo_metadata(repo_path: str) -> Dict[str, Any]:
    """Extract Git repository metadata."""
    metadata = {
        'repo_path': repo_path,
        'is_git_repo': True
    }
    
    try:
        # Try to get Git info using GitPython if available
        import git
        repo = git.Repo(repo_path)
        
        metadata.update({
            'current_branch': repo.active_branch.name,
            'commit_count': len(list(repo.iter_commits())),
            'last_commit': {
                'hash': repo.head.commit.hexsha[:8],
                'message': repo.head.commit.message.strip(),
                'author': str(repo.head.commit.author),
                'date': repo.head.commit.committed_datetime.isoformat()
            },
            'remotes': [remote.name for remote in repo.remotes],
            'is_dirty': repo.is_dirty()
        })
        
        # Get remote URL if available
        if repo.remotes:
            try:
                metadata['remote_url'] = repo.remotes.origin.url
            except:
                pass
                
    except ImportError:
        # GitPython not available, use basic Git commands
        try:
            import subprocess
            
            # Get current branch
            result = subprocess.run(['git', 'branch', '--show-current'], 
                                  cwd=repo_path, capture_output=True, text=True)
            if result.returncode == 0:
                metadata['current_branch'] = result.stdout.strip()
            
            # Get last commit info
            result = subprocess.run(['git', 'log', '-1', '--format=%H|%s|%an|%ai'], 
                                  cwd=repo_path, capture_output=True, text=True)
            if result.returncode == 0:
                parts = result.stdout.strip().split('|')
                if len(parts) >= 4:
                    metadata['last_commit'] = {
                        'hash': parts[0][:8],
                        'message': parts[1],
                        'author': parts[2],
                        'date': parts[3]
                    }
        except Exception:
            pass
    except Exception:
        pass
    
    return metadata


def get_directory_metadata(dir_path: str) -> Dict[str, Any]:
    """Extract basic directory metadata."""
    metadata = {
        'directory_path': dir_path,
        'is_git_repo': False
    }
    
    try:
        # Basic directory info
        stat = os.stat(dir_path)
        metadata.update({
            'directory_name': os.path.basename(dir_path),
            'modified': stat.st_mtime,
            'absolute_path': os.path.abspath(dir_path)
        })
    except OSError:
        pass
    
    return metadata 