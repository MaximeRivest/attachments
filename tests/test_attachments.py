import unittest
import os
from attachments import Attachments, PDFParser, PPTXParser, DefaultXMLRenderer, HTMLParser
from attachments.exceptions import ParsingError
from attachments.utils import parse_index_string # For potential direct tests if needed
import subprocess

# Define the path to the test data directory
TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), 'test_data')
SAMPLE_PDF = os.path.join(TEST_DATA_DIR, 'sample.pdf') # Single page: "Hello PDF!"
SAMPLE_PPTX = os.path.join(TEST_DATA_DIR, 'sample.pptx') # 3 slides: "Slide 1 Title", "Content for page 2", "Slide 3 Title"
GENERATED_MULTI_PAGE_PDF = os.path.join(TEST_DATA_DIR, 'multi_page.pdf')
SAMPLE_HTML = os.path.join(TEST_DATA_DIR, 'sample.html') # Added for HTML tests
NON_EXISTENT_FILE = os.path.join(TEST_DATA_DIR, 'not_here.txt')

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

    def test_render_method_default_xml(self):
        if not hasattr(self, 'sample_pptx_exists') or not self.sample_pptx_exists:
            self.skipTest(f"Skipping PPTX render test as {SAMPLE_PPTX} is not available or readable.")
        atts = Attachments(SAMPLE_PPTX)
        xml_output = atts.render()
        self.assertIn('<attachment id="pptx1" type="pptx">', xml_output)
        self.assertIn("<meta name=\"num_slides\" value=\"3\" />", xml_output) # Expect 3 slides
        self.assertIn("Slide 1 Title", xml_output)
        self.assertIn("Content for page 3", xml_output)

    def test_render_method_default_xml_with_html(self):
        if not self.sample_html_exists:
            self.skipTest(f"{SAMPLE_HTML} not found.")
        atts = Attachments(SAMPLE_HTML)
        xml_output = atts.render()
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
        xml_output = str(atts)
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