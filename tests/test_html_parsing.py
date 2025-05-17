import unittest
import os
from attachments import Attachments, HTMLParser # Assuming HTMLParser is the direct parser
from attachments.exceptions import ParsingError
# from .test_base import BaseAttachmentsTest, SAMPLE_HTML, NON_EXISTENT_FILE, TEST_DATA_DIR
from tests.conftest import SAMPLE_HTML, NON_EXISTENT_FILE, TEST_DATA_DIR

# class TestHtmlParsing(BaseAttachmentsTest):
class TestHtmlParsing(unittest.TestCase):

    # --- Test HTML parsing via Attachments object (extracted and focused) ---
    def test_html_parsing_via_attachments(self):
        if not self.sample_html_exists:
            self.skipTest(f"{SAMPLE_HTML} not found or not created.")
        
        atts = Attachments(SAMPLE_HTML)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'html')
        self.assertEqual(data['file_path'], SAMPLE_HTML)
        # Check for specific markdown conversions
        self.assertIn("# Main Heading", data['text']) 
        self.assertIn("This is a paragraph", data['text'])
        self.assertIn("**strong emphasis**", data['text']) 
        self.assertIn("*italic text*", data['text'])
        self.assertIn("[Example Link](http://example.com)", data['text'])
        self.assertIn("* First item", data['text']) 
        # Check that script/style tags are removed
        self.assertNotIn("<script>", data['text'])
        self.assertNotIn("console.log('test')", data['text'])
        self.assertNotIn("<style>", data['text'])
        # HTML does not have pages/slides or explicit indices processed in this context
        self.assertIsNone(data.get('indices_processed')) 
        self.assertIsNone(data.get('num_pages'))
        self.assertIsNone(data.get('num_slides'))

    # --- Direct HTMLParser tests (from old TestIndividualParsers) ---
    def test_html_parser_direct(self):
        if not self.sample_html_exists:
             self.skipTest(f"{SAMPLE_HTML} not found for direct HTML parser test.")
        parser = HTMLParser()
        data = parser.parse(SAMPLE_HTML)
        # Check for specific markdown conversions by the parser directly
        self.assertIn("# Main Heading", data['text'])
        self.assertIn("**strong emphasis**", data['text'])
        self.assertIn("[Example Link](http://example.com)", data['text'])
        # Check that raw HTML tags are removed/converted
        self.assertNotIn("<p>", data['text'])
        self.assertNotIn("<h1>", data['text'])
        self.assertIn("*italic text*", data['text'])
        self.assertNotIn("<strong>", data['text'])
        # Check that script/style tags are removed
        self.assertNotIn("<script>", data['text'])
        self.assertNotIn("console.log('test')", data['text'])
        self.assertNotIn("<style>", data['text'])
        self.assertEqual(data['file_path'], SAMPLE_HTML)
        # self.assertEqual(data['type'], 'html') # HTMLParser does not set 'type' in its direct output

    def test_html_parser_file_not_found(self):
        parser = HTMLParser()
        with self.assertRaisesRegex(ParsingError, r"(Error processing HTML|Failed to parse HTML).*(No such file or directory|FileNotFoundError)"):
            parser.parse(NON_EXISTENT_FILE)

    def test_attachments_init_with_html(self):
        if not self.sample_html_exists:
            self.skipTest(f"{SAMPLE_HTML} not found.")

    def test_html_parsing_from_url_direct(self):
        if not self.sample_html_exists:
            self.skipTest(f"{SAMPLE_HTML} not found for direct HTML parser test.")
        parser = HTMLParser()
        data = parser.parse(SAMPLE_HTML)
        # Check for specific markdown conversions by the parser directly
        self.assertIn("# Main Heading", data['text'])
        self.assertIn("**strong emphasis**", data['text'])
        self.assertIn("[Example Link](http://example.com)", data['text'])
        # Check that raw HTML tags are removed/converted
        self.assertNotIn("<p>", data['text'])
        self.assertNotIn("<h1>", data['text'])
        self.assertIn("*italic text*", data['text'])
        self.assertNotIn("<strong>", data['text'])
        # Check that script/style tags are removed
        self.assertNotIn("<script>", data['text'])
        self.assertNotIn("console.log('test')", data['text'])
        self.assertNotIn("<style>", data['text'])
        self.assertEqual(data['file_path'], SAMPLE_HTML)
        # self.assertEqual(data['type'], 'html') # HTMLParser does not set 'type' in its direct output

if __name__ == '__main__':
    unittest.main() 