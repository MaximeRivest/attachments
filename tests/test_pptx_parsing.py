import unittest
import os
from attachments import Attachments, PPTXParser # Assuming PPTXParser for direct tests
from attachments.exceptions import ParsingError
# from .test_base import BaseAttachmentsTest, SAMPLE_PPTX, NON_EXISTENT_FILE, TEST_DATA_DIR
from tests.conftest import SAMPLE_PPTX, NON_EXISTENT_FILE, TEST_DATA_DIR

# class TestPptxParsing(BaseAttachmentsTest):
class TestPptxParsing(unittest.TestCase):

    def test_attachments_init_with_pptx(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not found.")

    # --- Tests for PPTX parsing and indexing via Attachments object ---
    def test_pptx_indexing_single_slide(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not available/readable for PPTX indexing test.")
        atts = Attachments(f"{SAMPLE_PPTX}[2]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'pptx')
        self.assertIn("Slide 2 Title", data['text'])
        self.assertIn("Content for page 2", data['text'])
        self.assertNotIn("Slide 1 Title", data['text'])
        self.assertNotIn("Slide 3 Title", data['text'])
        self.assertEqual(data['num_slides'], 3) # Based on programmatically created PPTX
        self.assertEqual(data['indices_processed'], [2])

    def test_pptx_indexing_range(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not available/readable for PPTX indexing test.")
        atts = Attachments(f"{SAMPLE_PPTX}[1-2]") 
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
        atts = Attachments(f"{SAMPLE_PPTX}[1,N]") 
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
        atts = Attachments(f"{SAMPLE_PPTX}[-2:]") 
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
        atts = Attachments(f"{SAMPLE_PPTX}[]") # Empty index means all slides
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("Slide 1 Title", data['text'])
        self.assertIn("Slide 2 Title", data['text'])
        self.assertIn("Slide 3 Title", data['text'])
        self.assertEqual(data['num_slides'], 3)
        self.assertEqual(data['indices_processed'], [1, 2, 3])

    # --- Direct PPTXParser tests (from old TestIndividualParsers) ---
    def test_pptx_parser_direct_indexing(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not available/readable for direct PPTX parser test.")
        parser = PPTXParser()
        data = parser.parse(SAMPLE_PPTX, indices="N,1") # Slides 3 and 1
        self.assertIn("Slide 1 Title", data['text'])
        self.assertNotIn("Slide 2 Title", data['text'])
        self.assertIn("Slide 3 Title", data['text'])
        self.assertEqual(data['num_slides'], 3)
        self.assertEqual(data['indices_processed'], [1, 3]) # PPTXParser sorts and uniques indices

    def test_pptx_parser_direct_invalid_indices(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not available/readable for direct PPTX parser test.")
        parser = PPTXParser()
        data = parser.parse(SAMPLE_PPTX, indices="99,abc") # Invalid indices 
        self.assertEqual(data['text'].strip(), "") # Expect empty text for invalid indices
        self.assertEqual(data['num_slides'], 3) 
        self.assertEqual(data['indices_processed'], [])

    # Add test for PPTX parser file not found if needed, similar to PDF
    # def test_pptx_parser_file_not_found(self):
    #     parser = PPTXParser()
    #     with self.assertRaisesRegex(ParsingError, r"(File not found|no such file|cannot open)"):
    #         parser.parse(NON_EXISTENT_FILE) # NON_EXISTENT_FILE from base

if __name__ == '__main__':
    unittest.main() 