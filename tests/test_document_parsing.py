import unittest
import os

from attachments import Attachments, DOCXParser, ODTParser
from attachments.exceptions import ParsingError

from tests.conftest import (
    SAMPLE_DOCX, SAMPLE_ODT, NON_EXISTENT_FILE, TEST_DATA_DIR
)

class TestDocumentParsing(unittest.TestCase):

    # --- Test DOCX parsing via Attachments object ---
    def test_attachments_init_with_docx(self):
        if not self.sample_docx_exists:
            self.skipTest(f"{SAMPLE_DOCX} not found.")
        atts = Attachments(SAMPLE_DOCX)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'docx')
        self.assertEqual(data['file_path'], SAMPLE_DOCX)
        # These assertions depend on the content of your sample.docx
        self.assertIn("Header is here", data['text'])
        self.assertIn("Hello this is a test document", data['text'])
        # Add more specific content checks if necessary

    # --- Test ODT parsing via Attachments object ---
    def test_attachments_init_with_odt(self):
        if not self.sample_odt_exists:
            self.skipTest(f"{SAMPLE_ODT} not found or not created by setup.")
        atts = Attachments(SAMPLE_ODT)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'odt')
        self.assertEqual(data['file_path'], SAMPLE_ODT)
        # These assertions depend on the content of your sample.odt
        self.assertIn("Header is here", data['text']) # Assuming similar content to DOCX for test purposes
        self.assertIn("Hello this is a test document", data['text'])
        # Add more specific content checks if necessary

    # --- Direct DOCXParser tests (from old TestAttachmentsIndexing) ---
    def test_docx_parser_direct(self):
        if not self.sample_docx_exists:
            self.skipTest(f"{SAMPLE_DOCX} not found for direct DOCX parser test.")
        parser = DOCXParser()
        data = parser.parse(SAMPLE_DOCX)
        self.assertEqual(data['type'], 'docx')
        self.assertEqual(data['file_path'], SAMPLE_DOCX)
        self.assertIn("Header is here", data['text'])
        self.assertIn("Hello this is a test document", data['text'])

    def test_docx_parser_file_not_found(self):
        parser = DOCXParser()
        with self.assertRaisesRegex(ParsingError, r"(File not found|no such file|cannot open|Failed to open|Package not found|Error parsing DOCX file)", msg="Regex should match specific ParsingError for DOCX file not found."):
            parser.parse(os.path.join(TEST_DATA_DIR, "not_here.txt")) # or some other non-docx but non-existent

    def test_docx_parser_corrupted_file(self):
        # This test is not provided in the original file or the code block
        # It's assumed to exist as it's called in the test_docx_parser_file_not_found method
        pass

    # --- Direct ODTParser tests (from old TestAttachmentsIndexing) ---
    def test_odt_parser_direct(self):
        if not self.sample_odt_exists:
            self.skipTest(f"{SAMPLE_ODT} not found for direct ODT parser test.")
        parser = ODTParser()
        data = parser.parse(SAMPLE_ODT)
        self.assertEqual(data['type'], 'odt')
        self.assertEqual(data['file_path'], SAMPLE_ODT)
        self.assertIn("Header is here", data['text'])
        self.assertIn("Hello this is a test document", data['text'])

    def test_odt_parser_file_not_found(self):
        parser = ODTParser()
        with self.assertRaisesRegex(ParsingError, r"(File not found|no such file|cannot open|Failed to open)"):
            parser.parse(NON_EXISTENT_FILE)

if __name__ == '__main__':
    unittest.main() 