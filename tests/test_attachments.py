import unittest
import os
from attachments import Attachments, PDFParser, PPTXParser, DefaultXMLRenderer, HTMLParser
from attachments.exceptions import ParsingError
from attachments.utils import parse_index_string # For potential direct tests if needed
import subprocess
from PIL import Image
import re

# Define the path to the test data directory
TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), 'test_data')
SAMPLE_PDF = os.path.join(TEST_DATA_DIR, 'sample.pdf') # Single page: "Hello PDF!"
SAMPLE_PPTX = os.path.join(TEST_DATA_DIR, 'sample.pptx') # 3 slides: "Slide 1 Title", "Content for page 2", "Slide 3 Title"
GENERATED_MULTI_PAGE_PDF = os.path.join(TEST_DATA_DIR, 'multi_page.pdf')
SAMPLE_HTML = os.path.join(TEST_DATA_DIR, 'sample.html') # Added for HTML tests
NON_EXISTENT_FILE = os.path.join(TEST_DATA_DIR, 'not_here.txt')
SAMPLE_PNG = os.path.join(TEST_DATA_DIR, 'sample.png') # Added for PNG tests
SAMPLE_JPG = os.path.join(TEST_DATA_DIR, 'sample.jpg') # Added for JPG tests
SAMPLE_HEIC = os.path.join(TEST_DATA_DIR, 'sample.heic') # Added for HEIC tests

# Helper to create a multi-page PDF for testing PDF indexing
def create_multi_page_pdf(path, num_pages=5):
    if os.path.exists(path):
        return
    try:
        import fitz # PyMuPDF
        doc = fitz.open() # New PDF
        for i in range(num_pages):
            page = doc.new_page()
            page.insert_text((50, 72), f"This is page {i+1} of {num_pages}.")
        doc.save(path)
        doc.close()
        print(f"Created {path} with {num_pages} pages for testing.")
    except Exception as e:
        print(f"Could not create multi-page PDF {path}: {e}")

class TestAttachmentsIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Ensure sample PDF exists
        if not os.path.exists(SAMPLE_PDF):
            # Create a simple one if missing (content specific to existing tests)
            try:
                import fitz
                doc = fitz.open()
                page = doc.new_page()
                page.insert_text((50, 72), "Hello PDF!")
                doc.save(SAMPLE_PDF)
                doc.close()
                print(f"Created {SAMPLE_PDF} for testing.")
            except Exception as e:
                 print(f"Warning: Could not create {SAMPLE_PDF}. PDF tests might be limited: {e}")
        
        # Create multi-page PDF for indexing tests
        create_multi_page_pdf(GENERATED_MULTI_PAGE_PDF, 5) # Creates a 5-page PDF

        # Generate the sample PPTX for tests (3 slides expected by current tests)
        try:
            script_path = os.path.join(TEST_DATA_DIR, "generate_test_pptx.py")
            if not os.path.exists(script_path):
                raise FileNotFoundError(f"generate_test_pptx.py not found at {script_path}")
            
            print(f"Attempting to run {script_path} in {TEST_DATA_DIR}...")
            result = subprocess.run(
                ["python3", script_path],
                check=True, capture_output=True, text=True, cwd=TEST_DATA_DIR
            )
            print(f"generate_test_pptx.py stdout: {result.stdout.strip()}")
            if result.stderr:
                print(f"generate_test_pptx.py stderr: {result.stderr.strip()}")
            
            if not os.path.exists(SAMPLE_PPTX):
                 raise FileNotFoundError(f"{SAMPLE_PPTX} was not created by generate_test_pptx.py")
            print(f"{SAMPLE_PPTX} generated successfully.")
            cls.sample_pptx_exists = True

        except Exception as e:
            print(f"Could not create or verify sample.pptx: {e}. PPTX-dependent tests may be skipped or fail.")
            cls.sample_pptx_exists = False
        
        if cls.sample_pptx_exists:
            try:
                from pptx import Presentation
                Presentation(SAMPLE_PPTX) # Try to open
                print(f"{SAMPLE_PPTX} is readable by python-pptx.")
            except Exception as e:
                print(f"Warning: Generated {SAMPLE_PPTX} could not be reliably opened by python-pptx: {e}. PPTX tests might fail.")
                cls.sample_pptx_exists = False

        # Ensure sample HTML exists (it's static, so just check)
        if not os.path.exists(SAMPLE_HTML):
            # This is unexpected as it should be committed with the tests
            print(f"CRITICAL WARNING: {SAMPLE_HTML} not found. HTML tests will fail or be skipped.")
            # Optionally create a dummy one, but better if it's the specific test file
            try:
                with open(SAMPLE_HTML, "w") as f:
                    f.write("<html><head><title>Dummy</title></head><body><p>Fallback HTML</p></body></html>")
                print(f"Created a fallback {SAMPLE_HTML} as it was missing.")
            except Exception as e_html_create:
                print(f"Could not create fallback {SAMPLE_HTML}: {e_html_create}")
        cls.sample_html_exists = os.path.exists(SAMPLE_HTML)

        # Ensure sample images exist
        cls.sample_png_exists = os.path.exists(SAMPLE_PNG)
        cls.sample_jpg_exists = os.path.exists(SAMPLE_JPG)
        cls.sample_heic_exists = os.path.exists(SAMPLE_HEIC)
        if not cls.sample_png_exists or not cls.sample_jpg_exists:
            print(f"Warning: Sample images (sample.png or sample.jpg) not found. Attempting to create them.")
            try:
                # Attempt to run the creation script if images are missing
                img_creation_script_path = os.path.join(TEST_DATA_DIR, "create_sample_images.py")
                if os.path.exists(img_creation_script_path):
                    subprocess.run(["python3", img_creation_script_path], check=True, cwd=TEST_DATA_DIR, capture_output=True)
                    cls.sample_png_exists = os.path.exists(SAMPLE_PNG)
                    cls.sample_jpg_exists = os.path.exists(SAMPLE_JPG)
                    cls.sample_heic_exists = os.path.exists(SAMPLE_HEIC)
                    if cls.sample_png_exists and cls.sample_jpg_exists:
                        print("Successfully created sample images using create_sample_images.py.")
                    else:
                        print("Failed to create sample images using script.")
                else:
                    print(f"create_sample_images.py not found at {img_creation_script_path}.")
            except Exception as e_img_create:
                print(f"Could not create sample images: {e_img_create}")
        
        if not cls.sample_png_exists:
            print(f"CRITICAL WARNING: {SAMPLE_PNG} is still missing. PNG image tests will fail or be skipped.")
        if not cls.sample_jpg_exists:
            print(f"CRITICAL WARNING: {SAMPLE_JPG} is still missing. JPG image tests will fail or be skipped.")
        if not cls.sample_heic_exists:
            print(f"CRITICAL WARNING: {SAMPLE_HEIC} is missing. HEIC image tests will fail or be skipped.")

    def test_initialize_attachments_with_pdf(self):
        if not os.path.exists(SAMPLE_PDF):
            self.skipTest(f"{SAMPLE_PDF} not found.")
        atts = Attachments(SAMPLE_PDF)
        self.assertEqual(len(atts.attachments_data), 1)
        self.assertEqual(atts.attachments_data[0]['type'], 'pdf')
        self.assertIn("Hello PDF!", atts.attachments_data[0]['text'])
        self.assertEqual(atts.attachments_data[0]['num_pages'], 1)
        self.assertEqual(atts.attachments_data[0]['indices_processed'], [1])

    def test_initialize_attachments_with_pptx(self):
        if not hasattr(self, 'sample_pptx_exists') or not self.sample_pptx_exists:
            self.skipTest(f"Skipping PPTX test as {SAMPLE_PPTX} is not available or readable.")
        atts = Attachments(SAMPLE_PPTX)
        self.assertEqual(len(atts.attachments_data), 1)
        self.assertEqual(atts.attachments_data[0]['type'], 'pptx')
        self.assertIn("Slide 1 Title", atts.attachments_data[0]['text'])
        self.assertIn("Content for page 2", atts.attachments_data[0]['text'])
        self.assertIn("Slide 3 Title", atts.attachments_data[0]['text'])
        self.assertEqual(atts.attachments_data[0]['num_slides'], 3)

    def test_initialize_attachments_with_html(self):
        if not self.sample_html_exists:
            self.skipTest(f"{SAMPLE_HTML} not found.")
        
        atts = Attachments(SAMPLE_HTML)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'html')
        self.assertEqual(data['file_path'], SAMPLE_HTML)
        self.assertIn("# Main Heading", data['text']) # html2text usually converts h1 to #
        self.assertIn("This is a paragraph", data['text'])
        self.assertIn("**strong emphasis**", data['text']) # Strong to markdown bold
        self.assertIn("_italic text_", data['text'])     # Em to markdown italic (using underscores)
        self.assertIn("[Example Link](http://example.com)", data['text'])
        self.assertIn("* First item", data['text']) # ul/li to markdown list
        self.assertNotIn("<script>", data['text']) # Script tags should be ignored by default by html2text
        self.assertNotIn("console.log", data['text'])
        # Check for indices_processed, should be present but likely None or empty for HTML initially
        # Depending on HTMLParser's return, it might not have 'indices_processed' or 'num_pages/slides'
        # For now, let's assert they are not present, or adapt if HTMLParser adds them.
        self.assertIsNone(data.get('indices_processed')) # HTMLParser doesn't add it
        self.assertIsNone(data.get('num_pages'))
        self.assertIsNone(data.get('num_slides'))

    def test_initialize_attachments_with_png(self):
        if not self.sample_png_exists:
            self.skipTest(f"{SAMPLE_PNG} not found.")
        atts = Attachments(SAMPLE_PNG)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'png')
        self.assertEqual(data['file_path'], SAMPLE_PNG)
        self.assertIn("[Image: sample.png (original: PNG RGB) -> processed to 1x1 for output as jpeg]", data['text'])
        self.assertEqual(data['width'], 1)
        self.assertEqual(data['height'], 1)
        self.assertTrue('image_object' in data)
        from PIL import Image
        self.assertIsInstance(data['image_object'], Image.Image)

    def test_initialize_attachments_with_jpeg(self):
        if not self.sample_jpg_exists:
            self.skipTest(f"{SAMPLE_JPG} not found.")
        atts = Attachments(SAMPLE_JPG)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'jpeg')
        self.assertEqual(data['file_path'], SAMPLE_JPG)
        self.assertIn("[Image: sample.jpg (original: JPEG RGB) -> processed to 1x1 for output as jpeg]", data['text'])
        self.assertEqual(data['width'], 1)
        self.assertEqual(data['height'], 1)
        self.assertTrue('image_object' in data)
        from PIL import Image
        self.assertIsInstance(data['image_object'], Image.Image)

    def test_initialize_attachments_with_heic(self):
        if not self.sample_heic_exists:
            self.skipTest(f"{SAMPLE_HEIC} not found.")
        atts = Attachments(SAMPLE_HEIC)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'heic') # Or 'heif' depending on pillow-heif's primary format reported
        self.assertEqual(data['file_path'], SAMPLE_HEIC)
        # Pillow-heif might report original_format as HEIF. We should verify actual output.
        # Example assertion: self.assertIn(f"[Image: sample.heic (original: HEIF ", data['text'])
        self.assertTrue(data['text'].startswith(f"[Image: {os.path.basename(SAMPLE_HEIC)} (original: HEIF")) # HEIF is common for .heic
        self.assertTrue('image_object' in data)
        self.assertIsInstance(data['image_object'], Image.Image)
        # Verify some default dimensions are present (actual values depend on sample.heic)
        self.assertTrue(data['width'] > 0)
        self.assertTrue(data['height'] > 0)
        self.assertEqual(data['original_format'].upper(), 'HEIF') # pillow-heif usually reports HEIF

    def test_render_method_xml_explicitly_for_pptx(self):
        if not hasattr(self, 'sample_pptx_exists') or not self.sample_pptx_exists:
            self.skipTest(f"Skipping PPTX XML render test as {SAMPLE_PPTX} is not available or readable.")
        atts = Attachments(SAMPLE_PPTX)
        xml_output = atts.render('xml') # Explicitly render as XML
        self.assertTrue(xml_output.startswith("<attachments>"))
        self.assertTrue(xml_output.endswith("</attachments>"))
        self.assertIn('<attachment id="pptx1" type="pptx">', xml_output)
        self.assertIn("<meta name=\"num_slides\" value=\"3\" />", xml_output)
        self.assertIn("Slide 1 Title", xml_output) # Assuming PlainTextRenderer output for PPTX text is used in XML
        self.assertIn("Content for page 3", xml_output)

    def test_render_method_default_xml_with_html(self):
        if not self.sample_html_exists:
            self.skipTest(f"{SAMPLE_HTML} not found.")
        atts = Attachments(SAMPLE_HTML)
        xml_output = atts.render('xml') # Explicitly render as XML
        self.assertTrue(xml_output.startswith("<attachments>"))
        self.assertTrue(xml_output.endswith("</attachments>"))
        self.assertIn('<attachment id="html1" type="html">', xml_output)
        # Check that some Markdown (from html2text) is present in the content
        # html2text might escape some characters for XML, so be careful with assertions
        # For example, '# Main Heading' will be in the text content.
        # DefaultXMLRenderer will escape < > & if they appear in markdown from html2text
        self.assertIn("# Main Heading", xml_output) 
        self.assertIn("**strong emphasis**", xml_output)
        self.assertIn("</content>", xml_output)
        self.assertIn("</attachment>", xml_output)

    def test_initialize_with_multiple_files(self):
        if not (os.path.exists(SAMPLE_PDF) and hasattr(self, 'sample_pptx_exists') and self.sample_pptx_exists):
            self.skipTest(f"Skipping multi-file test as {SAMPLE_PDF} or {SAMPLE_PPTX} is not available/readable.")
        atts = Attachments(SAMPLE_PDF, SAMPLE_PPTX)
        self.assertEqual(len(atts.attachments_data), 2)
        self.assertEqual(atts.attachments_data[0]['type'], 'pdf')
        self.assertEqual(atts.attachments_data[1]['type'], 'pptx')

    def test_initialize_with_multiple_files_including_html(self):
        if not (os.path.exists(SAMPLE_PDF) and self.sample_html_exists):
            self.skipTest(f"Skipping multi-file HTML test as {SAMPLE_PDF} or {SAMPLE_HTML} is not available.")
        atts = Attachments(SAMPLE_PDF, SAMPLE_HTML)
        self.assertEqual(len(atts.attachments_data), 2)
        pdf_data = atts.attachments_data[0] if atts.attachments_data[0]['type'] == 'pdf' else atts.attachments_data[1]
        html_data = atts.attachments_data[0] if atts.attachments_data[0]['type'] == 'html' else atts.attachments_data[1]
        
        self.assertEqual(pdf_data['type'], 'pdf')
        self.assertEqual(html_data['type'], 'html')
        self.assertIn("Hello PDF!", pdf_data['text'])
        self.assertIn("# Main Heading", html_data['text'])

    def test_string_representation_xml(self):
        if not os.path.exists(SAMPLE_PDF):
            self.skipTest(f"{SAMPLE_PDF} not found.")
        atts = Attachments(SAMPLE_PDF)
        xml_output = atts.render('xml') # Check XML rendering explicitly
        self.assertTrue(xml_output.startswith("<attachments>"))
        self.assertTrue(xml_output.endswith("</attachments>"))
        self.assertIn('<attachment id="pdf1" type="pdf">', xml_output)
        self.assertIn("<meta name=\"num_pages\" value=\"1\" />", xml_output)
        self.assertIn("<content>\nHello PDF!\n    </content>", xml_output)

    def test_non_existent_file_skipped(self):
        atts = Attachments(NON_EXISTENT_FILE, SAMPLE_PDF if os.path.exists(SAMPLE_PDF) else NON_EXISTENT_FILE)
        # If PDF exists, count is 1, otherwise 0. Non-existent file is always skipped.
        expected_count = 1 if os.path.exists(SAMPLE_PDF) else 0 
        self.assertEqual(len(atts.attachments_data), expected_count)

    def test_unsupported_file_type_skipped(self):
        # Create a dummy unsupported file
        unsupported_file = os.path.join(TEST_DATA_DIR, "sample.xyz")
        with open(unsupported_file, "w") as f:
            f.write("this is an unsupported file type")
        
        atts = Attachments(unsupported_file, SAMPLE_PDF if os.path.exists(SAMPLE_PDF) else NON_EXISTENT_FILE)
        expected_count = 1 if os.path.exists(SAMPLE_PDF) else 0
        self.assertEqual(len(atts.attachments_data), expected_count)
        os.remove(unsupported_file)

    def test_parse_path_string(self):
        atts = Attachments() # Need an instance to access the method
        path1, indices1 = atts._parse_path_string("path/to/file.pdf")
        self.assertEqual(path1, "path/to/file.pdf")
        self.assertIsNone(indices1)

        path2, indices2 = atts._parse_path_string("file.pptx[:10]")
        self.assertEqual(path2, "file.pptx")
        self.assertEqual(indices2, ":10")

        path3, indices3 = atts._parse_path_string("another/doc.pdf[1,5,-1:]")
        self.assertEqual(path3, "another/doc.pdf")
        self.assertEqual(indices3, "1,5,-1:")
        
        path4, indices4 = atts._parse_path_string("noindices.txt[]") # Empty indices
        self.assertEqual(path4, "noindices.txt")
        self.assertEqual(indices4, "")

    def test_parse_path_string_with_indices(self):
        atts = Attachments() # Need an instance to access the method
        path, indices = atts._parse_path_string("file.pdf[1,2,-1:]")
        self.assertEqual(path, "file.pdf")
        self.assertEqual(indices, "1,2,-1:")

        path, indices = atts._parse_path_string("file.pptx[:N]")
        self.assertEqual(path, "file.pptx")
        self.assertEqual(indices, ":N")
        
        path, indices = atts._parse_path_string("file.txt")
        self.assertEqual(path, "file.txt")
        self.assertIsNone(indices)

        path, indices = atts._parse_path_string("file.txt[]") # Empty indices
        self.assertEqual(path, "file.txt")
        self.assertEqual(indices, "")

    # --- PDF Indexing Tests ---
    def test_pdf_indexing_single_page(self):
        if not os.path.exists(GENERATED_MULTI_PAGE_PDF):
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[2]") # Page 2 (0-indexed 1)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 2", data['text'])
        self.assertNotIn("This is page 1", data['text'])
        self.assertNotIn("This is page 3", data['text'])
        self.assertEqual(data['num_pages'], 5) # Total pages
        self.assertEqual(data['indices_processed'], [2])

    def test_pdf_indexing_range(self):
        if not os.path.exists(GENERATED_MULTI_PAGE_PDF):
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[2-4]") # Pages 2,3,4
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 2", data['text'])
        self.assertIn("This is page 3", data['text'])
        self.assertIn("This is page 4", data['text'])
        self.assertNotIn("This is page 1", data['text'])
        self.assertNotIn("This is page 5", data['text'])
        self.assertEqual(data['num_pages'], 5)
        self.assertEqual(data['indices_processed'], [2, 3, 4])

    def test_pdf_indexing_to_end_slice(self):
        if not os.path.exists(GENERATED_MULTI_PAGE_PDF):
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[4:]") # Pages 4,5
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 4", data['text'])
        self.assertIn("This is page 5", data['text'])
        self.assertNotIn("This is page 3", data['text'])
        self.assertEqual(data['num_pages'], 5)
        self.assertEqual(data['indices_processed'], [4, 5])

    def test_pdf_indexing_from_start_slice(self):
        if not os.path.exists(GENERATED_MULTI_PAGE_PDF):
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[:2]") # Pages 1,2
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 1", data['text'])
        self.assertIn("This is page 2", data['text'])
        self.assertNotIn("This is page 3", data['text'])
        self.assertEqual(data['num_pages'], 5)
        self.assertEqual(data['indices_processed'], [1, 2])

    def test_pdf_indexing_with_n(self):
        if not os.path.exists(GENERATED_MULTI_PAGE_PDF):
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[1,N]") # Pages 1 and 5 (for 5-page PDF)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 1", data['text'])
        self.assertIn("This is page 5", data['text'])
        self.assertNotIn("This is page 2", data['text'])
        self.assertNotIn("This is page 4", data['text'])
        self.assertEqual(data['num_pages'], 5)
        self.assertEqual(data['indices_processed'], [1, 5])

    def test_pdf_indexing_negative(self):
        if not os.path.exists(GENERATED_MULTI_PAGE_PDF):
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[-2:]") # Last 2 pages (4,5 for 5-page PDF)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 4", data['text'])
        self.assertIn("This is page 5", data['text'])
        self.assertNotIn("This is page 3", data['text'])
        self.assertEqual(data['num_pages'], 5)
        self.assertEqual(data['indices_processed'], [4, 5])

    def test_pdf_indexing_empty_result(self):
        if not os.path.exists(GENERATED_MULTI_PAGE_PDF):
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[99]") # Page 99 on a 5 page PDF
        self.assertEqual(len(atts.attachments_data), 1) # Attachment is still processed
        data = atts.attachments_data[0]
        self.assertEqual(data['text'], "") # No text extracted
        self.assertEqual(data['num_pages'], 5) # Total pages is still correct
        self.assertEqual(data['indices_processed'], []) # No pages processed

    # --- PPTX Indexing Tests (SAMPLE_PPTX has 3 slides) ---
    # Slide 1: "Slide 1 Title" and "This is the first slide."
    # Slide 2: "Slide 2 Title" and "Content for page 2."
    # Slide 3: "Slide 3 Title" and "The final slide."

    def test_pptx_indexing_single_slide(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not available/readable for PPTX indexing test.")
        atts = Attachments(f"{SAMPLE_PPTX}[2]") # Slide 2
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("Slide 2 Title", data['text'])
        self.assertIn("Content for page 2", data['text'])
        self.assertNotIn("Slide 1 Title", data['text'])
        self.assertNotIn("Slide 3 Title", data['text'])
        self.assertEqual(data['num_slides'], 3)
        self.assertEqual(data['indices_processed'], [2])

    def test_pptx_indexing_range(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not available/readable for PPTX indexing test.")
        atts = Attachments(f"{SAMPLE_PPTX}[1-2]") # Slides 1,2
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("Slide 1 Title", data['text'])
        self.assertIn("Slide 2 Title", data['text'])
        self.assertNotIn("Slide 3 Title", data['text'])
        self.assertEqual(data['num_slides'], 3)
        self.assertEqual(data['indices_processed'], [1, 2])

    def test_pptx_indexing_with_n(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not available/readable for PPTX indexing test.")
        atts = Attachments(f"{SAMPLE_PPTX}[1,N]") # Slides 1 and 3 (for 3-slide PPTX)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("Slide 1 Title", data['text'])
        self.assertIn("Slide 3 Title", data['text'])
        self.assertNotIn("Slide 2 Title", data['text'])
        self.assertEqual(data['num_slides'], 3)
        self.assertEqual(data['indices_processed'], [1, 3])

    def test_pptx_indexing_negative_slice(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not available/readable for PPTX indexing test.")
        atts = Attachments(f"{SAMPLE_PPTX}[-2:]") # Last 2 slides (2,3 for 3-slide PPTX)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("Slide 2 Title", data['text'])
        self.assertIn("Slide 3 Title", data['text'])
        self.assertNotIn("Slide 1 Title", data['text'])
        self.assertEqual(data['num_slides'], 3)
        self.assertEqual(data['indices_processed'], [2, 3])
    
    def test_pptx_indexing_empty_indices_string(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not available/readable for PPTX indexing test.")
        atts = Attachments(f"{SAMPLE_PPTX}[]") # Empty index string
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        # Should default to all slides if index string is empty but present
        # or be handled as an empty selection by parse_index_string.
        # parse_index_string(' ', 3) -> []
        # The parser logic: if indices_str is empty, pages_to_process_indices becomes range(num_total)
        # This needs to be consistent. Attachments._parse_path_string returns "" for "[]".
        # parsers.py: if indices ('' from Attachments) and isinstance(str) -> calls parse_index_string('', N) -> []
        # Then: if not pages_to_process_indices ('[]' is true) and num >0 and indices ('' is false here!) -> no!
        # else: (indices is '') -> pages_to_process_indices = list(range(num_total))
        # So, "[]" should process all pages.
        self.assertIn("Slide 1 Title", data['text'])
        self.assertIn("Slide 2 Title", data['text'])
        self.assertIn("Slide 3 Title", data['text'])
        self.assertEqual(data['num_slides'], 3)
        self.assertEqual(data['indices_processed'], [1, 2, 3])

    def test_image_transformations_resize(self):
        if not self.sample_png_exists:
            self.skipTest(f"{SAMPLE_PNG} not found for resize test.")
        atts = Attachments(f"{SAMPLE_PNG}[resize:50x75]")
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'png')
        self.assertTrue('image_object' in data)
        self.assertEqual(data['image_object'].width, 50)
        self.assertEqual(data['image_object'].height, 75)
        self.assertEqual(data['width'], 50) # Check metadata reflects transform
        self.assertEqual(data['height'], 75)
        self.assertIn("resize:50x75", data['text'])
        self.assertEqual(data['applied_operations'].get('resize'), (50,75))

    def test_image_transformations_rotate(self):
        if not self.sample_jpg_exists:
            self.skipTest(f"{SAMPLE_JPG} not found for rotate test.")
        # Original sample.jpg is 1x1. Rotating 90 deg should keep it 1x1.
        atts = Attachments(f"{SAMPLE_JPG}[rotate:90]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'jpeg')
        self.assertTrue('image_object' in data)
        self.assertEqual(data['image_object'].width, 1) # Dimensions may swap for non-square after 90/270 rotation
        self.assertEqual(data['image_object'].height, 1)
        self.assertEqual(data['width'], 1)
        self.assertEqual(data['height'], 1)
        self.assertIn("rotate:90", data['text'])
        self.assertEqual(data['applied_operations'].get('rotate'), 90)

    def test_image_transformations_resize_auto_height(self):
        if not self.sample_png_exists: # sample.png is 1x1
            self.skipTest(f"{SAMPLE_PNG} not found for resize test.")
        # Create a non-square image for this test to be meaningful
        temp_img_path = os.path.join(TEST_DATA_DIR, "temp_2x1.png")
        try:
            img = Image.new('RGB', (2, 1), color='green')
            img.save(temp_img_path, 'PNG')
            atts = Attachments(f"{temp_img_path}[resize:100xauto]")
            self.assertEqual(len(atts.attachments_data), 1)
            data = atts.attachments_data[0]
            self.assertEqual(data['image_object'].width, 100)
            self.assertEqual(data['image_object'].height, 50) # Original 2x1 -> 100x50
            self.assertEqual(data['applied_operations'].get('resize'), (100,None))
        finally:
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)

    def test_attachments_images_property_empty(self):
        atts = Attachments(SAMPLE_PDF) # Only a PDF
        self.assertEqual(atts.images, [])

    def test_attachments_images_property_single_png(self):
        if not self.sample_png_exists:
            self.skipTest(f"{SAMPLE_PNG} not found.")
        atts = Attachments(SAMPLE_PNG)
        self.assertEqual(len(atts.images), 1)
        b64_image = atts.images[0]
        # Default output for an RGB PNG (like our sample) is now JPEG as per ImageParser logic
        self.assertTrue(b64_image.startswith("data:image/jpeg;base64,"))
        # Basic check: decode and see if it resembles an image header (optional)
        import base64
        try:
            header = base64.b64decode(b64_image.split(',')[1])[:3] # JPEG SOI + APPx marker
            self.assertEqual(header, b'\xff\xd8\xff') 
        except Exception:
            self.fail("Base64 decoding or JPEG header check failed for PNG converted to JPEG.")

    def test_attachments_images_property_jpeg_output_format(self):
        if not self.sample_png_exists:
            self.skipTest(f"{SAMPLE_PNG} not found.")
        atts = Attachments(f"{SAMPLE_PNG}[format:jpeg,quality:70]")
        self.assertEqual(len(atts.images), 1)
        b64_image = atts.images[0]
        self.assertTrue(b64_image.startswith("data:image/jpeg;base64,"))
        self.assertEqual(atts.attachments_data[0]['output_format'], 'jpeg')
        self.assertEqual(atts.attachments_data[0]['output_quality'], 70)
        import base64
        try:
            header = base64.b64decode(b64_image.split(',')[1])[:3]
            self.assertEqual(header, b'\xff\xd8\xff') # JPEG SOI & APP0/APP1 marker start
        except Exception:
            self.fail("Base64 decoding or JPEG header check failed.")

    def test_attachments_images_property_multiple_images(self):
        files_to_test = []
        skipped_any = False
        if self.sample_png_exists: files_to_test.append(SAMPLE_PNG)
        else: skipped_any = True
        if self.sample_jpg_exists: files_to_test.append(SAMPLE_JPG)
        else: skipped_any = True
        if self.sample_heic_exists: files_to_test.append(SAMPLE_HEIC)
        else: skipped_any = True
        
        if skipped_any or not files_to_test:
            self.skipTest(f"One or more sample images (PNG, JPG, HEIC) not found for multiple image test.")

        atts = Attachments(*files_to_test)
        self.assertEqual(len(atts.images), len(files_to_test))
        # All images (RGB PNG, JPG, HEIC) will likely default to JPEG output by ImageParser logic
        # unless HEIC has alpha and PNG output is chosen by ImageParser.
        # For now, a general check:
        for img_b64 in atts.images:
            self.assertTrue(img_b64.startswith("data:image/")) # More general check

    def test_repr_markdown_output(self):
        paths_for_markdown = []
        has_pdf = False
        has_png = False
        has_heic = False

        if os.path.exists(SAMPLE_PDF):
            paths_for_markdown.append(SAMPLE_PDF)
            has_pdf = True
        if self.sample_png_exists:
            paths_for_markdown.append(f"{SAMPLE_PNG}[resize:20x20]")
            has_png = True
        if self.sample_heic_exists:
            paths_for_markdown.append(f"{SAMPLE_HEIC}[resize:25x25]")
            has_heic = True

        if not (has_pdf or has_png or has_heic): # If no files at all
            self.skipTest("No sample files available for markdown repr test.")
        if not paths_for_markdown: # Should be caught by above, but defensive
            atts = Attachments()
            self.assertIn("_No attachments processed._", atts._repr_markdown_())
            return
            
        atts = Attachments(*paths_for_markdown)
        markdown_output = atts._repr_markdown_()
        # print(f"DEBUG Markdown Output:\n{markdown_output}") # Keep for temp debugging if needed

        self.assertIn("### Attachments Summary", markdown_output)
        summary_part, gallery_part = markdown_output, ""
        if "\n### Image Previews" in markdown_output:
            parts = markdown_output.split("\n### Image Previews", 1)
            summary_part = parts[0]
            if len(parts) > 1: gallery_part = parts[1]
        
        # --- Test Summary Part --- 
        if has_pdf:
            self.assertIn(f"**ID:** `pdf1` (`pdf` from `{SAMPLE_PDF}`)", summary_part)
            self.assertIn("Hello PDF!", summary_part) 
            self.assertIn("Total Pages:** `1` (All processed)", summary_part)
            self.assertNotIn(f"![{os.path.basename(SAMPLE_PDF)}](data:image", summary_part) # No image tag for PDF here

        if has_png:
            png_id_match = re.search(r"\*\*ID:\*\* `(png\d+)` \(`png` from", summary_part)
            self.assertIsNotNone(png_id_match, "PNG ID line not found in summary")
            png_id = png_id_match.group(1) if png_id_match else "png_not_found"
            
            self.assertIn(f"(`png` from `{SAMPLE_PNG}[resize:20x20]`)", summary_part)
            self.assertIn("  - **Dimensions (after ops):** `20x20`", summary_part)
            self.assertIn("  - **Original Format:** `PNG`", summary_part)
            self.assertIn("  - **Original Mode:** `RGB`", summary_part) # Assuming RGB for sample PNG
            self.assertIn("  - **Operations:** `{'resize': (20, 20)}`", summary_part)
            self.assertIn("  - **Output as:** `jpeg`", summary_part)
            self.assertNotIn(f"![{os.path.basename(SAMPLE_PNG)}](data:image", summary_part) # No image tag here

        if has_heic:
            heic_id_match = re.search(r"\*\*ID:\*\* `(heic\d+)` \(`heic` from", summary_part)
            self.assertIsNotNone(heic_id_match, "HEIC ID line not found in summary")
            heic_id = heic_id_match.group(1) if heic_id_match else "heic_not_found"

            expected_heic_original_path_str = f"{SAMPLE_HEIC}[resize:25x25]"
            self.assertTrue(re.search(rf"\(`heic` from `{re.escape(expected_heic_original_path_str)}`\)", summary_part))
            self.assertIn(f"(`heic` from `{expected_heic_original_path_str}`)", summary_part)
            self.assertIn("  - **Dimensions (after ops):** `25x25`", summary_part) 
            self.assertIn("  - **Original Format:** `HEIF`", summary_part) # pillow-heif reports HEIF
            self.assertIn("  - **Original Mode:** `RGB`", summary_part) # Assuming RGB for sample HEIC after conversion by pillow-heif
            self.assertIn("  - **Operations:** `{'resize': (25, 25)}`", summary_part)
            self.assertIn("  - **Output as:** `jpeg`", summary_part)
            self.assertNotIn(f"![{os.path.basename(SAMPLE_HEIC)}](data:image", summary_part) # No image tag here
        
        # --- Test Gallery Part --- 
        if has_png or has_heic: # If there should be a gallery
            self.assertTrue(markdown_output.count("\n### Image Previews") <= 1, "Multiple Image Previews headers found") # ensure it is present if expected
            if not gallery_part and (has_png or has_heic):
                 self.fail("Image gallery expected but not found or incorrectly split")

            # Check for table structure for the gallery
            self.assertIn("| &nbsp; | &nbsp; | &nbsp; |", gallery_part) # Header with 3 columns
            self.assertIn("|---|---|---|", gallery_part)      # Header separator for 3 columns

            # Verify images are within table cells. This is a simplified check.
            # A more robust check would parse rows and cells.
            if has_png:
                self.assertIsNotNone(png_id_match, "PNG ID for gallery check not found earlier")
                # Check if the PNG image tag is within a table row context
                png_filename_escaped = re.escape(os.path.basename(SAMPLE_PNG))
                png_regex = rf"\|[^|]*\!\[{png_filename_escaped}\][^|]*data:image/jpeg;base64,[^|]*\|"
                self.assertTrue(re.search(png_regex, gallery_part), f"PNG image tag ({SAMPLE_PNG}) not found within a Markdown table cell structure in gallery. Regex: {png_regex}")
            
            if has_heic:
                self.assertIsNotNone(heic_id_match, "HEIC ID for gallery check not found earlier")
                # Check if the HEIC image tag is within a table row context
                heic_filename_escaped = re.escape(os.path.basename(SAMPLE_HEIC))
                heic_regex = rf"\|[^|]*\!\[{heic_filename_escaped}\][^|]*data:image/jpeg;base64,[^|]*\|"
                self.assertTrue(re.search(heic_regex, gallery_part), f"HEIC image tag ({SAMPLE_HEIC}) not found within a Markdown table cell structure in gallery. Regex: {heic_regex}")

        else: # No images, so no gallery part
            self.assertNotIn("\n### Image Previews", markdown_output)

        # Check for the main summary item separator, it should still exist in the summary_part if there are multiple items
        if (has_pdf and (has_png or has_heic)) or (has_png and has_heic): # if more than one summary item
            self.assertIn("\n---\n", summary_part)
        elif markdown_output.count("**ID:**") > 1: # Generic check if more than one item processed
             self.assertIn("\n---\n", summary_part)
        # If only one item, summary_part might not have '---' if it's the end of the summary_part. Let's be more specific.
        # The '---' is appended after *each* summary item. So it should be there if any item was processed for summary.
        if has_pdf or has_png or has_heic:
             self.assertTrue(summary_part.count("\n---\n") >= markdown_output.count("**ID:**") -1, "Separator count in summary part seems off.")

    def test_str_representation_default_is_xml(self):
        paths_for_xml_str = []
        if os.path.exists(SAMPLE_PDF): paths_for_xml_str.append(SAMPLE_PDF)
        if self.sample_png_exists: paths_for_xml_str.append(f"{SAMPLE_PNG}[resize:10x10]")
        if self.sample_heic_exists: paths_for_xml_str.append(f"{SAMPLE_HEIC}[resize:15x15,format:png]")

        if len(paths_for_xml_str) < 2:
            self.skipTest(f"Missing sample files for str representation XML test.")

        atts = Attachments(*paths_for_xml_str)
        output_str = str(atts)

        self.assertTrue(output_str.startswith("<attachments>"))
        self.assertTrue(output_str.endswith("</attachments>"))

        if SAMPLE_PDF in paths_for_xml_str:
            self.assertIn('<attachment id="pdf1" type="pdf">', output_str)
            self.assertIn("<meta name=\"num_pages\" value=\"1\" />", output_str)
            self.assertIn("<content>\nHello PDF!\n    </content>", output_str)

        if f"{SAMPLE_PNG}[resize:10x10]" in paths_for_xml_str:
            # Dynamically find png block or adjust id if order changes
            self.assertTrue(re.search(r'<attachment id="png\d+" type="png">', output_str))
            self.assertIn("[Image: sample.png (original: PNG RGB, ops: \"resize:10x10\") -&gt; processed to 10x10 for output as jpeg]", output_str)
            self.assertIn("<meta name=\"dimensions\" value=\"10x10\" />", output_str)
            self.assertIn("<meta name=\"original_format\" value=\"PNG\" />", output_str)
            self.assertIn("<meta name=\"applied_operations\" value=\"{'resize': (10, 10)}\" />", output_str) # Ensure closing /> is part of string

        if f"{SAMPLE_HEIC}[resize:15x15,format:png]" in paths_for_xml_str:
            self.assertTrue(re.search(r'<attachment id="heic\d+" type="heic">', output_str)) # Original type is heic
            expected_heic_ops_str_for_xml = "resize:15x15,format:png"
            # The text representation in XML content might have ops string XML escaped if it contained & < > "
            # For "resize:15x15,format:png" there are no such characters, so it should be direct.
            expected_heic_text_content_regex = rf""".*original: HEIF RGB, ops: \"{re.escape(expected_heic_ops_str_for_xml)}\".*"""
            self.assertTrue(re.search(expected_heic_text_content_regex, output_str))
            self.assertIn("<meta name=\"dimensions\" value=\"15x15\" />", output_str)
            self.assertIn("<meta name=\"original_format\" value=\"HEIF\" />", output_str) # From pillow-heif
            self.assertIn("<meta name=\"output_format_target\" value=\"png\" />", output_str)
            # Check parts of applied_operations string, ensure it's within the value attribute
            self.assertIn("value=\"{'resize': (15, 15), 'format': 'png'}\"", output_str)
    
    # Consider adding a specific test for HEIC XML metadata if more detail is needed beyond the str representation.
    # For instance, if HEIC has specific metadata we want to ensure is present.
    # For now, test_str_representation_default_is_xml covers its inclusion.

class TestAttachmentsIndexing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure necessary sample files are available (can reuse from TestAttachmentsIntegration)
        # This setup can be minimal if TestAttachmentsIntegration.setUpClass ensures files exist.
        # However, to be safe, explicitly check for files needed by indexing tests.
        cls.sample_pdf_path = SAMPLE_PDF
        cls.sample_png_path = SAMPLE_PNG
        cls.sample_heic_path = SAMPLE_HEIC

        cls.pdf_exists = os.path.exists(cls.sample_pdf_path)
        cls.png_exists = os.path.exists(cls.sample_png_path)
        cls.heic_exists = os.path.exists(cls.sample_heic_path)

        if not (cls.pdf_exists and cls.png_exists and cls.heic_exists):
            print("Warning: Not all sample files (PDF, PNG, HEIC) exist. Indexing tests might be limited or skipped.")
            # Attempt to run the main setup if files are missing, as it tries to create them.
            # This might be a bit circular if this class is run in isolation, but helpful in a full suite.
            try:
                TestAttachmentsIntegration.setUpClass() 
                # Re-check after attempting main setup
                cls.pdf_exists = os.path.exists(cls.sample_pdf_path)
                cls.png_exists = os.path.exists(cls.sample_png_path)
                cls.heic_exists = os.path.exists(cls.sample_heic_path)
            except Exception as e:
                print(f"Error running TestAttachmentsIntegration.setUpClass for TestAttachmentsIndexing: {e}")

    def test_integer_indexing(self):
        if not (self.pdf_exists and self.png_exists):
            self.skipTest("PDF or PNG sample file missing for integer indexing test.")
        
        original_paths = [self.sample_pdf_path, f"{self.sample_png_path}[resize:10x10]"]
        atts = Attachments(*original_paths)
        self.assertEqual(len(atts.attachments_data), 2)

        # Test getting the first item (PDF)
        indexed_att_0 = atts[0]
        self.assertIsInstance(indexed_att_0, Attachments)
        self.assertEqual(len(indexed_att_0.attachments_data), 1)
        self.assertEqual(indexed_att_0.attachments_data[0]['type'], 'pdf')
        self.assertEqual(indexed_att_0.original_paths_with_indices, [original_paths[0]])

        # Test getting the second item (PNG)
        indexed_att_1 = atts[1]
        self.assertIsInstance(indexed_att_1, Attachments)
        self.assertEqual(len(indexed_att_1.attachments_data), 1)
        self.assertEqual(indexed_att_1.attachments_data[0]['type'], 'png')
        self.assertEqual(indexed_att_1.original_paths_with_indices, [original_paths[1]])

    def test_slice_indexing(self):
        if not (self.pdf_exists and self.png_exists and self.heic_exists):
            self.skipTest("One or more sample files (PDF, PNG, HEIC) missing for slice indexing test.")

        original_paths = [
            self.sample_pdf_path,
            f"{self.sample_png_path}[resize:10x10]",
            f"{self.sample_heic_path}[format:png]"
        ]
        atts = Attachments(*original_paths)
        self.assertEqual(len(atts.attachments_data), 3)

        # Test slice [0:2]
        sliced_atts_0_2 = atts[0:2]
        self.assertIsInstance(sliced_atts_0_2, Attachments)
        self.assertEqual(len(sliced_atts_0_2.attachments_data), 2)
        self.assertEqual(sliced_atts_0_2.attachments_data[0]['type'], 'pdf')
        self.assertEqual(sliced_atts_0_2.attachments_data[1]['type'], 'png')
        self.assertEqual(sliced_atts_0_2.original_paths_with_indices, original_paths[0:2])

        # Test slice with a step [::2]
        sliced_atts_step = atts[::2]
        self.assertIsInstance(sliced_atts_step, Attachments)
        self.assertEqual(len(sliced_atts_step.attachments_data), 2) # PDF and HEIC
        self.assertEqual(sliced_atts_step.attachments_data[0]['type'], 'pdf')
        self.assertEqual(sliced_atts_step.attachments_data[1]['type'], 'heic') # Original type is heic
        self.assertEqual(sliced_atts_step.original_paths_with_indices, original_paths[::2])

        # Test slice resulting in one item
        sliced_atts_single = atts[1:2]
        self.assertIsInstance(sliced_atts_single, Attachments)
        self.assertEqual(len(sliced_atts_single.attachments_data), 1)
        self.assertEqual(sliced_atts_single.attachments_data[0]['type'], 'png')
        self.assertEqual(sliced_atts_single.original_paths_with_indices, original_paths[1:2])

    def test_empty_slice_indexing(self):
        if not self.pdf_exists:
            self.skipTest("PDF sample file missing for empty slice test.")
        atts = Attachments(self.sample_pdf_path)
        empty_atts = atts[10:12] # Slice that will be out of bounds / empty
        self.assertIsInstance(empty_atts, Attachments)
        self.assertEqual(len(empty_atts.attachments_data), 0)
        self.assertEqual(len(empty_atts.original_paths_with_indices), 0)

    def test_out_of_bounds_integer_indexing(self):
        if not self.pdf_exists:
            self.skipTest("PDF sample file missing for out-of-bounds test.")
        atts = Attachments(self.sample_pdf_path)
        with self.assertRaises(IndexError):
            _ = atts[1] # original_paths_with_indices has only 1 item

    def test_invalid_index_type(self):
        if not self.pdf_exists:
            self.skipTest("PDF sample file missing for invalid index type test.")
        atts = Attachments(self.sample_pdf_path)
        with self.assertRaises(TypeError):
            _ = atts["key"] # type: ignore

class TestIndividualParsers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure multi-page PDF for direct parser tests if needed
        create_multi_page_pdf(GENERATED_MULTI_PAGE_PDF, 3) # 3-page for simpler direct tests
        TestAttachmentsIntegration.setUpClass() # Run the main setup to get sample.pptx and check sample.html
        # cls.sample_html_exists = os.path.exists(SAMPLE_HTML) # Redundant if TestAttachmentsIntegration.setUpClass sets it

    def test_pdf_parser_direct_indexing(self):
        if not os.path.exists(GENERATED_MULTI_PAGE_PDF):
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} for direct parser test not found.")
        parser = PDFParser()
        # Test with PDF now having 5 pages (content: "This is page X of 5.")
        # setUpClass for TestIndividualParsers creates 3-page, then TestAttachmentsIntegration.setUpClass recreates it as 5-page.
        data = parser.parse(GENERATED_MULTI_PAGE_PDF, indices="1,3")
        self.assertIn("This is page 1", data['text'])
        self.assertNotIn("This is page 2", data['text'])
        self.assertIn("This is page 3", data['text'])
        self.assertEqual(data['num_pages'], 5) # Should be 5 pages total
        self.assertEqual(data['indices_processed'], [1, 3])

    def test_pptx_parser_direct_indexing(self):
        if not TestAttachmentsIntegration.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not available/readable for direct PPTX parser test.")
        parser = PPTXParser()
        # SAMPLE_PPTX has 3 slides
        data = parser.parse(SAMPLE_PPTX, indices="N,1") # Last (3) and First (1)
        self.assertIn("Slide 1 Title", data['text'])
        self.assertNotIn("Slide 2 Title", data['text'])
        self.assertIn("Slide 3 Title", data['text'])
        self.assertEqual(data['num_slides'], 3)
        self.assertEqual(data['indices_processed'], [1, 3])

    def test_pdf_parser_direct_invalid_indices(self):
        if not os.path.exists(GENERATED_MULTI_PAGE_PDF):
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} for direct parser test not found.")
        parser = PDFParser()
        data = parser.parse(GENERATED_MULTI_PAGE_PDF, indices="99,abc") # 5-page PDF
        self.assertEqual(data['text'].strip(), "")
        self.assertEqual(data['num_pages'], 5) # Should be 5 pages total
        self.assertEqual(data['indices_processed'], [])

    def test_pdf_parser_file_not_found(self):
        parser = PDFParser()
        with self.assertRaisesRegex(ParsingError, r"(File not found|no such file|cannot open)"):
            parser.parse(NON_EXISTENT_FILE)

    def test_html_parser_direct(self):
        if not TestAttachmentsIntegration.sample_html_exists: # Rely on the flag set by the other class setup
             self.skipTest(f"{SAMPLE_HTML} not found for direct HTML parser test.")
        parser = HTMLParser()
        data = parser.parse(SAMPLE_HTML)
        self.assertIn("# Main Heading", data['text'])
        self.assertIn("**strong emphasis**", data['text'])
        self.assertIn("[Example Link](http://example.com)", data['text'])
        self.assertNotIn("<p>", data['text'])
        self.assertNotIn("<style>", data['text'])
        self.assertEqual(data['file_path'], SAMPLE_HTML)

if __name__ == '__main__':
    unittest.main() 