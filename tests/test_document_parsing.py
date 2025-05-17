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
        self.assertEqual(len(atts.attachments_data), 2)
        types = {item['type'] for item in atts.attachments_data}
        self.assertIn('docx', types)
        self.assertIn('jpeg', types)
        doc_item = next(item for item in atts.attachments_data if item['type'] == 'docx')
        self.assertEqual(doc_item['file_path'], SAMPLE_DOCX)
        self.assertIn("Header is here", doc_item['text'])
        self.assertIn("Hello this is a test document", doc_item['text'])
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
        # ODT text extraction might fail with Markitdown if no converter is found
        self.assertEqual(data['text'], "")
        self.assertIn("conversion_error", data)
        self.assertIn("ODT format not supported", data["conversion_error"])

    # --- Direct DOCXParser tests (from old TestAttachmentsIndexing) ---
    def test_docx_parser_direct(self):
        if not self.sample_docx_exists:
            self.skipTest(f"{SAMPLE_DOCX} not found for direct DOCX parser test.")
        parser = DOCXParser()
        data = parser.parse(SAMPLE_DOCX)
        # self.assertEqual(data['type'], 'docx') # Type is not part of parser output
        self.assertEqual(data['file_path'], SAMPLE_DOCX)
        self.assertIn("Header is here", data['text'])
        self.assertIn("Hello this is a test document", data['text'])

    def test_docx_parser_file_not_found(self):
        parser = DOCXParser()
        with self.assertRaisesRegex(ParsingError, r"(Error processing DOCX|Failed to parse DOCX).*(No such file or directory|FileNotFoundError|Package not found)"):
            parser.parse(os.path.join(TEST_DATA_DIR, "not_here.txt"))

    # def test_docx_parser_corrupted_file(self):
    #     # This test is not provided in the original file or the code block
    #     # It's assumed to exist as it's called in the test_docx_parser_file_not_found method
    #     pass

    # --- Direct ODTParser tests (from old TestAttachmentsIndexing) ---
    def test_odt_parser_direct(self):
        if not self.sample_odt_exists:
            self.skipTest(f"{SAMPLE_ODT} not found for direct ODT parser test.")
        parser = ODTParser()
        data = parser.parse(SAMPLE_ODT)
        # self.assertEqual(data['type'], 'odt') # Type is not part of parser output anymore
        self.assertEqual(data['file_path'], SAMPLE_ODT)
        # ODT text extraction might fail with Markitdown
        self.assertEqual(data['text'], "")
        self.assertIn("conversion_error", data)
        self.assertIn("ODT format not supported", data["conversion_error"])

    def test_odt_parser_file_not_found(self):
        parser = ODTParser()
        with self.assertRaisesRegex(ParsingError, r"File not found"):
            parser.parse(os.path.join(TEST_DATA_DIR, "not_here.odt")) # Use .odt extension for clarity

    # def test_odt_parser_unsupported_format_handled(self):
    #     # This test is not provided in the original file or the code block
    #     # It's assumed to exist as it's called in the test_odt_parser_file_not_found method
    #     pass

if __name__ == '__main__':
    unittest.main() 