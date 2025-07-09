from .core import Attachment
import re
import os
import glob

# --- ENHANCED MATCHERS ---
# These matchers now check file extensions, Content-Type headers, and magic numbers
# This makes them work seamlessly with both file paths and URL responses

def url_match(att: 'Attachment') -> bool:
    """Check if the attachment path looks like a URL."""
    url_pattern = r'^https?://'
    return bool(re.match(url_pattern, att.path))

def webpage_match(att: 'Attachment') -> bool:
    """Check if the attachment is a webpage URL (not a downloadable file)."""
    if not att.path.startswith(('http://', 'https://')):
        return False

    # Exclude URLs that end with file extensions (those go to url_to_response + morphing)
    file_extensions = ['.pdf', '.pptx', '.ppt', '.docx', '.doc', '.xlsx', '.xls',
                      '.csv', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.zip',
                      '.svg', '.svgz', '.eps', '.epsf', '.epsi',  # Vector graphics
                      '.heic', '.heif', '.webp']  # Additional image formats

    return not any(att.path.lower().endswith(ext) for ext in file_extensions)

def csv_match(att: 'Attachment') -> bool:
    """Enhanced CSV matcher: checks file extension, Content-Type, and magic numbers."""
    # File extension check
    if att.path.endswith('.csv'):
        return True

    # Content-Type check for URL responses
    if 'text/csv' in att.content_type:
        return True

    # Magic number check (CSV files often start with headers)
    if att.has_content:
        text_sample = att.get_text_sample(200)
        if text_sample and ',' in text_sample and '\n' in text_sample:
            lines = text_sample.split('\n')[:2]
            if len(lines) >= 1 and lines[0].count(',') >= 1:
                return True

    return False

def pdf_match(att: 'Attachment') -> bool:
    """Enhanced PDF matcher: checks file extension, Content-Type, and magic numbers."""
    # File extension check
    if att.path.endswith('.pdf'):
        return True

    # Content-Type check for URL responses
    if 'pdf' in att.content_type:
        return True

    # Magic number check (PDF files start with %PDF)
    if att.has_content and att.has_magic_signature(b'%PDF'):
        return True

    return False

def pptx_match(att: 'Attachment') -> bool:
    """Enhanced PowerPoint matcher: checks file extension, Content-Type, and magic numbers."""
    # File extension check
    if att.path.endswith(('.pptx', '.ppt')):
        return True

    # Content-Type check for URL responses
    if any(x in att.content_type for x in ['powerpoint', 'presentation', 'vnd.ms-powerpoint']):
        return True

    # Magic number check (ZIP-based Office files start with PK and contain ppt/)
    if att.has_content:
        if att.has_magic_signature(b'PK') and att.contains_in_content(b'ppt/'):
            return True

    return False

def docx_match(att: 'Attachment') -> bool:
    """Enhanced Word matcher: checks file extension, Content-Type, and magic numbers."""
    # File extension check
    if att.path.endswith(('.docx', '.doc')):
        return True

    # Content-Type check for URL responses
    if any(x in att.content_type for x in ['msword', 'document', 'wordprocessingml']):
        return True

    # Magic number check (ZIP-based Office files start with PK and contain word/)
    if att.has_content:
        if att.has_magic_signature(b'PK') and att.contains_in_content(b'word/'):
            return True

    return False

def excel_match(att: 'Attachment') -> bool:
    """Enhanced Excel matcher: checks file extension, Content-Type, and magic numbers."""
    # File extension check
    if att.path.endswith(('.xlsx', '.xls')):
        return True

    # Content-Type check for URL responses
    if any(x in att.content_type for x in ['excel', 'spreadsheet', 'vnd.ms-excel']):
        return True

    # Magic number check (ZIP-based Office files start with PK and contain xl/)
    if att.has_content:
        if att.has_magic_signature(b'PK') and att.contains_in_content(b'xl/'):
            return True

    return False

def image_match(att: 'Attachment') -> bool:
    """Enhanced image matcher: checks file extension, Content-Type, and magic numbers."""
    # File extension check
    if att.path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.heif', '.webp')):
        return True

    # Content-Type check for URL responses
    if att.content_type.startswith('image/'):
        return True

    # Magic number check for common image formats
    if att.has_content:
        image_signatures = [
            b'\xff\xd8\xff',  # JPEG
            b'\x89PNG',       # PNG
            b'GIF8',          # GIF
            b'BM',            # BMP
        ]
        if att.has_magic_signature(image_signatures):
            return True

        # Special case for WebP (RIFF format with WEBP)
        if att.has_magic_signature(b'RIFF') and att.contains_in_content(b'WEBP', max_search_bytes=20):
            return True

    return False

def text_match(att: 'Attachment') -> bool:
    """Enhanced text matcher: checks file extension, Content-Type, and content analysis."""
    # File extension check - comprehensive list of text-based file extensions
    text_extensions = (
        # Plain text and documentation
        '.txt', '.text', '.asc', '.rtf', '.md', '.markdown', '.mdown', '.mkd', '.mdx',
        '.rst', '.rest', '.asciidoc', '.adoc', '.org', '.tex', '.latex',

        # Programming languages
        '.py', '.pyw', '.pyi', '.js', '.mjs', '.jsx', '.ts', '.tsx', '.java', '.class',
        '.c', '.h', '.cpp', '.cc', '.cxx', '.hpp', '.cs', '.php', '.rb', '.go', '.rs',
        '.swift', '.kt', '.scala', '.clj', '.hs', '.elm', '.dart', '.lua', '.pl', '.pm',
        '.r', '.R', '.m', '.f', '.f90', '.f95', '.pas', '.vb', '.vbs', '.ps1', '.psm1',
        '.sh', '.bash', '.zsh', '.fish', '.tcl', '.awk', '.sed',

        # Web technologies
        '.html', '.htm', '.xhtml', '.xml', '.xsl', '.xslt', '.css', '.scss', '.sass',
        '.less', '.stylus', '.svg', '.vue', '.svelte', '.jsp', '.asp', '.aspx', '.php',
        '.qmd',

        # Data formats
        '.json', '.jsonl', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.properties',
        '.env', '.dotenv', '.csv', '.tsv', '.dsv', '.sql', '.ddl', '.dml',

        # Configuration and build files
        '.makefile', '.dockerfile', '.dockerignore', '.gitignore', '.gitattributes',
        '.editorconfig', '.eslintrc', '.prettierrc', '.babelrc', '.npmrc', '.yarnrc',
        '.requirements', '.pipfile', '.poetry', '.pyproject', '.setup', '.manifest',
        '.cmake', '.gradle', '.maven', '.sbt', '.ant', '.rake', '.gulp', '.grunt',

        # Log and output files
        '.log', '.out', '.err', '.trace', '.debug', '.info', '.warn', '.error',

        # Miscellaneous text formats
        '.patch', '.diff', '.rej', '.orig', '.backup', '.bak', '.tmp', '.temp',
        '.include', '.import', '.template', '.tmpl', '.snippet', '.frag', '.vert',
        '.plist', '.strings', '.po', '.pot', '.mo', '.resx', '.resources',
    )

    if att.path.lower().endswith(text_extensions):
        return True

    # Content-Type check for URL responses
    if (att.content_type.startswith('text/') or
        'json' in att.content_type or
        'xml' in att.content_type):
        return True

    # Content analysis for text files
    if att.has_content and att.is_likely_text():
        return True

    return False

def svg_match(att: 'Attachment') -> bool:
    """Enhanced SVG matcher: checks file extension, Content-Type, and SVG content signatures."""
    # File extension check
    if att.path.lower().endswith(('.svg', '.svgz')):
        return True

    # Content-Type check for URL responses
    if 'svg' in att.content_type or att.content_type == 'image/svg+xml':
        return True

    # Content analysis for SVG files (check for SVG root element)
    if att.has_content:
        text_sample = att.get_text_sample(500)
        if text_sample and '<svg' in text_sample.lower() and 'xmlns' in text_sample.lower():
            return True

    return False

def eps_match(att: 'Attachment') -> bool:
    """Enhanced EPS matcher: checks file extension, Content-Type, and EPS content signatures."""
    # File extension check
    if att.path.lower().endswith(('.eps', '.epsf', '.epsi')):
        return True

    # Content-Type check for URL responses
    if any(x in att.content_type for x in ['postscript', 'eps', 'application/postscript']):
        return True

    # Content analysis for EPS files (check for EPS header)
    if att.has_content:
        text_sample = att.get_text_sample(200)
        if text_sample:
            # EPS files typically start with %!PS-Adobe and contain %%BoundingBox
            if (text_sample.startswith('%!PS-Adobe') or
                ('%%BoundingBox:' in text_sample and '%!' in text_sample)):
                return True

    return False

def zip_match(att: 'Attachment') -> bool:
    """Enhanced ZIP matcher: checks file extension and magic numbers."""
    # File extension check
    if att.path.lower().endswith('.zip'):
        return True

    # Magic number check (ZIP files start with PK, but exclude Office formats)
    if att.has_content:
        if (att.has_magic_signature(b'PK') and
            not att.contains_in_content([b'word/', b'ppt/', b'xl/'])):
            return True

    return False

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
