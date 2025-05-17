import unittest
import os
from PIL import Image # For type checking in image init tests

from attachments import Attachments # The main class to test
# Import constants from conftest.py. The fixture in conftest.py will handle setup.
from tests.conftest import (
    SAMPLE_PDF, SAMPLE_PPTX, SAMPLE_HTML, SAMPLE_PNG, SAMPLE_JPG, SAMPLE_HEIC,
    NON_EXISTENT_FILE, TEST_DATA_DIR
)

# No longer inherits from BaseAttachmentsTest, but directly from unittest.TestCase
# The base_test_setup fixture in conftest.py is autouse and class-scoped.
class TestCoreFunctionality(unittest.TestCase):

    # setUpClass would now be handled by the pytest fixture if it were here.
    # Individual test methods will access self.sample_pdf_exists etc., 
    # which should be set on the class by the fixture.

    def test_initialize_attachments_with_pdf(self):
        # Accessing self.sample_pdf_exists which should be set by the fixture on the class
        if not self.sample_pdf_exists: 
            self.skipTest(f"{SAMPLE_PDF} not found or not created by fixture.")
        atts = Attachments(SAMPLE_PDF)
        self.assertEqual(len(atts.attachments_data), 1)
        self.assertEqual(atts.attachments_data[0]['type'], 'pdf')
        self.assertIn("Hello PDF!", atts.attachments_data[0]['text']) # Assuming sample.pdf contains this
        self.assertEqual(atts.attachments_data[0]['page_count'], 1)
        self.assertEqual(atts.attachments_data[0]['indices_processed'], [1])

    def test_initialize_attachments_with_pptx(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"Skipping PPTX test as {SAMPLE_PPTX} is not available or readable.")
        atts = Attachments(SAMPLE_PPTX)
        self.assertEqual(len(atts.attachments_data), 1)
        self.assertEqual(atts.attachments_data[0]['type'], 'pptx')
        self.assertIn("Slide 1 Title", atts.attachments_data[0]['text'])
        self.assertIn("Content for page 2", atts.attachments_data[0]['text'])
        self.assertIn("Content for page 3", atts.attachments_data[0]['text']) # Based on current programmatic creation
        self.assertEqual(atts.attachments_data[0]['num_slides'], 3) # Based on current programmatic creation

    def test_initialize_attachments_with_html(self):
        if not self.sample_html_exists:
            self.skipTest(f"{SAMPLE_HTML} not found or not created.")
        
        atts = Attachments(SAMPLE_HTML)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'html')
        self.assertEqual(data['file_path'], SAMPLE_HTML)
        self.assertIn("# Main Heading", data['text']) 
        self.assertIn("This is a paragraph", data['text'])
        self.assertIn("**strong emphasis**", data['text']) 
        self.assertIn("_italic text_", data['text'])     
        self.assertIn("[Example Link](http://example.com)", data['text'])
        self.assertIn("* First item", data['text']) 
        self.assertNotIn("<script>", data['text']) 
        self.assertNotIn("console.log", data['text'])
        self.assertIsNone(data.get('indices_processed')) 
        self.assertIsNone(data.get('num_pages'))
        self.assertIsNone(data.get('num_slides'))

    def test_initialize_attachments_with_png(self):
        if not self.sample_png_exists:
            self.skipTest(f"{SAMPLE_PNG} not found or not created.")
        atts = Attachments(SAMPLE_PNG)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'png')
        self.assertEqual(data['file_path'], SAMPLE_PNG)
        # Updated assertion for ImageParser text output format
        expected_text_start = f"Image: {os.path.basename(SAMPLE_PNG)}. Original format: PNG, Original mode: RGB, Original dims: 10x10."
        self.assertTrue(data['text'].startswith(expected_text_start))
        self.assertIn("Final dims: 10x10 (no operations).", data['text'])
        self.assertEqual(data['original_dimensions'], (10,10)) # Check structured output

    def test_initialize_attachments_with_jpeg(self):
        if not self.sample_jpg_exists:
            self.skipTest(f"{SAMPLE_JPG} not found or not created.")
        atts = Attachments(SAMPLE_JPG)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'jpeg')
        self.assertEqual(data['file_path'], SAMPLE_JPG)
        # Updated assertion for ImageParser text output format
        expected_text_start = f"Image: {os.path.basename(SAMPLE_JPG)}. Original format: JPEG, Original mode: RGB, Original dims: 10x10."
        self.assertTrue(data['text'].startswith(expected_text_start))
        self.assertIn("Final dims: 10x10 (no operations).", data['text'])
        self.assertEqual(data['original_dimensions'], (10,10)) # Check structured output

    def test_initialize_attachments_with_heic(self):
        if not self.sample_heic_exists:
            self.skipTest(f"{SAMPLE_HEIC} not found. This test requires a pre-existing valid HEIC file.")
        atts = Attachments(SAMPLE_HEIC)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'heic') # Type should be heic, as detected
        self.assertEqual(data['file_path'], SAMPLE_HEIC)
        # Updated assertion for ImageParser text output format. HEIC original format is HEIF.
        # Original dimensions for sample.heic are 3024x4032 or similar, let's be flexible or check conftest.
        # For now, just check start. Assuming original mode is RGB after pillow_heif conversion.
        # Note: The actual original dims from pillow_heif might vary. This checks the structure.
        expected_text_start = f"Image: {os.path.basename(SAMPLE_HEIC)}. Original format: HEIF, Original mode: RGB"
        self.assertTrue(data['text'].startswith(expected_text_start))
        self.assertIn("(no operations).", data['text']) # Check for the end part without specific dims
        self.assertTrue(data['original_dimensions'][0] > 0) # Check structured output
        self.assertTrue(data['original_dimensions'][1] > 0) # Check structured output
        self.assertEqual(data['original_format'].upper(), 'HEIF')

    def test_initialize_with_multiple_files(self):
        if not (self.sample_pdf_exists and self.sample_pptx_exists):
            self.skipTest(f"Skipping multi-file test as {SAMPLE_PDF} or {SAMPLE_PPTX} is not available/readable.")
        atts = Attachments(SAMPLE_PDF, SAMPLE_PPTX)
        self.assertEqual(len(atts.attachments_data), 2)
        # Order might not be guaranteed, so check types present
        types_found = {item['type'] for item in atts.attachments_data}
        self.assertIn('pdf', types_found)
        self.assertIn('pptx', types_found)


    def test_initialize_with_multiple_files_including_html(self):
        if not (self.sample_pdf_exists and self.sample_html_exists):
            self.skipTest(f"Skipping multi-file HTML test as {SAMPLE_PDF} or {SAMPLE_HTML} is not available.")
        atts = Attachments(SAMPLE_PDF, SAMPLE_HTML)
        self.assertEqual(len(atts.attachments_data), 2)
        
        pdf_data = next((item for item in atts.attachments_data if item['type'] == 'pdf'), None)
        html_data = next((item for item in atts.attachments_data if item['type'] == 'html'), None)
        
        self.assertIsNotNone(pdf_data)
        self.assertIsNotNone(html_data)
        self.assertIn("Hello PDF!", pdf_data['text'])
        self.assertIn("# Main Heading", html_data['text'])

    def test_non_existent_file_skipped(self):
        # NON_EXISTENT_FILE should not exist. If SAMPLE_PDF exists, we expect 1 attachment.
        # If SAMPLE_PDF also doesn't exist (e.g. base setup failed), expect 0.
        initial_files = [NON_EXISTENT_FILE]
        expected_count = 0
        if self.sample_pdf_exists:
            initial_files.append(SAMPLE_PDF)
            expected_count = 1
            
        atts = Attachments(*initial_files)
        self.assertEqual(len(atts.attachments_data), expected_count)
        if expected_count == 1:
            self.assertEqual(atts.attachments_data[0]['file_path'], SAMPLE_PDF)

    def test_unsupported_file_type_skipped(self):
        unsupported_file_path = os.path.join(TEST_DATA_DIR, "sample.xyz_unsupported")
        # Setup: create a dummy unsupported file
        with open(unsupported_file_path, "w") as f:
            f.write("this is an unsupported file type")
        
        initial_files = [unsupported_file_path]
        expected_count = 0
        if self.sample_pdf_exists:
            initial_files.append(SAMPLE_PDF)
            expected_count = 1

        atts = Attachments(*initial_files)
        self.assertEqual(len(atts.attachments_data), expected_count)
        if expected_count == 1:
             self.assertEqual(atts.attachments_data[0]['file_path'], SAMPLE_PDF)
        
        # Teardown: remove the dummy unsupported file
        if os.path.exists(unsupported_file_path):
            os.remove(unsupported_file_path)

    # def test_parse_path_string_internal_method(self):
    #     # Test the internal _parse_path_string method
    #     # This method is usually not called directly by users but is core to Attachments init
    #     atts = Attachments() # No files needed to test this method
    #     
    #     path1, indices1 = atts._parse_path_string("path/to/file.pdf")
    #     self.assertEqual(path1, "path/to/file.pdf")
    #     self.assertIsNone(indices1)
    #
    #     path2, indices2 = atts._parse_path_string("file.pptx[:10]")
    #     self.assertEqual(path2, "file.pptx")
    #     self.assertEqual(indices2, ":10")
    #
    #     path3, indices3 = atts._parse_path_string("another/doc.pdf[1,5,-1:]")
    #     self.assertEqual(path3, "another/doc.pdf")
    #     self.assertEqual(indices3, "1,5,-1:")
    #     
    #     path4, indices4 = atts._parse_path_string("noindices.txt[]") 
    #     self.assertEqual(path4, "noindices.txt")
    #     self.assertEqual(indices4, "")

    # __repr__ usually gives a developer-friendly string, often type and id
    def test_repr_output(self):
        if not self.sample_pdf_exists:
            self.skipTest(f"{SAMPLE_PDF} not found.")
        atts = Attachments(SAMPLE_PDF)
        repr_str = repr(atts)
        # Expected: Attachments('tests/test_data/sample.pdf')
        self.assertEqual(repr_str, f"Attachments('{SAMPLE_PDF}')")
        
        atts_empty = Attachments()
        repr_str_empty = repr(atts_empty)
        self.assertEqual(repr_str_empty, "Attachments()")

        # Test with verbose=True
        atts_verbose = Attachments(SAMPLE_PDF, verbose=True)
        repr_str_verbose = repr(atts_verbose)
        self.assertEqual(repr_str_verbose, f"Attachments('{SAMPLE_PDF}', verbose=True)")

    # Default __str__ should be XML representation
    def test_str_representation_is_xml(self):
        if not self.sample_pdf_exists:
            self.skipTest(f"{SAMPLE_PDF} not found for __str__ XML test.")
        atts = Attachments(SAMPLE_PDF)
        xml_output_via_str = str(atts)
        
        self.assertTrue(xml_output_via_str.startswith("<attachments>"))
        self.assertTrue(xml_output_via_str.endswith("</attachments>"))
        self.assertIn('<attachment id="pdf1" type="pdf">', xml_output_via_str)
        self.assertIn("<meta name=\"page_count\" value=\"1\" />", xml_output_via_str)
        self.assertIn("<content>\nHello PDF!\n    </content>", xml_output_via_str)
        self.assertNotIn("<images>", xml_output_via_str) # No images in sample_pdf

    def test_render_method_xml_explicitly_for_pptx(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"Skipping PPTX XML render test as {SAMPLE_PPTX} is not available or readable.")
        atts = Attachments(SAMPLE_PPTX)
        xml_output = atts.render('xml')
        self.assertTrue(xml_output.startswith("<attachments>"))
        self.assertTrue(xml_output.endswith("</attachments>"))
        self.assertIn('<attachment id="pptx1" type="pptx">', xml_output)
        self.assertIn("<meta name=\"num_slides\" value=\"3\" />", xml_output) # Matches generated PPTX
        self.assertIn("Slide 1 Title", xml_output)
        self.assertIn("Content for page 3", xml_output)

    def test_render_method_default_xml_with_html(self):
        if not self.sample_html_exists:
            self.skipTest(f"{SAMPLE_HTML} not found.")
        atts = Attachments(SAMPLE_HTML)
        xml_output = atts.render('xml') # Default renderer is XML
        self.assertTrue(xml_output.startswith("<attachments>"))
        self.assertTrue(xml_output.endswith("</attachments>"))
        self.assertIn('<attachment id="html1" type="html">', xml_output)
        self.assertIn("# Main Heading", xml_output) # Check for markdown content from HTML
        self.assertIn("**strong emphasis**", xml_output)
        self.assertIn("</content>", xml_output)
        self.assertIn("</attachment>", xml_output)

    def test_initialize_and_repr_with_list_of_paths(self):
        if not (self.sample_png_exists and self.sample_jpg_exists):
            self.skipTest(f"Required sample files ({SAMPLE_PNG} and {SAMPLE_JPG}) not found.")

        paths_with_ops = [
            SAMPLE_PNG,
            f"{SAMPLE_JPG}[resize:50x50]"
        ]
        atts = Attachments(paths_with_ops, verbose=True) # Pass the list as a single argument

        self.assertEqual(len(atts.attachments_data), 2, "Should process two attachments from the list.")

        # Check data for PNG
        item_png = next((item for item in atts.attachments_data if item['original_path_str'] == SAMPLE_PNG), None)
        self.assertIsNotNone(item_png, "PNG attachment not found.")
        self.assertEqual(item_png['type'], 'png')
        self.assertEqual(item_png['file_path'], SAMPLE_PNG)

        # Check data for JPG
        jpg_with_ops_str = f"{SAMPLE_JPG}[resize:50x50]"
        item_jpg = next((item for item in atts.attachments_data if item['original_path_str'] == jpg_with_ops_str), None)
        self.assertIsNotNone(item_jpg, "JPG attachment not found.")
        self.assertEqual(item_jpg['type'], 'jpeg')
        self.assertEqual(item_jpg['file_path'], SAMPLE_JPG)
        self.assertIn('resize', item_jpg.get('operations_applied', {}))
        self.assertEqual(item_jpg['dimensions_after_ops'], (50,50))

        # Check __repr__
        # self.original_paths_with_indices should be [SAMPLE_PNG, jpg_with_ops_str]
        expected_repr = f"Attachments('{SAMPLE_PNG}', '{jpg_with_ops_str}', verbose=True)"
        self.assertEqual(repr(atts), expected_repr, "The __repr__ output is not as expected.")

if __name__ == '__main__':
    unittest.main() 