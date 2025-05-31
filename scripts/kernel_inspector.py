#!/usr/bin/env python3
"""
Jupyter Kernel Inspector - Debug and inspect running Jupyter kernels

Usage:
    uv run python docs/scripts/kernel_inspector.py [options]

Examples:
    # Basic inspection (last 4 In/Out + variables)
    uv run python docs/scripts/kernel_inspector.py

    # Show more history
    uv run python docs/scripts/kernel_inspector.py --history 10

    # Focus on specific variable
    uv run python docs/scripts/kernel_inspector.py --var agent

    # Show only errors/exceptions
    uv run python docs/scripts/kernel_inspector.py --errors-only

    # Execute custom code in kernel
    uv run python docs/scripts/kernel_inspector.py --exec "print(type(agent))"

    # Show all available kernels
    uv run python docs/scripts/kernel_inspector.py --list-kernels
"""

import os
import json
import glob
import argparse
from jupyter_client import BlockingKernelClient

def find_kernels():
    """Find all available kernel connection files."""
    runtime_dir = os.path.expanduser("~/.local/share/jupyter/runtime/")
    kernel_files = glob.glob(os.path.join(runtime_dir, "kernel-*.json"))
    
    if not kernel_files:
        return []
    
    # Sort by modification time, most recent first
    kernel_files.sort(key=os.path.getmtime, reverse=True)
    return kernel_files

def connect_to_kernel(connection_file, timeout=5):
    """Connect to a running kernel."""
    try:
        with open(connection_file, 'r') as f:
            connection_info = json.load(f)
        
        client = BlockingKernelClient()
        client.load_connection_info(connection_info)
        client.start_channels()
        client.wait_for_ready(timeout=timeout)
        return client
        
    except Exception as e:
        print(f"Error connecting to kernel: {e}")
        return None

def execute_code(client, code):
    """Execute code in the kernel and return output."""
    msg_id = client.execute(code)
    output = []
    errors = []
    
    while True:
        try:
            msg = client.get_iopub_msg(timeout=1)
            if msg['parent_header']['msg_id'] == msg_id:
                if msg['msg_type'] == 'stream':
                    output.append(msg['content']['text'])
                elif msg['msg_type'] == 'execute_result':
                    output.append(msg['content']['data']['text/plain'])
                elif msg['msg_type'] == 'error':
                    # Capture full error information
                    error_content = msg['content']
                    error_output = []
                    error_output.append(f"ERROR: {error_content['ename']}: {error_content['evalue']}")
                    if 'traceback' in error_content:
                        error_output.append("\nFull Traceback:")
                        for line in error_content['traceback']:
                            # Remove ANSI escape codes for cleaner output
                            import re
                            clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line)
                            error_output.append(clean_line)
                    errors.append('\n'.join(error_output))
                elif msg['msg_type'] == 'status' and msg['content']['execution_state'] == 'idle':
                    break
        except:
            break
    
    # Combine output and errors
    result = ''.join(output)
    if errors:
        result += '\n' + '\n'.join(errors)
    
    return result

def inspect_history(client, num_entries=4):
    """Get In/Out history from kernel."""
    code = f"""
from IPython import get_ipython
ip = get_ipython()

if ip and hasattr(ip, 'user_ns'):
    In = ip.user_ns.get('In', [])
    Out = ip.user_ns.get('Out', {{}})
    
    print(f"=== KERNEL HISTORY ===")
    print(f"Total inputs: {{len(In)}}")
    print(f"Total outputs: {{len(Out)}}")
    
    print("\\n=== Last {num_entries} Inputs ===")
    for i in range(max(0, len(In)-{num_entries}), len(In)):
        if i < len(In) and In[i].strip():
            print(f"In[{{i}}]:")
            print(In[i])
            print("-" * 50)
    
    print("\\n=== Last {num_entries} Outputs ===")
    out_keys = sorted(Out.keys())[-{num_entries}:] if Out else []
    for key in out_keys:
        print(f"Out[{{key}}]:")
        print(repr(Out[key]))
        print("-" * 50)
else:
    print("No IPython instance found")
"""
    return execute_code(client, code)

def inspect_variables(client, var_name=None):
    """Get current variables from kernel."""
    if var_name:
        code = f"""
from IPython import get_ipython
ip = get_ipython()

if ip and hasattr(ip, 'user_ns'):
    if '{var_name}' in ip.user_ns:
        var = ip.user_ns['{var_name}']
        print(f"=== Variable: {var_name} ===")
        print(f"Type: {{type(var)}}")
        print(f"Value: {{repr(var)}}")
        print(f"Attributes: {{[attr for attr in dir(var) if not attr.startswith('_')]}}")
    else:
        print(f"Variable '{var_name}' not found")
else:
    print("No IPython instance found")
"""
    else:
        code = """
from IPython import get_ipython
ip = get_ipython()

if ip and hasattr(ip, 'user_ns'):
    user_vars = {k: type(v).__name__ for k, v in ip.user_ns.items() 
                 if not k.startswith('_') and k not in ['In', 'Out', 'get_ipython']}
    print("=== Current Variables ===")
    for var, var_type in sorted(user_vars.items()):
        print(f"  {var}: {var_type}")
else:
    print("No IPython instance found")
"""
    return execute_code(client, code)

def inspect_errors(client):
    """Look for recent errors in kernel history and show full tracebacks."""
    code = """
from IPython import get_ipython
import sys
import traceback

ip = get_ipython()

if ip and hasattr(ip, 'user_ns'):
    In = ip.user_ns.get('In', [])
    Out = ip.user_ns.get('Out', {})
    
    print("=== Recent Errors/Exceptions ===")
    error_found = False
    
    # Check the last exception info
    if hasattr(sys, 'last_type') and hasattr(sys, 'last_value') and hasattr(sys, 'last_traceback'):
        print("\\n=== Last Exception ===")
        print(f"Type: {sys.last_type.__name__}")
        print(f"Value: {sys.last_value}")
        print("\\nFull Traceback:")
        traceback.print_exception(sys.last_type, sys.last_value, sys.last_traceback)
        error_found = True
    
    # Look through recent inputs for error patterns
    print("\\n=== Recent Inputs with Potential Errors ===")
    for i, inp in enumerate(In[-10:], start=max(0, len(In)-10)):
        if any(keyword in inp.lower() for keyword in ['error', 'exception', 'traceback', 'failed']):
            print(f"In[{i}] (potential error):")
            print(inp)
            print("-" * 30)
            error_found = True
    
    # Check if there are any exception objects in namespace
    exceptions = {k: v for k, v in ip.user_ns.items() 
                 if isinstance(v, Exception)}
    if exceptions:
        print("\\n=== Exception Objects in Namespace ===")
        for name, exc in exceptions.items():
            print(f"{name}: {type(exc).__name__}: {exc}")
            error_found = True
    
    # Check for recent failed executions by looking at execution count gaps
    if hasattr(ip, 'execution_count'):
        print(f"\\n=== Execution Info ===")
        print(f"Current execution count: {ip.execution_count}")
        print(f"Total inputs: {len(In)}")
        print(f"Total outputs: {len(Out)}")
        
        # Look for missing outputs (could indicate errors)
        missing_outputs = []
        for i in range(1, len(In)):
            if i not in Out and In[i].strip():
                missing_outputs.append(i)
        
        if missing_outputs:
            print(f"\\nInputs without outputs (possible errors): {missing_outputs}")
            for i in missing_outputs[-5:]:  # Show last 5
                if i < len(In):
                    print(f"In[{i}]: {In[i][:100]}{'...' if len(In[i]) > 100 else ''}")
            error_found = True
    
    if not error_found:
        print("No obvious errors found in recent history")
        
else:
    print("No IPython instance found")
"""
    return execute_code(client, code)

def main():
    parser = argparse.ArgumentParser(
        description="Inspect running Jupyter kernels",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument('--history', type=int, default=4,
                       help='Number of In/Out entries to show (default: 4)')
    parser.add_argument('--var', '-v', type=str,
                       help='Inspect specific variable')
    parser.add_argument('--errors-only', '-e', action='store_true',
                       help='Show only errors and exceptions')
    parser.add_argument('--exec', '-x', type=str,
                       help='Execute custom code in kernel')
    parser.add_argument('--list-kernels', '-l', action='store_true',
                       help='List all available kernels')
    parser.add_argument('--kernel-index', '-k', type=int, default=0,
                       help='Use kernel at index (0=most recent, default: 0)')
    parser.add_argument('--timeout', '-t', type=int, default=5,
                       help='Connection timeout in seconds (default: 5)')
    
    args = parser.parse_args()
    
    # Find available kernels
    kernels = find_kernels()
    
    if not kernels:
        print("No Jupyter kernels found!")
        print("Make sure you have a running Jupyter session.")
        return
    
    if args.list_kernels:
        print("=== Available Kernels ===")
        for i, kernel in enumerate(kernels):
            mtime = os.path.getmtime(kernel)
            print(f"{i}: {os.path.basename(kernel)} (modified: {mtime})")
        return
    
    # Select kernel
    if args.kernel_index >= len(kernels):
        print(f"Kernel index {args.kernel_index} not available. Found {len(kernels)} kernels.")
        return
    
    kernel_file = kernels[args.kernel_index]
    print(f"Connecting to: {os.path.basename(kernel_file)}")
    
    # Connect to kernel
    client = connect_to_kernel(kernel_file, args.timeout)
    if not client:
        return
    
    try:
        # Execute requested inspection
        if args.exec:
            print("=== Custom Code Execution ===")
            result = execute_code(client, args.exec)
            print(result)
        
        elif args.errors_only:
            result = inspect_errors(client)
            print(result)
        
        elif args.var:
            result = inspect_variables(client, args.var)
            print(result)
        
        else:
            # Default: show history and variables
            result = inspect_history(client, args.history)
            print(result)
            
            print("\n" + "="*60 + "\n")
            
            result = inspect_variables(client)
            print(result)
    
    finally:
        client.stop_channels()

if __name__ == "__main__":
    main() 