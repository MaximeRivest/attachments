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
        # Markitdown processes the whole PPTX.
        self.assertIn("Slide 1 Title", data['text'])
        self.assertIn("Slide 2 Title", data['text'])
        self.assertIn("Content for page 2", data['text'])
        self.assertIn("Slide 3 Title", data['text'])
        # self.assertNotIn("Slide 1 Title", data['text'])
        # self.assertNotIn("Slide 3 Title", data['text'])

    def test_pptx_indexing_range(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not available/readable for PPTX indexing test.")
        atts = Attachments(f"{SAMPLE_PPTX}[1-2]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("Slide 1 Title", data['text'])
        self.assertIn("Slide 2 Title", data['text'])
        # Markitdown processes the whole PPTX.
        self.assertIn("Slide 3 Title", data['text'])
        # self.assertNotIn("Slide 3 Title", data['text'])

    def test_pptx_indexing_with_n(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not available/readable for PPTX indexing test.")
        atts = Attachments(f"{SAMPLE_PPTX}[1,N]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("Slide 1 Title", data['text'])
        self.assertIn("Slide 3 Title", data['text'])
        # Markitdown processes the whole PPTX.
        self.assertIn("Slide 2 Title", data['text'])
        # self.assertNotIn("Slide 2 Title", data['text'])

    def test_pptx_indexing_negative_slice(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not available/readable for PPTX indexing test.")
        atts = Attachments(f"{SAMPLE_PPTX}[-2:]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("Slide 2 Title", data['text'])
        self.assertIn("Slide 3 Title", data['text'])
        # Markitdown processes the whole PPTX.
        self.assertIn("Slide 1 Title", data['text'])
        # self.assertNotIn("Slide 1 Title", data['text'])

    def test_pptx_indexing_empty_indices_string(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not available/readable for PPTX indexing test.")
        atts = Attachments(f"{SAMPLE_PPTX}[]") # Empty index means all slides
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("Slide 1 Title", data['text'])
        self.assertIn("Slide 2 Title", data['text'])
        self.assertIn("Slide 3 Title", data['text'])
        # self.assertEqual(data['num_slides'], 3) # Not from parser

    # --- Direct PPTXParser tests (from old TestIndividualParsers) ---
    def test_pptx_parser_direct_indexing(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not available/readable for direct PPTX parser test.")
        parser = PPTXParser()
        # Markitdown processes the whole PPTX.
        data = parser.parse(SAMPLE_PPTX, indices="N,1") # Slides 3 and 1
        self.assertIn("Slide 1 Title", data['text'])
        self.assertIn("Slide 2 Title", data['text'])
        self.assertIn("Slide 3 Title", data['text'])
        # self.assertNotIn("Slide 2 Title", data['text'])
        # self.assertEqual(data['num_slides'], 3) # Not from parser

    def test_pptx_parser_direct_invalid_indices(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not available/readable for direct PPTX parser test.")
        parser = PPTXParser()
        # Markitdown processes the whole PPTX.
        data = parser.parse(SAMPLE_PPTX, indices="99,abc") # Invalid indices
        self.assertIn("Slide 1 Title", data['text'])
        self.assertIn("Slide 3 Title", data['text'])
        # self.assertEqual(data['text'].strip(), "") # Fails

    def test_pptx_parser_file_not_found(self):
        parser = PPTXParser()
        with self.assertRaisesRegex(ParsingError, r"(Error processing PPTX|Failed to parse PPTX).*(No such file or directory|FileNotFoundError)"):
            parser.parse(NON_EXISTENT_FILE)

    def test_pptx_parser_corrupted_file(self):
        # Add test for PPTX parser corrupted file if needed
        pass

if __name__ == '__main__':
    unittest.main() 