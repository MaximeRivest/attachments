import pytest
import os
# import sys # No longer needed
import shutil
from io import BytesIO
# import wave # No longer needed for dummy WAV creation here if we use pre-existing minimal.wav
# import struct # No longer needed for dummy WAV creation here
from PIL import Image, ImageDraw, ImageFont
import unittest # Keep if any test classes still use it as a base
import subprocess # For checking ffmpeg

# Ensure the project root is in sys.path # This block will be removed
# PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
# if PROJECT_ROOT not in sys.path:
#     sys.path.insert(0, PROJECT_ROOT)

from attachments import Attachments # This should now work due to pyproject.toml

# Optional imports for creating sample files
try:
    from pptx import Presentation
    from pptx.util import Inches
    print("conftest: Successfully imported Presentation and Inches from pptx.")
except ImportError:
    Presentation, Inches = None, None # type: ignore
    print("conftest: Warning: python-pptx not installed.")

try:
    import fitz as _fitz_module
    print("conftest: Successfully imported fitz as _fitz_module")
except ImportError:
    _fitz_module = None # type: ignore
    print("conftest: Warning: PyMuPDF (fitz) not imported.")

# Define paths to the test data directory and common sample files
TEST_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_data')
AUDIO_DIR = os.path.join(TEST_DATA_DIR, 'audio') # Kept for structure, though only one audio file used from TEST_DATA_DIR now

SAMPLE_PDF = os.path.join(TEST_DATA_DIR, 'sample.pdf')
GENERATED_MULTI_PAGE_PDF = os.path.join(TEST_DATA_DIR, 'multi_page.pdf')
SAMPLE_PPTX = os.path.join(TEST_DATA_DIR, 'sample.pptx')
SAMPLE_HTML = os.path.join(TEST_DATA_DIR, 'sample.html')
NON_EXISTENT_FILE = os.path.join(TEST_DATA_DIR, 'not_here.txt')
SAMPLE_PNG = os.path.join(TEST_DATA_DIR, 'sample.png')
SAMPLE_JPG = os.path.join(TEST_DATA_DIR, 'sample.jpg')
SAMPLE_HEIC = os.path.join(TEST_DATA_DIR, 'sample.heic') # Assumed to exist or be added
SAMPLE_DOCX = os.path.join(TEST_DATA_DIR, 'sample.docx') # Assumed to exist or be added
SAMPLE_ODT = os.path.join(TEST_DATA_DIR, 'sample.odt')   # Assumed to exist or be added

# Main WAV file for testing, as per user request (was USER_PROVIDED_WAV)
SAMPLE_AUDIO_WAV = os.path.join(TEST_DATA_DIR, 'sample_audio.wav') 

# --- Debugging: Print info about the installed 'attachments' package ---
import importlib.util
import site

print("--- Conftest: Debugging Package Location ---")
try:
    spec = importlib.util.find_spec("attachments")
    if spec and spec.origin:
        package_init_file = spec.origin
        package_dir = os.path.dirname(package_init_file)
        print(f"Found 'attachments' package __init__.py at: {package_init_file}")
        print(f"Inferred 'attachments' package directory: {package_dir}")
        if os.path.isdir(package_dir):
            print(f"Contents of {package_dir}:")
            for item in os.listdir(package_dir):
                print(f"  - {item}")
        else:
            print(f"Error: {package_dir} is not a directory.")
    elif spec and spec.submodule_search_locations:
        print(f"'attachments' is a namespace package. Locations: {spec.submodule_search_locations}")
        for loc in spec.submodule_search_locations:
            if os.path.isdir(loc):
                print(f"Contents of namespace location {loc}:")
                for item in os.listdir(loc):
                    print(f"  - {item}")
    else:
        print("Error: Could not find 'attachments' package specification or its location.")
except Exception as e:
    print(f"Error during package debug: {e}")
print("--- Conftest: End Debugging ---")
# --- End Debugging --- 

def create_multi_page_pdf(path, num_pages=5):
    # (Function content is the same)
    if os.path.exists(path) and os.path.getsize(path) > 0: return
    if _fitz_module is None: 
        print(f"conftest: PyMuPDF (_fitz_module) not available, cannot create {path}.")
        return
    try:
        doc = _fitz_module.open() 
        for i in range(num_pages):
            page = doc.new_page(); page.insert_text((50, 72), f"This is page {i+1} of {num_pages}.")
        doc.save(path); doc.close()
        print(f"conftest: Created {path} with {num_pages} pages for testing.")
    except Exception as e:
        print(f"conftest: Could not create multi-page PDF {path}: {e}")

# Global variable to cache ffmpeg check
_ffmpeg_checked = False
_ffmpeg_present = False

def is_ffmpeg_available():
    global _ffmpeg_checked, _ffmpeg_present
    if _ffmpeg_checked:
        return _ffmpeg_present
    try:
        # Try to run ffmpeg -version and check return code
        process = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=False)
        _ffmpeg_present = process.returncode == 0
    except FileNotFoundError:
        _ffmpeg_present = False # ffmpeg command not found
    except Exception:
        _ffmpeg_present = False # Any other error, assume not available
    _ffmpeg_checked = True
    if not _ffmpeg_present:
        print("\nINFO: ffmpeg not found or not runnable. Some audio conversion tests will be skipped.")
    return _ffmpeg_present

@pytest.fixture(scope="class", autouse=True)
def base_test_setup(request):
    cls = request.cls
    print(f"conftest: Running pytest fixture 'base_test_setup' for class {cls.__name__}")

    if not os.path.exists(TEST_DATA_DIR): os.makedirs(TEST_DATA_DIR, exist_ok=True)
    if not os.path.exists(AUDIO_DIR): os.makedirs(AUDIO_DIR, exist_ok=True)

    cls.test_output_dir = os.path.join(TEST_DATA_DIR, "test_outputs_conftest_fixture_base")
    if not os.path.exists(cls.test_output_dir): os.makedirs(cls.test_output_dir, exist_ok=True)

    # Sample PDF
    if not (os.path.exists(SAMPLE_PDF) and os.path.getsize(SAMPLE_PDF) > 0):
        if _fitz_module: 
            try:
                doc = _fitz_module.open(); page = doc.new_page(); page.insert_text((50, 72), "Hello PDF!"); doc.save(SAMPLE_PDF); doc.close()
                print(f"conftest: Fixture created {SAMPLE_PDF}.")
            except Exception as e:
                 print(f"conftest: Fixture warning: Could not create {SAMPLE_PDF}: {e}")
        else:
            print(f"conftest: Fixture warning: PyMuPDF (_fitz_module) not available for {SAMPLE_PDF}")
    cls.sample_pdf_exists = os.path.exists(SAMPLE_PDF) and os.path.getsize(SAMPLE_PDF) > 0
    if not cls.sample_pdf_exists: print(f"conftest: CRITICAL WARNING: {SAMPLE_PDF} missing or empty. Generation depends on PyMuPDF.")

    create_multi_page_pdf(GENERATED_MULTI_PAGE_PDF, 5)
    cls.generated_multi_page_pdf_exists = os.path.exists(GENERATED_MULTI_PAGE_PDF) and os.path.getsize(GENERATED_MULTI_PAGE_PDF) > 0
    if not cls.generated_multi_page_pdf_exists and _fitz_module is None:
        print(f"conftest: INFO: {GENERATED_MULTI_PAGE_PDF} could not be created because PyMuPDF (fitz) is not available.")
    elif not cls.generated_multi_page_pdf_exists:
        print(f"conftest: WARNING: {GENERATED_MULTI_PAGE_PDF} missing or empty despite PyMuPDF potentially being available.")

    # Sample PPTX
    if not (os.path.exists(SAMPLE_PPTX) and os.path.getsize(SAMPLE_PPTX) > 100):
        if Presentation is None or Inches is None: 
            print(f"conftest: Fixture: python-pptx not available for {SAMPLE_PPTX}.")
            cls.sample_pptx_exists = False
        else:
            try:
                if os.path.exists(SAMPLE_PPTX): os.remove(SAMPLE_PPTX)
                prs = Presentation(); slide_layout_title = prs.slide_layouts[0]; slide1 = prs.slides.add_slide(slide_layout_title)
                title1 = slide1.shapes.title; title1.text = "Slide 1 Title"
                slide_layout_content = prs.slide_layouts[1]; slide2 = prs.slides.add_slide(slide_layout_content)
                title2 = slide2.shapes.title; title2.text = "Slide 2 Title"; slide2.placeholders[1].text_frame.text = "Content for page 2"
                slide3 = prs.slides.add_slide(slide_layout_content); title3 = slide3.shapes.title; title3.text = "Slide 3 Title"; slide3.placeholders[1].text_frame.text = "Content for page 3"
                prs.save(SAMPLE_PPTX)
                print(f"conftest: Fixture created {SAMPLE_PPTX}.")
                cls.sample_pptx_exists = True
            except Exception as e:
                print(f"conftest: Fixture: Could not create {SAMPLE_PPTX}: {e}.")
                cls.sample_pptx_exists = False
    else:
        cls.sample_pptx_exists = True 

    if cls.sample_pptx_exists and Presentation is not None:
        try: Presentation(SAMPLE_PPTX)
        except Exception as e:
            print(f"conftest: Fixture warning: {SAMPLE_PPTX} could not be opened: {e}.")
            cls.sample_pptx_exists = False
    if not cls.sample_pptx_exists: print(f"conftest: CRITICAL WARNING: {SAMPLE_PPTX} missing or invalid. Generation depends on python-pptx.")

    # Sample HTML
    if not (os.path.exists(SAMPLE_HTML) and os.path.getsize(SAMPLE_HTML) > 0):
        try:
            with open(SAMPLE_HTML, "w") as f: f.write("<html><head><title>Sample HTML</title></head><body><h1>Main Heading</h1><p>This is a paragraph with <strong>strong emphasis</strong> and <em>italic text</em>. <a href=\"http://example.com\">Example Link</a></p><ul><li>First item</li><li>Second item</li></ul><script>console.log('test');</script></body></html>")
            print(f"conftest: Fixture created {SAMPLE_HTML}.")
        except Exception as e_html_create:
            print(f"conftest: Fixture: Could not create {SAMPLE_HTML}: {e_html_create}")
    cls.sample_html_exists = os.path.exists(SAMPLE_HTML) and os.path.getsize(SAMPLE_HTML) > 0
    if not cls.sample_html_exists: print(f"conftest: CRITICAL WARNING: {SAMPLE_HTML} missing or empty.")

    # PNG and JPG creation - Always recreate for consistency
    try: 
        if os.path.exists(SAMPLE_PNG): os.remove(SAMPLE_PNG)
        img_png = Image.new('RGB', (10, 10), color = 'red'); img_png.save(SAMPLE_PNG, 'PNG'); print(f"conftest: Fixture created {SAMPLE_PNG}.")
    except Exception as e_png: print(f"conftest: Fixture: Could not create {SAMPLE_PNG}: {e_png}")
    cls.sample_png_exists = os.path.exists(SAMPLE_PNG) and os.path.getsize(SAMPLE_PNG) > 0
    if not cls.sample_png_exists: print(f"conftest: CRITICAL WARNING: {SAMPLE_PNG} missing or empty.")
    
    try:
        if os.path.exists(SAMPLE_JPG): os.remove(SAMPLE_JPG)
        img_jpg = Image.new('RGB', (10, 10), color = 'blue'); img_jpg.save(SAMPLE_JPG, 'JPEG'); print(f"conftest: Fixture created {SAMPLE_JPG}.")
    except Exception as e_jpg: print(f"conftest: Fixture: Could not create {SAMPLE_JPG}: {e_jpg}")
    cls.sample_jpg_exists = os.path.exists(SAMPLE_JPG) and os.path.getsize(SAMPLE_JPG) > 0
    if not cls.sample_jpg_exists: print(f"conftest: CRITICAL WARNING: {SAMPLE_JPG} missing or empty.")
    
    cls.sample_heic_exists = os.path.exists(SAMPLE_HEIC) and os.path.getsize(SAMPLE_HEIC) > 0
    if not cls.sample_heic_exists: print(f"conftest: WARNING: {SAMPLE_HEIC} missing or empty. This file needs to be manually added to {TEST_DATA_DIR}.")

    # Audio files - Rely on sample_audio.wav as the primary WAV test file
    cls.sample_audio_wav_exists = os.path.exists(SAMPLE_AUDIO_WAV) and os.path.getsize(SAMPLE_AUDIO_WAV) > 0
    if not cls.sample_audio_wav_exists: print(f"conftest: CRITICAL WARNING: Main audio file {SAMPLE_AUDIO_WAV} missing or empty.")

    # DOCX and ODT - Rely on pre-existing files
    cls.sample_docx_exists = os.path.exists(SAMPLE_DOCX) and os.path.getsize(SAMPLE_DOCX) > 0
    if not cls.sample_docx_exists: print(f"conftest: WARNING: {SAMPLE_DOCX} missing or empty. This file needs to be manually added to {TEST_DATA_DIR}.")
    
    cls.sample_odt_exists = os.path.exists(SAMPLE_ODT) and os.path.getsize(SAMPLE_ODT) > 0
    if not cls.sample_odt_exists: print(f"conftest: WARNING: {SAMPLE_ODT} missing or empty. This file needs to be manually added to {TEST_DATA_DIR}.")

    cls.ffmpeg_available = is_ffmpeg_available()

class BaseTestSetup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # ... (existing setUpClass content)
        cls.ffmpeg_available = is_ffmpeg_available()

    def skipTestIfNoFFmpeg(self):
        if not self.ffmpeg_available:
            self.skipTest("ffmpeg not available, skipping audio conversion test.")

