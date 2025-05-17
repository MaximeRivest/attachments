import unittest
from attachments import Attachments
# from .test_base import (
#     BaseAttachmentsTest, SAMPLE_PDF, SAMPLE_PNG, SAMPLE_HEIC, SAMPLE_PPTX
# )
from tests.conftest import (
    SAMPLE_PDF, SAMPLE_PNG, SAMPLE_HEIC, SAMPLE_PPTX
)

# class TestAttachmentsObjectIndexingAndSlicing(BaseAttachmentsTest):
class TestAttachmentsObjectIndexingAndSlicing(unittest.TestCase):

    def test_integer_indexing_on_attachments_object(self):
        if not (self.sample_pdf_exists and self.sample_png_exists):
            self.skipTest("Required sample files (PDF, PNG) not found for integer indexing test.")
        
        # Use paths that are known to be set up by BaseAttachmentsTest
        original_paths = [SAMPLE_PDF, f"{SAMPLE_PNG}[resize:10x10]"]
        atts = Attachments(*original_paths)
        self.assertEqual(len(atts.attachments_data), 2, "Initial Attachments object should have 2 items.")

        # Test indexing the first item
        indexed_att_0 = atts[0]
        self.assertIsInstance(indexed_att_0, Attachments, "Indexing should return an Attachments object.")
        self.assertEqual(len(indexed_att_0.attachments_data), 1, "Indexed Attachments object should have 1 item.")
        self.assertEqual(indexed_att_0.attachments_data[0]['type'], 'pdf')
        self.assertEqual(indexed_att_0.attachments_data[0]['file_path'], SAMPLE_PDF)
        # Check that original_paths_with_indices is correctly set for the new subset object
        self.assertEqual(indexed_att_0.original_paths_with_indices, [original_paths[0]])

        # Test indexing the second item
        indexed_att_1 = atts[1]
        self.assertIsInstance(indexed_att_1, Attachments)
        self.assertEqual(len(indexed_att_1.attachments_data), 1)
        self.assertEqual(indexed_att_1.attachments_data[0]['type'], 'png')
        self.assertEqual(indexed_att_1.attachments_data[0]['file_path'], SAMPLE_PNG)
        self.assertEqual(indexed_att_1.original_paths_with_indices, [original_paths[1]])

    def test_slice_indexing_on_attachments_object(self):
        if not (self.sample_pdf_exists and self.sample_png_exists and self.sample_heic_exists):
            self.skipTest("One or more sample files (PDF, PNG, HEIC) missing for slice indexing test.")

        original_paths = [
            SAMPLE_PDF,
            f"{SAMPLE_PNG}[resize:10x10]",
            f"{SAMPLE_HEIC}[format:png]"
        ]
        atts = Attachments(*original_paths)
        self.assertEqual(len(atts.attachments_data), 3, "Initial Attachments object should have 3 items.")

        # Slice: first two items
        sliced_atts_0_2 = atts[0:2]
        self.assertIsInstance(sliced_atts_0_2, Attachments)
        self.assertEqual(len(sliced_atts_0_2.attachments_data), 2)
        self.assertEqual(sliced_atts_0_2.attachments_data[0]['type'], 'pdf')
        self.assertEqual(sliced_atts_0_2.attachments_data[1]['type'], 'png')
        self.assertEqual(sliced_atts_0_2.original_paths_with_indices, original_paths[0:2])

        # Slice: with a step
        sliced_atts_step = atts[::2]
        self.assertIsInstance(sliced_atts_step, Attachments)
        self.assertEqual(len(sliced_atts_step.attachments_data), 2) 
        self.assertEqual(sliced_atts_step.attachments_data[0]['type'], 'pdf')
        self.assertEqual(sliced_atts_step.attachments_data[1]['type'], 'heic') # HEIC was converted to PNG type by parser
        self.assertEqual(sliced_atts_step.original_paths_with_indices, original_paths[::2])

        # Slice: single item
        sliced_atts_single = atts[1:2]
        self.assertIsInstance(sliced_atts_single, Attachments)
        self.assertEqual(len(sliced_atts_single.attachments_data), 1)
        self.assertEqual(sliced_atts_single.attachments_data[0]['type'], 'png')
        self.assertEqual(sliced_atts_single.original_paths_with_indices, original_paths[1:2])

    def test_empty_slice_indexing_on_attachments_object(self):
        if not self.sample_pdf_exists:
            self.skipTest("PDF sample file missing for empty slice test.")
        atts = Attachments(SAMPLE_PDF)
        empty_atts = atts[10:12] # Slice that should result in no items
        self.assertIsInstance(empty_atts, Attachments)
        self.assertEqual(len(empty_atts.attachments_data), 0)
        self.assertEqual(len(empty_atts.original_paths_with_indices), 0)

    def test_out_of_bounds_integer_indexing_on_attachments_object(self):
        if not self.sample_pdf_exists:
            self.skipTest("PDF sample file missing for out-of-bounds test.")
        atts = Attachments(SAMPLE_PDF)
        with self.assertRaises(IndexError):
            _ = atts[1] # atts has only 1 item (index 0)
        with self.assertRaises(IndexError):
            _ = atts[-2] # Also out of bounds for a single item list

    def test_invalid_index_type_on_attachments_object(self):
        if not self.sample_pdf_exists:
            self.skipTest("PDF sample file missing for invalid index type test.")
        atts = Attachments(SAMPLE_PDF)
        with self.assertRaises(TypeError):
            _ = atts["key"] # type: ignore 

if __name__ == '__main__':
    unittest.main() 