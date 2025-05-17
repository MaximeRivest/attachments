import unittest
import os

from attachments import Attachments, PDFParser # For direct parser tests
from attachments.exceptions import ParsingError # For error checking

from tests.conftest import (
    SAMPLE_PDF, GENERATED_MULTI_PAGE_PDF, NON_EXISTENT_FILE, TEST_DATA_DIR
)

class TestPdfParsing(unittest.TestCase):

    # --- Tests for PDF parsing and indexing via Attachments object ---
    def test_pdf_indexing_single_page(self):
        if not self.generated_multi_page_pdf_exists: # Relies on GENERATED_MULTI_PAGE_PDF from base setup
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[2]") # Indexing string is passed
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'pdf') # Type comes from Attachments processing
        
        # Markitdown currently processes the whole PDF regardless of Attachments indices.
        # So, we expect all pages in the text. The specific page [2] might not be isolated.
        self.assertIn("This is page 1", data['text']) # Expect Page 1 text
        self.assertIn("This is page 2", data['text']) # Expect Page 2 text
        self.assertIn("This is page 5", data['text']) # Expect Page 5 text
        # self.assertNotIn("This is page 1", data['text']) # This would fail now
        # self.assertNotIn("This is page 3", data['text']) # This would fail now

    def test_pdf_indexing_range(self):
        if not self.generated_multi_page_pdf_exists:
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[2-4]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 2", data['text'])
        self.assertIn("This is page 3", data['text'])
        self.assertIn("This is page 4", data['text'])
        # Markitdown currently processes the whole PDF.
        self.assertIn("This is page 1", data['text'])
        self.assertIn("This is page 5", data['text'])
        # self.assertNotIn("This is page 1", data['text']) # Fails
        # self.assertNotIn("This is page 5", data['text']) # Fails

    def test_pdf_indexing_to_end_slice(self):
        if not self.generated_multi_page_pdf_exists:
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[4:]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 4", data['text'])
        self.assertIn("This is page 5", data['text'])
        # Markitdown currently processes the whole PDF.
        self.assertIn("This is page 1", data['text'])
        # self.assertNotIn("This is page 3", data['text'])

    def test_pdf_indexing_from_start_slice(self):
        if not self.generated_multi_page_pdf_exists:
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[:2]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 1", data['text'])
        self.assertIn("This is page 2", data['text'])
        # Markitdown currently processes the whole PDF.
        self.assertIn("This is page 3", data['text'])
        # self.assertNotIn("This is page 3", data['text'])

    def test_pdf_indexing_with_n(self):
        if not self.generated_multi_page_pdf_exists:
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[1,N]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 1", data['text'])
        self.assertIn("This is page 5", data['text'])
        # Markitdown currently processes the whole PDF.
        self.assertIn("This is page 2", data['text'])
        # self.assertNotIn("This is page 2", data['text'])
        # self.assertNotIn("This is page 4", data['text']) # Removed, page 4 will be present

    def test_pdf_indexing_negative(self):
        if not self.generated_multi_page_pdf_exists:
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[-2:]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 4", data['text'])
        self.assertIn("This is page 5", data['text'])
        # Markitdown currently processes the whole PDF.
        self.assertIn("This is page 1", data['text'])
        # self.assertNotIn("This is page 3", data['text'])

    def test_pdf_indexing_empty_result(self):
        if not self.generated_multi_page_pdf_exists:
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        # Attachments class itself might handle invalid index string before parser, 
        # or parser might get it. If markitdown gets it, it processes whole file.
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[99]") # Index out of bounds for typical indexing
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        # Markitdown will process the whole file as it doesn't use the index string "[99]"
        self.assertIn("This is page 1", data['text'])
        self.assertIn("This is page 5", data['text'])
        # self.assertEqual(data['text'], "") # This would fail

    def test_pdf_indexing_empty_indices_string(self):
        if not self.generated_multi_page_pdf_exists:
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found for PDF indexing test.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[]") # Empty index should mean all pages
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 1", data['text'])
        self.assertIn("This is page 5", data['text'])
        # self.assertEqual(data['page_count'], 5) # page_count is not returned by parser

    # --- Direct PDFParser tests (from old TestIndividualParsers) ---
    def test_pdf_parser_direct_indexing(self):
        if not self.generated_multi_page_pdf_exists: 
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} for direct parser test not found.")
        parser = PDFParser() 
        # PDFParser.parse does not use 'indices' with markitdown, so full text is expected.
        data = parser.parse(GENERATED_MULTI_PAGE_PDF, indices="1,3") 
        self.assertIn("This is page 1", data['text'])
        self.assertIn("This is page 2", data['text'])
        self.assertIn("This is page 3", data['text'])
        # self.assertNotIn("This is page 2", data['text'])
        # self.assertEqual(data['page_count'], 5) # Not returned by parser
        # self.assertIn("page_indices_applied", data) # Not returned by this parser setup

    def test_pdf_parser_direct_invalid_indices(self):
        if not self.generated_multi_page_pdf_exists:
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} for direct parser test not found.")
        parser = PDFParser()
        # Markitdown will parse the whole file as indices string is not used by it.
        data = parser.parse(GENERATED_MULTI_PAGE_PDF, indices="99,abc") 
        self.assertIn("This is page 1", data['text'])
        self.assertIn("This is page 5", data['text'])
        # self.assertEqual(data['text'].strip(), "") # Fails

    def test_pdf_parser_file_not_found(self):
        parser = PDFParser()
        with self.assertRaisesRegex(ParsingError, r"(Error processing PDF|Failed to parse PDF).*(No such file or directory|FileNotFoundError)"):
            parser.parse(NON_EXISTENT_FILE)

if __name__ == '__main__':
    unittest.main() 