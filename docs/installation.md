# Installation

## Requirements

- Python 3.10 or later
- pip or uv (recommended)

## Install from PyPI

The simplest way to install Attachments is from PyPI:

```bash
pip install attachments
```

Or using `uv` (faster):

```bash
uv pip install attachments
```

## Install with Optional Dependencies

### Extended File Format Support

For additional file formats (HEIF images, audio transcription, etc.):

```bash
pip install "attachments[extended]"
```

### Browser Automation

For web content extraction:

```bash
pip install "attachments[browser]"
```

### Documentation Tools

For building documentation and running notebooks:

```bash
pip install "attachments[docs]"
```

### All Features

To install everything:

```bash
pip install "attachments[all]"
```

## Development Installation

For development, clone the repository and install in editable mode:

```bash
git clone https://github.com/MaximeRivest/attachments.git
cd attachments
uv venv
uv pip install -e ".[dev,test,docs]"
```

## System Dependencies

Some features require system-level dependencies:

### PDF Processing
- Already included with PyMuPDF (no additional dependencies)

### Audio Processing
For audio transcription features:
- `ffmpeg` (for audio format conversion)

### Office Documents  
For advanced document conversion:
- LibreOffice (optional, for document conversion)

## Verify Installation

Test your installation:

```python
from attachments import Attachments

# Basic test
ctx = Attachments("README.md")
print(f"Loaded {len(ctx)} files")
print(f"Text length: {len(ctx.text)} characters")
```

## Troubleshooting

### Common Issues

**PyMuPDF Installation Issues**
If you encounter issues with PyMuPDF:
```bash
pip install --upgrade pip
pip install --no-cache-dir PyMuPDF
```

**Pillow Installation Issues**
For image processing issues:
```bash
pip install --upgrade Pillow
```

**Permission Errors**
Use `--user` flag for user-only installation:
```bash
pip install --user attachments
```

### Platform-Specific Notes

**macOS**
Install system dependencies with Homebrew:
```bash
brew install ffmpeg
```

**Ubuntu/Debian**
```bash
sudo apt-get update
sudo apt-get install ffmpeg libreoffice
```

**Windows**
- Download FFmpeg from https://ffmpeg.org/
- Install LibreOffice from https://www.libreoffice.org/

### Virtual Environments

Always recommended to use virtual environments:

**Using venv**
```bash
python -m venv attachments-env
source attachments-env/bin/activate  # Linux/macOS
# attachments-env\Scripts\activate  # Windows
pip install attachments
```

**Using uv (recommended)**
```bash
uv venv attachments-env
source attachments-env/bin/activate
uv pip install attachments
``` 