#!/usr/bin/env python3
"""
TODO Collector for Attachments Library

This script collects all TODO, FIXME, HACK, XXX, and NOTE comments from the codebase
and provides multiple output formats for professional TODO management.

Professional approaches supported:
1. Simple text file output (TODO.md)
2. GitHub Issues format (for integration with issue tracking)
3. JSON format (for integration with project management tools)
4. CSV format (for spreadsheet management)
5. Interactive terminal output with filtering

Usage:
    python scripts/collect_todos.py [options]

Examples:
    python scripts/collect_todos.py --output markdown --file TODO.md
    python scripts/collect_todos.py --output json --file todos.json
    python scripts/collect_todos.py --output csv --file todos.csv
    python scripts/collect_todos.py --interactive
"""

import argparse
import json
import csv
import re
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class TodoItem:
    """Represents a single TODO item found in the codebase."""
    file_path: str
    line_number: int
    todo_type: str  # TODO, FIXME, HACK, XXX, NOTE
    content: str
    context_lines: List[str]  # Surrounding lines for context
    author: Optional[str] = None  # Extracted from git blame if available
    priority: str = "medium"  # low, medium, high, critical
    category: str = "general"  # general, bug, feature, refactor, docs, test
    estimated_effort: str = "unknown"  # quick, small, medium, large


class TodoCollector:
    """Collects and manages TODO items from the codebase."""
    
    # TODO patterns to search for
    TODO_PATTERNS = [
        r'#\s*(TODO|FIXME|HACK|XXX|NOTE)\s*:?\s*(.+)',
        r'//\s*(TODO|FIXME|HACK|XXX|NOTE)\s*:?\s*(.+)',
        r'/\*\s*(TODO|FIXME|HACK|XXX|NOTE)\s*:?\s*(.+)\s*\*/',
        r'<!--\s*(TODO|FIXME|HACK|XXX|NOTE)\s*:?\s*(.+)\s*-->',
    ]
    
    # File extensions to search
    SEARCH_EXTENSIONS = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h',
        '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.scala',
        '.md', '.rst', '.txt', '.yml', '.yaml', '.json', '.xml', '.html',
        '.css', '.scss', '.sass', '.less', '.sql', '.sh', '.bash'
    }
    
    # Directories to ignore
    IGNORE_DIRS = {
        '.git', '.svn', '.hg', '__pycache__', '.pytest_cache', 'node_modules',
        '.venv', 'venv', 'env', '.env', 'build', 'dist', '.build', '_build',
        '.tox', '.coverage', 'htmlcov', '.mypy_cache', '.idea', '.vscode'
    }
    
    def __init__(self, root_path: str = "src"):
        self.root_path = Path(root_path).resolve()
        self.todos: List[TodoItem] = []
    
    def collect_todos(self) -> List[TodoItem]:
        """Collect all TODO items from the codebase."""
        self.todos = []
        
        for file_path in self._get_files_to_search():
            try:
                self._process_file(file_path)
            except Exception as e:
                print(f"Warning: Could not process {file_path}: {e}")
        
        return self.todos
    
    def _get_files_to_search(self) -> List[Path]:
        """Get list of files to search for TODOs."""
        files = []
        
        for root, dirs, filenames in os.walk(self.root_path):
            # Remove ignored directories
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]
            
            for filename in filenames:
                file_path = Path(root) / filename
                if file_path.suffix.lower() in self.SEARCH_EXTENSIONS:
                    files.append(file_path)
        
        return files
    
    def _process_file(self, file_path: Path):
        """Process a single file for TODO items."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception:
            return
        
        for line_num, line in enumerate(lines, 1):
            for pattern in self.TODO_PATTERNS:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    todo_type = match.group(1).upper()
                    content = match.group(2).strip()
                    
                    # Skip if this is a skip marker
                    if '+SKIP' in line.upper() or 'TODOON' in line.upper():
                        continue
                    
                    # Get context lines
                    context_start = max(0, line_num - 3)
                    context_end = min(len(lines), line_num + 2)
                    context_lines = [
                        f"{i+1:4d}: {lines[i].rstrip()}" 
                        for i in range(context_start, context_end)
                    ]
                    
                    # Extract additional metadata from content
                    priority = self._extract_priority(content)
                    category = self._extract_category(content, file_path)
                    effort = self._extract_effort(content)
                    
                    todo_item = TodoItem(
                        file_path=str(file_path.relative_to(self.root_path)),
                        line_number=line_num,
                        todo_type=todo_type,
                        content=content,
                        context_lines=context_lines,
                        priority=priority,
                        category=category,
                        estimated_effort=effort
                    )
                    
                    self.todos.append(todo_item)
                    break  # Only match first pattern per line
    
    def _extract_priority(self, content: str) -> str:
        """Extract priority from TODO content."""
        content_lower = content.lower()
        if any(word in content_lower for word in ['critical', 'urgent', 'asap']):
            return 'critical'
        elif any(word in content_lower for word in ['high', 'important']):
            return 'high'
        elif any(word in content_lower for word in ['low', 'minor', 'someday']):
            return 'low'
        return 'medium'
    
    def _extract_category(self, content: str, file_path: Path) -> str:
        """Extract category from TODO content and file context."""
        content_lower = content.lower()
        
        # Category keywords
        if any(word in content_lower for word in ['bug', 'fix', 'error', 'issue']):
            return 'bug'
        elif any(word in content_lower for word in ['feature', 'add', 'implement', 'new']):
            return 'feature'
        elif any(word in content_lower for word in ['refactor', 'clean', 'optimize', 'improve']):
            return 'refactor'
        elif any(word in content_lower for word in ['doc', 'comment', 'explain']):
            return 'docs'
        elif any(word in content_lower for word in ['test', 'spec', 'coverage']):
            return 'test'
        
        # File-based categories
        if 'test' in str(file_path).lower():
            return 'test'
        elif file_path.suffix in {'.md', '.rst', '.txt'}:
            return 'docs'
        
        return 'general'
    
    def _extract_effort(self, content: str) -> str:
        """Extract estimated effort from TODO content."""
        content_lower = content.lower()
        if any(word in content_lower for word in ['quick', 'simple', 'easy', 'minor']):
            return 'quick'
        elif any(word in content_lower for word in ['small', 'short']):
            return 'small'
        elif any(word in content_lower for word in ['large', 'big', 'major', 'complex']):
            return 'large'
        elif any(word in content_lower for word in ['medium']):
            return 'medium'
        return 'unknown'
    
    def output_markdown(self, file_path: str = "TODO.md"):
        """Output TODOs as a markdown file."""
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("# TODO List\n\n")
            f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total TODOs found: {len(self.todos)}\n\n")
            
            # Group by category
            categories = {}
            for todo in self.todos:
                if todo.category not in categories:
                    categories[todo.category] = []
                categories[todo.category].append(todo)
            
            for category, todos in sorted(categories.items()):
                f.write(f"## {category.title()} ({len(todos)} items)\n\n")
                
                for todo in sorted(todos, key=lambda x: (x.priority != 'critical', x.priority != 'high', x.file_path)):
                    f.write(f"### {todo.todo_type}: {todo.content}\n\n")
                    f.write(f"- **File**: `{todo.file_path}:{todo.line_number}`\n")
                    f.write(f"- **Priority**: {todo.priority}\n")
                    f.write(f"- **Effort**: {todo.estimated_effort}\n\n")
                    
                    f.write("**Context:**\n```\n")
                    for line in todo.context_lines:
                        f.write(f"{line}\n")
                    f.write("```\n\n")
                    f.write("---\n\n")
        
        print(f"Markdown TODO list written to: {file_path}")
    
    def output_json(self, file_path: str = "todos.json"):
        """Output TODOs as JSON for integration with tools."""
        data = {
            "generated_at": datetime.now().isoformat(),
            "total_count": len(self.todos),
            "todos": [asdict(todo) for todo in self.todos]
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"JSON TODO list written to: {file_path}")
    
    def output_csv(self, file_path: str = "todos.csv"):
        """Output TODOs as CSV for spreadsheet management."""
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'File', 'Line', 'Type', 'Priority', 'Category', 'Effort',
                'Content', 'Context'
            ])
            
            # Data
            for todo in self.todos:
                context = ' | '.join(todo.context_lines)
                writer.writerow([
                    todo.file_path, todo.line_number, todo.todo_type,
                    todo.priority, todo.category, todo.estimated_effort,
                    todo.content, context
                ])
        
        print(f"CSV TODO list written to: {file_path}")
    
    def output_github_issues(self, file_path: str = "github_issues.md"):
        """Output TODOs in GitHub Issues format."""
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("# GitHub Issues from TODOs\n\n")
            f.write("Copy and paste each section below as a new GitHub issue.\n\n")
            f.write("---\n\n")
            
            for i, todo in enumerate(self.todos, 1):
                # Issue title
                title = f"{todo.todo_type}: {todo.content[:60]}{'...' if len(todo.content) > 60 else ''}"
                f.write(f"## Issue #{i}: {title}\n\n")
                
                # Issue body
                f.write("**Description:**\n")
                f.write(f"{todo.content}\n\n")
                
                f.write("**Location:**\n")
                f.write(f"File: `{todo.file_path}` (line {todo.line_number})\n\n")
                
                f.write("**Context:**\n")
                f.write("```python\n")  # Assume Python for syntax highlighting
                for line in todo.context_lines:
                    f.write(f"{line}\n")
                f.write("```\n\n")
                
                # Labels
                labels = [todo.category, todo.priority]
                if todo.todo_type.lower() != 'todo':
                    labels.append(todo.todo_type.lower())
                
                f.write(f"**Labels:** {', '.join(labels)}\n")
                f.write(f"**Effort:** {todo.estimated_effort}\n\n")
                f.write("---\n\n")
        
        print(f"GitHub Issues format written to: {file_path}")
    
    def interactive_mode(self):
        """Interactive terminal mode for browsing TODOs."""
        if not self.todos:
            print("No TODOs found in the codebase!")
            return
        
        print(f"\n🔍 Found {len(self.todos)} TODO items in the codebase\n")
        
        while True:
            print("Options:")
            print("1. List all TODOs")
            print("2. Filter by type (TODO, FIXME, etc.)")
            print("3. Filter by priority")
            print("4. Filter by category")
            print("5. Show statistics")
            print("6. Export to file")
            print("0. Exit")
            
            choice = input("\nEnter your choice (0-6): ").strip()
            
            if choice == '0':
                break
            elif choice == '1':
                self._show_todos(self.todos)
            elif choice == '2':
                self._filter_by_type()
            elif choice == '3':
                self._filter_by_priority()
            elif choice == '4':
                self._filter_by_category()
            elif choice == '5':
                self._show_statistics()
            elif choice == '6':
                self._export_menu()
            else:
                print("Invalid choice. Please try again.")
    
    def _show_todos(self, todos: List[TodoItem], limit: int = 10):
        """Show a list of TODOs."""
        if not todos:
            print("No TODOs match the current filter.")
            return
        
        print(f"\nShowing {min(len(todos), limit)} of {len(todos)} TODOs:\n")
        
        for i, todo in enumerate(todos[:limit], 1):
            print(f"{i:2d}. [{todo.todo_type}] {todo.content}")
            print(f"    📁 {todo.file_path}:{todo.line_number}")
            print(f"    🏷️  {todo.priority} priority, {todo.category} category")
            print()
        
        if len(todos) > limit:
            print(f"... and {len(todos) - limit} more")
    
    def _filter_by_type(self):
        """Filter TODOs by type."""
        types = list(set(todo.todo_type for todo in self.todos))
        print(f"\nAvailable types: {', '.join(types)}")
        
        selected_type = input("Enter type to filter by: ").strip().upper()
        if selected_type in types:
            filtered = [todo for todo in self.todos if todo.todo_type == selected_type]
            self._show_todos(filtered)
        else:
            print("Invalid type.")
    
    def _filter_by_priority(self):
        """Filter TODOs by priority."""
        priorities = ['critical', 'high', 'medium', 'low']
        print(f"\nAvailable priorities: {', '.join(priorities)}")
        
        selected_priority = input("Enter priority to filter by: ").strip().lower()
        if selected_priority in priorities:
            filtered = [todo for todo in self.todos if todo.priority == selected_priority]
            self._show_todos(filtered)
        else:
            print("Invalid priority.")
    
    def _filter_by_category(self):
        """Filter TODOs by category."""
        categories = list(set(todo.category for todo in self.todos))
        print(f"\nAvailable categories: {', '.join(categories)}")
        
        selected_category = input("Enter category to filter by: ").strip().lower()
        if selected_category in categories:
            filtered = [todo for todo in self.todos if todo.category == selected_category]
            self._show_todos(filtered)
        else:
            print("Invalid category.")
    
    def _show_statistics(self):
        """Show TODO statistics."""
        if not self.todos:
            print("No TODOs found.")
            return
        
        print(f"\n📊 TODO Statistics:")
        print(f"Total TODOs: {len(self.todos)}")
        
        # By type
        types = {}
        for todo in self.todos:
            types[todo.todo_type] = types.get(todo.todo_type, 0) + 1
        print(f"\nBy Type:")
        for todo_type, count in sorted(types.items()):
            print(f"  {todo_type}: {count}")
        
        # By priority
        priorities = {}
        for todo in self.todos:
            priorities[todo.priority] = priorities.get(todo.priority, 0) + 1
        print(f"\nBy Priority:")
        for priority in ['critical', 'high', 'medium', 'low']:
            count = priorities.get(priority, 0)
            if count > 0:
                print(f"  {priority}: {count}")
        
        # By category
        categories = {}
        for todo in self.todos:
            categories[todo.category] = categories.get(todo.category, 0) + 1
        print(f"\nBy Category:")
        for category, count in sorted(categories.items()):
            print(f"  {category}: {count}")
    
    def _export_menu(self):
        """Show export options."""
        print("\nExport options:")
        print("1. Markdown (TODO.md)")
        print("2. JSON (todos.json)")
        print("3. CSV (todos.csv)")
        print("4. GitHub Issues (github_issues.md)")
        
        choice = input("Enter export choice (1-4): ").strip()
        
        if choice == '1':
            self.output_markdown()
        elif choice == '2':
            self.output_json()
        elif choice == '3':
            self.output_csv()
        elif choice == '4':
            self.output_github_issues()
        else:
            print("Invalid choice.")


def main():
    parser = argparse.ArgumentParser(
        description="Collect and manage TODOs from the codebase",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '--output', '-o',
        choices=['markdown', 'json', 'csv', 'github'],
        help='Output format'
    )
    
    parser.add_argument(
        '--file', '-f',
        help='Output file path'
    )
    
    parser.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='Run in interactive mode'
    )
    
    parser.add_argument(
        '--root',
        default='src',
        help='Root directory to search (default: src directory)'
    )
    
    args = parser.parse_args()
    
    # Create collector and collect TODOs
    collector = TodoCollector(args.root)
    print("🔍 Scanning codebase for TODOs...")
    todos = collector.collect_todos()
    print(f"✅ Found {len(todos)} TODO items")
    
    if args.interactive:
        collector.interactive_mode()
    elif args.output:
        if args.output == 'markdown':
            collector.output_markdown(args.file or 'TODO.md')
        elif args.output == 'json':
            collector.output_json(args.file or 'todos.json')
        elif args.output == 'csv':
            collector.output_csv(args.file or 'todos.csv')
        elif args.output == 'github':
            collector.output_github_issues(args.file or 'github_issues.md')
    else:
        # Default: show summary and offer interactive mode
        if todos:
            print(f"\nFound {len(todos)} TODOs:")
            for todo in todos[:5]:  # Show first 5
                print(f"  • [{todo.todo_type}] {todo.content[:60]}{'...' if len(todo.content) > 60 else ''}")
                print(f"    📁 {todo.file_path}:{todo.line_number}")
            
            if len(todos) > 5:
                print(f"  ... and {len(todos) - 5} more")
            
            print(f"\nRun with --interactive for more options")
            print(f"Or use --output to export (markdown, json, csv, github)")
        else:
            print("No TODOs found in the codebase! 🎉")


if __name__ == '__main__':
    main() 