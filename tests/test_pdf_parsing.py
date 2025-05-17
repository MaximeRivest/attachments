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
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[2]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'pdf')
        self.assertIn("This is page 2", data['text'])
        self.assertNotIn("This is page 1", data['text'])
        self.assertNotIn("This is page 3", data['text'])
        self.assertEqual(data['page_count'], 5) # GENERATED_MULTI_PAGE_PDF has 5 pages by default from base
        self.assertEqual(data['indices_processed'], [2])

    def test_pdf_indexing_range(self):
        if not self.generated_multi_page_pdf_exists:
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[2-4]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 2", data['text'])
        self.assertIn("This is page 3", data['text'])
        self.assertIn("This is page 4", data['text'])
        self.assertNotIn("This is page 1", data['text'])
        self.assertNotIn("This is page 5", data['text'])
        self.assertEqual(data['page_count'], 5)
        self.assertEqual(data['indices_processed'], [2, 3, 4])

    def test_pdf_indexing_to_end_slice(self):
        if not self.generated_multi_page_pdf_exists:
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[4:]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 4", data['text'])
        self.assertIn("This is page 5", data['text'])
        self.assertNotIn("This is page 3", data['text'])
        self.assertEqual(data['page_count'], 5)
        self.assertEqual(data['indices_processed'], [4, 5])

    def test_pdf_indexing_from_start_slice(self):
        if not self.generated_multi_page_pdf_exists:
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[:2]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 1", data['text'])
        self.assertIn("This is page 2", data['text'])
        self.assertNotIn("This is page 3", data['text'])
        self.assertEqual(data['page_count'], 5)
        self.assertEqual(data['indices_processed'], [1, 2])

    def test_pdf_indexing_with_n(self):
        if not self.generated_multi_page_pdf_exists:
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[1,N]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 1", data['text'])
        self.assertIn("This is page 5", data['text'])
        self.assertNotIn("This is page 2", data['text'])
        self.assertNotIn("This is page 4", data['text'])
        self.assertEqual(data['page_count'], 5)
        self.assertEqual(data['indices_processed'], [1, 5])

    def test_pdf_indexing_negative(self):
        if not self.generated_multi_page_pdf_exists:
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[-2:]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 4", data['text'])
        self.assertIn("This is page 5", data['text'])
        self.assertNotIn("This is page 3", data['text'])
        self.assertEqual(data['page_count'], 5)
        self.assertEqual(data['indices_processed'], [4, 5])

    def test_pdf_indexing_empty_result(self):
        if not self.generated_multi_page_pdf_exists:
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[99]") # Index out of bounds
        self.assertEqual(len(atts.attachments_data), 1) 
        data = atts.attachments_data[0]
        self.assertEqual(data['text'], "") 
        self.assertEqual(data['page_count'], 5) 
        self.assertEqual(data['indices_processed'], []) 

    def test_pdf_indexing_empty_indices_string(self):
        if not self.generated_multi_page_pdf_exists:
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found for PDF indexing test.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 1", data['text'])
        self.assertIn("This is page 5", data['text'])
        self.assertEqual(data['page_count'], 5)
        self.assertEqual(data['indices_processed'], [1, 2, 3, 4, 5])

    # --- Direct PDFParser tests (from old TestIndividualParsers) ---
    def test_pdf_parser_direct_indexing(self):
        if not self.generated_multi_page_pdf_exists: # Checks if GENERATED_MULTI_PAGE_PDF was created
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} for direct parser test not found.")
        parser = PDFParser()
        # BaseAttachmentsTest.setUpClass creates GENERATED_MULTI_PAGE_PDF with 5 pages.
        data = parser.parse(GENERATED_MULTI_PAGE_PDF, indices="1,3")
        self.assertIn("This is page 1", data['text'])
        self.assertNotIn("This is page 2", data['text'])
        self.assertIn("This is page 3", data['text'])
        self.assertEqual(data['page_count'], 5) 
        self.assertEqual(data['indices_processed'], [1, 3])

    def test_pdf_parser_direct_invalid_indices(self):
        if not self.generated_multi_page_pdf_exists:
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} for direct parser test not found.")
        parser = PDFParser()
        data = parser.parse(GENERATED_MULTI_PAGE_PDF, indices="99,abc") # Invalid indices 
        self.assertEqual(data['text'].strip(), "")
        self.assertEqual(data['page_count'], 5) 
        self.assertEqual(data['indices_processed'], [])

    def test_pdf_parser_file_not_found(self):
        parser = PDFParser()
        with self.assertRaisesRegex(ParsingError, r"(File not found|no such file|cannot open)"):
            parser.parse(NON_EXISTENT_FILE)

if __name__ == '__main__':
    unittest.main() 