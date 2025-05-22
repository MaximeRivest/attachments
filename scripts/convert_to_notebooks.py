#!/usr/bin/env python3
"""
Convert Python tutorial scripts to Jupyter notebooks using jupytext.

This script processes Python files in docs/scripts/ and creates corresponding
.ipynb files in docs/examples/ with proper notebook metadata and MyST compatibility.
"""

import subprocess
import sys
import json
from pathlib import Path
from typing import Dict, Any

def install_jupytext():
    """Ensure jupytext is installed."""
    try:
        subprocess.run([sys.executable, "-m", "jupytext", "--version"], 
                      capture_output=True, check=True)
        print("✅ jupytext is available")
        return True
    except subprocess.CalledProcessError:
        print("❌ jupytext not found. Installing...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "jupytext"], 
                          check=True)
            print("✅ jupytext installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install jupytext: {e}")
            return False

def create_notebook_metadata(title: str, description: str = "") -> Dict[str, Any]:
    """Create notebook metadata for MyST and Jupyter."""
    return {
        "kernelspec": {
            "display_name": "Python 3 (ipykernel)",
            "language": "python",
            "name": "python3"
        },
        "language_info": {
            "codemirror_mode": {"name": "ipython", "version": 3},
            "file_extension": ".py",
            "mimetype": "text/x-python",
            "name": "python",
            "nbconvert_exporter": "python",
            "pygments_lexer": "ipython3",
            "version": "3.11.0"
        },
        "jupytext": {
            "formats": "ipynb,py:percent",
            "text_representation": {
                "extension": ".py",
                "format_name": "percent",
                "format_version": "1.3",
                "jupytext_version": "1.16.0"
            }
        }
    }

def convert_py_to_notebook(py_file: Path, output_dir: Path) -> Path:
    """Convert Python file to notebook using jupytext."""
    
    notebook_name = py_file.stem + ".ipynb"
    notebook_path = output_dir / notebook_name
    
    print(f"🔄 Converting {py_file.name} → {notebook_name}")
    
    # Read the Python file
    content = py_file.read_text(encoding='utf-8')
    
    # Add jupytext header if not present
    if not content.startswith("# ---") and not content.startswith("# %%"):
        title = py_file.stem.replace('_', ' ').title()
        if 'tutorial' in py_file.name.lower():
            title += " Tutorial"
        elif 'demo' in py_file.name.lower():
            title += " Demo"
            
        # Add percent format header
        header = f'''# %% [markdown]
# # {title}
#
# This notebook demonstrates the Attachments library's capabilities with our new modular architecture.

# %%
'''
        content = header + content
    
    # Write to temp file with percent format
    temp_py_path = output_dir / (py_file.stem + "_temp.py")
    temp_py_path.write_text(content, encoding='utf-8')
    
    try:
        # Convert using jupytext
        cmd = [
            sys.executable, "-m", "jupytext",
            "--to", "ipynb",
            "--output", str(notebook_path),
            str(temp_py_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"✅ Successfully converted {py_file.name}")
        
        # Clean up temp file
        temp_py_path.unlink()
        
        return notebook_path
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error converting {py_file.name}: {e.stderr}")
        if temp_py_path.exists():
            temp_py_path.unlink()
        raise

def create_demo_notebook(output_dir: Path) -> Path:
    """Create a comprehensive demo notebook showcasing the modular architecture."""
    
    notebook_path = output_dir / "modular_architecture_demo.ipynb"
    
    notebook_content = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# 🏗️ Modular Architecture Demo\n",
                    "\n",
                    "This notebook demonstrates the new **MIT-compatible** modular architecture of the Attachments library.\n",
                    "\n",
                    "## 🎯 Overview\n",
                    "\n",
                    "The library is now organized into modular components:\n",
                    "- **Loaders**: Load files into Python objects (PDF, CSV, Images)\n",
                    "- **Presenters**: Convert content to different formats (text, images, markdown)\n",
                    "- **Modifiers**: Transform and filter content (pages, sample, resize)\n",
                    "- **Adapters**: Format for specific APIs (OpenAI, Claude)\n",
                    "\n",
                    "## 📜 MIT License Compatibility\n",
                    "\n",
                    "- ✅ **Default**: `pypdf` (BSD) + `pypdfium2` (BSD/Apache)\n",
                    "- ⚠️ **Optional**: `PyMuPDF/fitz` (AGPL) - explicit opt-in only\n"
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "source": [
                    "# Import the modular components\n",
                    "from attachments.core import load, modify, present, adapt\n",
                    "from attachments import Attachments\n",
                    "\n",
                    "print(\"🔧 Attachments Modular Architecture Demo\")\n",
                    "print(\"=\" * 50)\n",
                    "print(\"🏗️  MIT-Compatible PDF Processing\")"
                ]
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## 📋 Available Components\n",
                    "\n",
                    "Let's see what components are auto-registered:"
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "source": [
                    "print(\"📋 Available Components:\")\n",
                    "print(f\"   Loaders: {[attr for attr in dir(load) if not attr.startswith('_')]}\")\n",
                    "print(f\"   Modifiers: {[attr for attr in dir(modify) if not attr.startswith('_')]}\")\n",
                    "print(f\"   Presenters: {[attr for attr in dir(present) if not attr.startswith('_')]}\")\n",
                    "print(f\"   Adapters: {[attr for attr in dir(adapt) if not attr.startswith('_')]}\")"
                ]
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## 🚀 High-Level Interface\n",
                    "\n",
                    "The easiest way to use Attachments is through the high-level interface:"
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "source": [
                    "# Use the high-level interface\n",
                    "# Note: Replace with an actual file path for real usage\n",
                    "try:\n",
                    "    ctx = Attachments(\"README.md\")  # Using README as example\n",
                    "    print(f\"✅ Files loaded: {len(ctx)}\")\n",
                    "    print(f\"✅ Total text length: {len(ctx.text)} characters\")\n",
                    "    print(f\"✅ Total images: {len(ctx.images)}\")\n",
                    "    \n",
                    "    # Show string representation\n",
                    "    print(\"\\n📄 Summary:\")\n",
                    "    print(ctx)\n",
                    "except Exception as e:\n",
                    "    print(f\"📝 Note: {e}\")\n",
                    "    print(\"This is expected if README.md is not available in the current path\")"
                ]
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## 🎯 Type-Safe Dispatch\n",
                    "\n",
                    "The modular architecture uses Python's type system for safe dispatch:"
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "source": [
                    "import pandas as pd\n",
                    "import numpy as np\n",
                    "\n",
                    "print(\"🎯 Type-Safe Dispatch Demo:\")\n",
                    "\n",
                    "# Create test data\n",
                    "df = pd.DataFrame({\"Feature\": [\"PDF Loading\", \"Image Generation\"], \"Status\": [\"✅ MIT License\", \"✅ BSD License\"]})\n",
                    "arr = np.array([1, 2, 3, 4, 5])\n",
                    "\n",
                    "# Multiple dispatch works automatically based on types\n",
                    "df_text = present.text(df)\n",
                    "df_markdown = present.markdown(df)\n",
                    "arr_markdown = present.markdown(arr)\n",
                    "\n",
                    "print(f\"   📊 DataFrame text: {len(df_text)} chars\")\n",
                    "print(f\"   📊 DataFrame markdown has tables: {'|' in df_markdown}\")\n",
                    "print(f\"   🔢 Array markdown has code blocks: {'```' in arr_markdown}\")\n",
                    "\n",
                    "# Show the actual markdown output\n",
                    "print(\"\\n📋 DataFrame as Markdown:\")\n",
                    "print(df_markdown[:200] + \"...\" if len(df_markdown) > 200 else df_markdown)"
                ]
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## 🔌 API Integration\n",
                    "\n",
                    "Easy integration with AI APIs:"
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "source": [
                    "# Demo API formatting (without actual files)\n",
                    "print(\"🔌 API Integration Demo:\")\n",
                    "\n",
                    "# Create a simple attachment for demo\n",
                    "import tempfile\n",
                    "with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:\n",
                    "    f.write(\"This is a demo text file for API integration.\")\n",
                    "    temp_file = f.name\n",
                    "\n",
                    "try:\n",
                    "    ctx = Attachments(temp_file)\n",
                    "    \n",
                    "    # Format for OpenAI\n",
                    "    openai_msgs = ctx.to_openai(\"Analyze this content\")\n",
                    "    print(f\"📤 OpenAI format: {len(openai_msgs)} messages\")\n",
                    "    \n",
                    "    # Format for Claude\n",
                    "    claude_msgs = ctx.to_claude(\"Analyze this content\")\n",
                    "    print(f\"📤 Claude format: {len(claude_msgs)} messages\")\n",
                    "    \n",
                    "    print(\"✅ API formatting successful!\")\n",
                    "    \n",
                    "except Exception as e:\n",
                    "    print(f\"⚠️  API demo: {e}\")\n",
                    "finally:\n",
                    "    # Clean up\n",
                    "    import os\n",
                    "    try:\n",
                    "        os.unlink(temp_file)\n",
                    "    except:\n",
                    "        pass"
                ]
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## 🏆 Architecture Benefits\n",
                    "\n",
                    "The new modular architecture provides:\n",
                    "\n",
                    "### ✅ **MIT License Compatibility**\n",
                    "- Default libraries are all MIT-compatible\n",
                    "- Optional AGPL components available with explicit opt-in\n",
                    "\n",
                    "### 🎯 **Type Safety** \n",
                    "- Components dispatch based on Python types\n",
                    "- Clear error messages for unsupported types\n",
                    "\n",
                    "### 🧩 **Modularity**\n",
                    "- Clean separation of concerns\n",
                    "- Each component has a single responsibility\n",
                    "\n",
                    "### 🔧 **Extensibility**\n",
                    "- Easy to add new components\n",
                    "- Auto-registration system\n",
                    "\n",
                    "### ⚡ **Performance**\n",
                    "- Only load what you need\n",
                    "- Efficient dispatch system\n",
                    "\n",
                    "---\n",
                    "\n",
                    "🔮 **Ready for new loaders, presenters, modifiers & adapters!**\n",
                    "\n",
                    "The architecture is designed to make adding new file formats and output targets as simple as writing a single decorated function."
                ]
            }
        ],
        "metadata": create_notebook_metadata(
            "Modular Architecture Demo",
            "Comprehensive demo of the new MIT-compatible modular architecture"
        ),
        "nbformat": 4,
        "nbformat_minor": 4
    }
    
    # Write the notebook
    with open(notebook_path, 'w', encoding='utf-8') as f:
        json.dump(notebook_content, f, indent=2, ensure_ascii=False)
    
    print(f"📓 Created demo notebook: {notebook_path.name}")
    return notebook_path

def main():
    """Main conversion function."""
    
    print("🔧 Jupyter Notebook Conversion Pipeline")
    print("=" * 50)
    
    # Ensure jupytext is available
    if not install_jupytext():
        return 1
    
    # Paths
    project_root = Path(__file__).parent.parent
    scripts_dir = project_root / "docs" / "scripts"
    examples_dir = project_root / "docs" / "examples"
    
    # Ensure output directory exists
    examples_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 Output directory: {examples_dir}")
    
    # Create the demo notebook first
    demo_path = create_demo_notebook(examples_dir)
    
    # Scripts to convert
    scripts_to_convert = [
        "openai_attachments_tutorial.py",
        "architecture_demonstration.py", 
        "atttachment_pipelines.py",
        "how_to_develop_plugins.py"
    ]
    
    converted_count = 0
    
    print(f"\n🔍 Looking for scripts in: {scripts_dir}")
    
    for script_name in scripts_to_convert:
        script_path = scripts_dir / script_name
        
        if not script_path.exists():
            print(f"⚠️  Script not found: {script_name}")
            continue
            
        try:
            notebook_path = convert_py_to_notebook(script_path, examples_dir)
            converted_count += 1
            
        except Exception as e:
            print(f"❌ Failed to convert {script_name}: {e}")
    
    print(f"\n🎉 Conversion Summary:")
    print(f"   📓 Demo notebook: ✅ Created")
    print(f"   📄 Scripts converted: {converted_count}")
    print(f"   📁 Notebooks saved to: {examples_dir}")
    
    # List created notebooks
    notebooks = list(examples_dir.glob("*.ipynb"))
    if notebooks:
        print(f"\n📚 Created Notebooks:")
        for nb in notebooks:
            print(f"   📓 {nb.name}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 