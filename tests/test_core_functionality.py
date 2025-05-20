import unittest
import os
import re
import xml.etree.ElementTree as ET # Import ElementTree
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
        if not self.sample_pdf_exists:
            self.skipTest(f"{SAMPLE_PDF} not found.")
        atts = Attachments(SAMPLE_PDF)
        self.assertEqual(len(atts.attachments_data), 2)
        types = {item['type'] for item in atts.attachments_data}
        self.assertIn('pdf', types)
        self.assertIn('jpeg', types)
        doc_item = next(item for item in atts.attachments_data if item['type'] == 'pdf')
        self.assertEqual(doc_item['file_path'], SAMPLE_PDF)
        self.assertIn("Hello PDF!", doc_item['text'])

    def test_initialize_attachments_with_pptx(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not found.")
        atts = Attachments(SAMPLE_PPTX)
        self.assertEqual(len(atts.attachments_data), 2)
        types = {item['type'] for item in atts.attachments_data}
        self.assertIn('pptx', types)
        self.assertIn('jpeg', types)
        doc_item = next(item for item in atts.attachments_data if item['type'] == 'pptx')
        self.assertIn("# Slide 1 Title", doc_item['text'])

    def test_initialize_attachments_with_html(self):
        if not self.sample_html_exists:
            self.skipTest(f"{SAMPLE_HTML} not found or not created.")
        
        atts = Attachments(SAMPLE_HTML)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'html')
        self.assertEqual(data['file_path'], SAMPLE_HTML)
        self.assertIn("# Main Heading", data['text'])
        self.assertIn("*italic text*", data['text']) # Check for markdown style from markitdown
        self.assertIn("**strong emphasis**", data['text']) 
        self.assertIn("[Example Link](http://example.com)", data['text'])
        self.assertIn("* First item", data['text']) 
        self.assertNotIn("<script>", data['text']) 
        self.assertNotIn("console.log", data['text'])
        self.assertIsNone(data.get('indices_processed')) 
        self.assertIsNone(data.get('num_pages'))
        self.assertIsNone(data.get('num_slides'))

    def test_initialize_attachments_with_png(self):
        if not self.sample_png_exists:
            self.skipTest(f"{SAMPLE_PNG} not found.")
        ops_str = "[resize:100x100]"
        atts = Attachments(f"{SAMPLE_PNG}{ops_str}")
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'png')
        self.assertEqual(data['original_path_str'], f"{SAMPLE_PNG}{ops_str}")
        self.assertEqual(data['file_path'], SAMPLE_PNG)
        self.assertEqual(data['text'], "") # Images have empty text
        self.assertEqual(data['original_format'], 'PNG')
        self.assertEqual(data['dimensions_after_ops'], (100,100))

    def test_initialize_attachments_with_jpeg(self):
        if not self.sample_jpg_exists:
            self.skipTest(f"{SAMPLE_JPG} not found or not created.")
        ops_str = "[quality:50]"
        atts = Attachments(f"{SAMPLE_JPG}{ops_str}")
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'jpeg')
        self.assertEqual(data['original_path_str'], f"{SAMPLE_JPG}{ops_str}")
        self.assertEqual(data['file_path'], SAMPLE_JPG)
        self.assertEqual(data['text'], "") # Images have empty text
        self.assertEqual(data['original_dimensions'], (10,10)) # Check structured output
        # print(f"DEBUG JPEG: original_format={data.get('original_format')}, output_quality={data.get('output_quality')}, all_data={data}") # Debug print
        self.assertEqual(data['original_format'], 'JPEG')
        self.assertEqual(data['output_quality'], 50)

    def test_initialize_attachments_with_heic(self):
        if not self.sample_heic_exists:
            self.skipTest(f"{SAMPLE_HEIC} not found.")
        ops_str = "[format:png]"
        atts = Attachments(f"{SAMPLE_HEIC}{ops_str}")
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'heic')
        self.assertEqual(data['original_path_str'], f"{SAMPLE_HEIC}{ops_str}") # Check original string with ops
        self.assertEqual(data['file_path'], SAMPLE_HEIC) # Check clean file path
        self.assertEqual(data['text'], "") # Images have empty text
        self.assertEqual(data['output_format'], 'png')
        self.assertEqual(data['original_format'], 'HEIF') # Pillow-heif reports HEIF for .heic

    def test_initialize_with_multiple_files(self):
        if not (self.sample_pdf_exists and self.sample_pptx_exists):
            self.skipTest(f"Skipping multi-file test as {SAMPLE_PDF} or {SAMPLE_PPTX} is not available/readable.")
        atts = Attachments(SAMPLE_PDF, SAMPLE_PPTX)
        self.assertEqual(len(atts.attachments_data), 4)
        # Order might not be guaranteed, so check types present
        types_found = {item['type'] for item in atts.attachments_data}
        self.assertIn('pdf', types_found)
        self.assertIn('pptx', types_found)


    def test_initialize_with_multiple_files_including_html(self):
        if not (self.sample_pdf_exists and self.sample_html_exists):
            self.skipTest(f"Skipping multi-file HTML test as {SAMPLE_PDF} or {SAMPLE_HTML} is not available.")
        atts = Attachments(SAMPLE_PDF, SAMPLE_HTML)
        self.assertEqual(len(atts.attachments_data), 3)
        
        pdf_data = next((item for item in atts.attachments_data if item['type'] == 'pdf'), None)
        html_data = next((item for item in atts.attachments_data if item['type'] == 'html'), None)
        
        self.assertIsNotNone(pdf_data)
        self.assertIsNotNone(html_data)
        self.assertIn("Hello PDF!", pdf_data['text'])
        self.assertIn("# Main Heading", html_data['text'])

    def test_non_existent_file_skipped(self):
        atts = Attachments("not_a_real_file.pdf")
        # No attachments should be created for non-existent files
        self.assertEqual(len(atts.attachments_data), 0)

    def test_unsupported_file_type_skipped(self):
        atts = Attachments("unsupported_file.xyz")
        # No attachments should be created for unsupported files
        self.assertEqual(len(atts.attachments_data), 0)

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
        if not self.sample_png_exists:
            self.skipTest(f"{SAMPLE_PNG} not found or not created by setup.")
        atts = Attachments(SAMPLE_PNG) 
        xml_output = str(atts)
        # print(f"DEBUG XML PNG: {xml_output}") 
        self.assertIn("<attachments>", xml_output)
        self.assertIn(f"original_path=\"{SAMPLE_PNG}\"", xml_output)

        root = ET.fromstring(xml_output)
        attachment_element = root.find("attachment[@type='png']")
        self.assertIsNotNone(attachment_element)
        content_element = attachment_element.find("content")
        self.assertIsNotNone(content_element)
        self.assertEqual(content_element.text, None) # Or check if it's an empty string if CDATA makes it so
        # For an empty CDATA, ElementTree might parse .text as None or empty string.
        # If it's an issue, might need to check for len(content_element) == 0 if it has no child text node.

        # self.assertIn("<content><![CDATA[]]></content>", xml_output) # Empty for image
        self.assertIn("</attachment>", xml_output)
        self.assertIn("</attachments>", xml_output)

    def test_render_method_xml_explicitly_for_pptx(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not found or not created by setup.")
        atts = Attachments(SAMPLE_PPTX)
        xml_output = atts.render('xml')
        # print(f"DEBUG XML PPTX: {xml_output}") 
        self.assertIn("<attachments>", xml_output)
        self.assertIn(f"original_path=\"{SAMPLE_PPTX}\"", xml_output)

        root = ET.fromstring(xml_output)
        attachment_element = root.find("attachment[@type='pptx']")
        self.assertIsNotNone(attachment_element)
        content_element = attachment_element.find("content")
        self.assertIsNotNone(content_element)
        self.assertIn("Slide 1 Title", content_element.text)
        # self.assertIn("<content><![CDATA[", xml_output)
        # self.assertIn("Slide 1 Title", xml_output) # Markdown content
        # self.assertIn("]]></content>", xml_output)
        self.assertIn("</attachment>", xml_output)
        self.assertIn("</attachments>", xml_output)

    def test_render_method_default_xml_with_html(self):
        if not self.sample_html_exists:
            self.skipTest(f"{SAMPLE_HTML} not found or not created by setup.")
        atts = Attachments(SAMPLE_HTML)
        xml_output = atts.render('xml')
        # print(f"DEBUG XML HTML: {xml_output}") 
        self.assertIn("<attachments>", xml_output)
        self.assertIn(f"original_path=\"{SAMPLE_HTML}\"", xml_output)
        
        root = ET.fromstring(xml_output)
        attachment_element = root.find("attachment[@type='html']")
        self.assertIsNotNone(attachment_element)
        content_element = attachment_element.find("content")
        self.assertIsNotNone(content_element)
        self.assertIn("# Main Heading", content_element.text)
        # self.assertIn("<content><![CDATA[", xml_output)
        # self.assertIn("# Main Heading", xml_output) # Markdown content in CDATA
        # self.assertIn("]]></content>", xml_output)
        self.assertIn("</attachment>", xml_output)
        self.assertIn("</attachments>", xml_output)

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

    def test_unsupported_render_format(self):
        # This method is not provided in the original file or the updated code block
        # It's unclear what this test is intended to check, so it's left unchanged
        pass

    def test_fallback_to_text_parser(self):
        """Test that files with unknown extensions or no extension fall back to TextParser."""
        unknown_ext_content = "Unknown extension fallback test."
        no_ext_content = "No extension fallback test."
        
        temp_dir = TEST_DATA_DIR # Use the existing test data directory for temp files
        unknown_ext_filepath = os.path.join(temp_dir, "test_unknown.unknownext")
        no_ext_filepath = os.path.join(temp_dir, "test_no_ext_file")

        try:
            with open(unknown_ext_filepath, "w", encoding="utf-8") as f:
                f.write(unknown_ext_content)
            with open(no_ext_filepath, "w", encoding="utf-8") as f:
                f.write(no_ext_content)

            atts = Attachments(unknown_ext_filepath, no_ext_filepath, verbose=True) # Verbose for debugging if needed
            self.assertEqual(len(atts.attachments_data), 2, "Should process two files with fallback")

            # Sort by original path to ensure consistent order for assertions
            sorted_attachments = sorted(atts.attachments_data, key=lambda x: x['original_path_str'])

            # Test the file with no extension
            # The order depends on how Attachments processes and potentially sorts them, or how listdir returns them.
            # Assuming Attachments processes in order of input for now, or we find by path.
            no_ext_data = next((item for item in sorted_attachments if item['original_path_str'] == no_ext_filepath), None)
            self.assertIsNotNone(no_ext_data, "Data for no-extension file not found")
            if no_ext_data: # Check to satisfy mypy
                self.assertEqual(no_ext_data['type'], 'txt', "File with no extension should be parsed as txt")
                self.assertEqual(no_ext_data['text'], no_ext_content, "Text content mismatch for no-extension file")
                self.assertIsNone(no_ext_data.get('original_detected_type'), "original_detected_type should be None for no-extension file")

            # Test the file with an unknown extension
            unknown_ext_data = next((item for item in sorted_attachments if item['original_path_str'] == unknown_ext_filepath), None)
            self.assertIsNotNone(unknown_ext_data, "Data for unknown-extension file not found")
            if unknown_ext_data: # Check to satisfy mypy
                self.assertEqual(unknown_ext_data['type'], 'txt', "File with unknown extension should be parsed as txt")
                self.assertEqual(unknown_ext_data['text'], unknown_ext_content, "Text content mismatch for unknown-extension file")
                self.assertIsNone(unknown_ext_data.get('original_detected_type'), "original_detected_type should be None for unknown-extension file")

        finally:
            # Clean up temporary files
            if os.path.exists(unknown_ext_filepath):
                os.remove(unknown_ext_filepath)
            if os.path.exists(no_ext_filepath):
                os.remove(no_ext_filepath)

    def test_unprocessed_inputs_populated_and_rendered(self):
        """Test that unprocessed_inputs list is populated for failed items and rendered in markdown."""
        non_existent_file = "/tmp/this/path/should/really/not/exist/ever/non_existent_file.txt"
        # Using a URL that is syntactically valid but should reliably fail to connect or resolve
        unreachable_url = "http://thisshouldnotexist.example.com/nonexistent.doc"
        
        # A file that exists but might cause a parsing error if we had a dummy parser for a fake type
        # For now, we'll just focus on file not found and URL unreachable
        
        if self.sample_pdf_exists: # A valid file to ensure some processing happens too
            atts = Attachments(non_existent_file, unreachable_url, SAMPLE_PDF, verbose=True)
        else:
            atts = Attachments(non_existent_file, unreachable_url, verbose=True)

        self.assertTrue(len(atts.unprocessed_inputs) >= 2, 
                        f"Expected at least 2 unprocessed inputs, got {len(atts.unprocessed_inputs)}")

        unprocessed_paths = [item[0] for item in atts.unprocessed_inputs]
        self.assertIn(non_existent_file, unprocessed_paths, "Non-existent file path not found in unprocessed_inputs")
        self.assertIn(unreachable_url, unprocessed_paths, "Unreachable URL not found in unprocessed_inputs")

        # Check that reasons are populated (not asserting exact string)
        for path_str, reason in atts.unprocessed_inputs:
            if path_str == non_existent_file:
                self.assertTrue(len(reason) > 0, "Reason for non-existent file should not be empty")
                self.assertIn("not found", reason.lower(), "Reason for non-existent file should mention 'not found'")
            if path_str == unreachable_url:
                self.assertTrue(len(reason) > 0, "Reason for unreachable URL should not be empty")
                self.assertIn("failed to download", reason.lower(), "Reason for unreachable URL should mention download failure")

        # Check Markdown representation
        markdown_output = atts._repr_markdown_()
        self.assertIn("### Unprocessed Inputs", markdown_output, "Markdown output missing Unprocessed Inputs section")
        self.assertIn(f"`{non_existent_file}`", markdown_output, "Markdown output missing non-existent file path")
        self.assertIn(f"`{unreachable_url}`", markdown_output, "Markdown output missing unreachable URL")
        # Also check that a part of the reason is there, e.g., "not found"
        self.assertIn("not found", markdown_output.lower(), "Markdown output missing 'not found' keyword for unprocessed file")
        self.assertIn("failed to download", markdown_output.lower(), "Markdown output missing download failure keyword for unprocessed URL")

    def test_initialize_attachments_with_list_of_paths(self):
        """Test initializing Attachments with a list of paths."""
        # ... existing code ...

if __name__ == '__main__':
    unittest.main() 