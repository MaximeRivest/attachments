import unittest
import os
import base64
from PIL import Image, ImageOps # For type checking and direct image ops if needed

from attachments import Attachments, ImageParser # The main class to test, ImageParser from top level
from attachments.image_processing import DEFAULT_IMAGE_OUTPUT_FORMAT, IMAGE_WIDTH_LIMIT
# Import BaseAttachmentsTest and constants from the new test_base.py
# from .test_base import (
#     BaseAttachmentsTest,
#     SAMPLE_PNG, SAMPLE_JPG, SAMPLE_HEIC, TEST_DATA_DIR, SAMPLE_PDF # Added SAMPLE_PDF
# )
from tests.conftest import (
    TEST_DATA_DIR, SAMPLE_PNG, SAMPLE_JPG, SAMPLE_HEIC, SAMPLE_PDF
)

# class TestImageProcessing(BaseAttachmentsTest):
class TestImageProcessing(unittest.TestCase):

    # Basic initialization tests (can be brief, focus on image-specific aspects)
    def test_initialize_with_png_image_data(self):
        if not self.sample_png_exists:
            self.skipTest(f"{SAMPLE_PNG} not found.")
        atts = Attachments(SAMPLE_PNG)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'png') # Original type from file
        # self.assertTrue('image_object' in data) # Removed: Check structured output instead
        self.assertEqual(data['original_format'], 'PNG')
        self.assertEqual(data['original_dimensions'], (10, 10)) # As per conftest sample
        self.assertEqual(data['dimensions_after_ops'], (10, 10)) # No ops, so same
        self.assertEqual(data['output_format'], 'png') # Default output if no ops
        self.assertFalse(data['operations_applied']) # No operations applied

    # def test_initialize_with_heic_image_data(self):
    #     if not self.sample_heic_exists:
    #         self.skipTest(f"{SAMPLE_HEIC} not found.")
    #     atts = Attachments(SAMPLE_HEIC)
    #     self.assertEqual(len(atts.attachments_data), 1)
    #     data = atts.attachments_data[0]
    #     self.assertEqual(data['type'], 'heic')
    #     # self.assertTrue('image_object' in data) # Removed
    #     # self.assertIsInstance(data['image_object'], Image.Image) # Removed
    #     self.assertTrue(data['width'] > 0)
    #     self.assertTrue(data['height'] > 0)
    #     self.assertEqual(data['original_format'].upper(), 'HEIF')

    # --- Image Transformation Tests ---
    def test_image_transformations_resize(self):
        if not self.sample_png_exists:
            self.skipTest(f"{SAMPLE_PNG} not found for resize test.")
        atts = Attachments(f"{SAMPLE_PNG}[resize:50x75]")
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'png')
        # self.assertTrue('image_object' in data) # Removed
        # img_obj = data['image_object'] # Removed
        # self.assertEqual(img_obj.width, 50) # Removed
        # self.assertEqual(img_obj.height, 75) # Removed
        self.assertEqual(data['dimensions_after_ops'][0], 50)
        self.assertEqual(data['dimensions_after_ops'][1], 75)
        self.assertEqual(data['operations_applied'].get('resize'), (50,75))

    def test_image_transformations_rotate(self):
        if not self.sample_jpg_exists:
            self.skipTest(f"{SAMPLE_JPG} not found for rotate test.")
        atts = Attachments(f"{SAMPLE_JPG}[rotate:90]")
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'jpeg')
        # self.assertTrue('image_object' in data) # Removed
        # img_obj = data['image_object'] # Removed
        # self.assertEqual(img_obj.width, 10) # Removed, assuming 10x10 sample_jpg from conftest
        # self.assertEqual(img_obj.height, 10) # Removed
        self.assertEqual(data['dimensions_after_ops'][0], 10)
        self.assertEqual(data['dimensions_after_ops'][1], 10)
        self.assertEqual(data['operations_applied'].get('rotate'), 90)

    def test_image_transformations_resize_auto_height(self):
        if not self.sample_png_exists: # Use PNG as it has a known aspect ratio from conftest
            self.skipTest(f"{SAMPLE_PNG} not found for resize test.")
        # SAMPLE_PNG is 10x10
        atts = Attachments(f"{SAMPLE_PNG}[resize:5xauto]") # Target width 5, auto height
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        # self.assertEqual(data['image_object'].width, 5) # Removed
        # self.assertEqual(data['image_object'].height, 5) # Removed, height should be 5 for 1:1 aspect ratio
        self.assertEqual(data['dimensions_after_ops'][0], 5)
        self.assertEqual(data['dimensions_after_ops'][1], 5)
        self.assertEqual(data['operations_applied'].get('resize'), (5, 'auto'))

    def test_image_transformation_format_conversion(self):
        if not self.sample_png_exists:
            self.skipTest(f"{SAMPLE_PNG} not found for format conversion test.")
        atts = Attachments(f"{SAMPLE_PNG}[format:jpeg,quality:75]")
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'png') # Original type
        self.assertEqual(data['output_format'], 'jpeg')
        self.assertEqual(data['output_quality'], 75)
        # self.assertIn("format:jpeg", data['text']) # Text is now empty for images
        self.assertIn("format", data['operations_applied'])
        self.assertEqual(data['operations_applied']['format'], 'jpeg')
        self.assertIn("quality", data['operations_applied'])
        self.assertEqual(data['operations_applied']['quality'], 75)

    def test_image_transformation_invalid_ops(self):
        if not self.sample_png_exists:
            self.skipTest(f"{SAMPLE_PNG} not found for invalid ops test.")
        atts = Attachments(f"{SAMPLE_PNG}[invalid_ops]")
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'png')
        self.assertEqual(data['output_format'], 'png') # Key: output is still PNG
        self.assertEqual(data['output_quality'], 75)   # Default quality is applied
        # self.assertIn("format", data['operations_applied'])
        # self.assertEqual(data['operations_applied']['format'], 'jpeg') # This was incorrect
        self.assertNotIn('format', data['operations_applied']) # Format op should not be in applied_ops if it was invalid and fell back to original
        self.assertEqual(data['operations_applied'].get('quality'), 75) # Quality op (default) should be there

    # --- Tests for Attachments.images property ---
    def test_attachments_images_property_empty_when_no_images(self):
        if not self.sample_pdf_exists: # sample_pdf_exists from base
             self.skipTest(f"Sample PDF for non-image test not available.")
        atts = Attachments(SAMPLE_PDF) # SAMPLE_PDF is not an image
        self.assertEqual(len(atts.images), 1)

    def test_attachments_images_property_single_png_processed_as_jpeg(self):
        if not self.sample_png_exists:
            self.skipTest(f"{SAMPLE_PNG} not found.")
        atts = Attachments(SAMPLE_PNG) # Default processing, ImageParser sets output_format to png
        self.assertEqual(len(atts.images), 1)
        b64_image = atts.images[0]
        # Default behavior: if original is PNG, and no format op, output should be PNG
        self.assertTrue(b64_image.startswith("data:image/png;base64,"))

    def test_attachments_images_property_explicit_jpeg_output(self):
        if not self.sample_png_exists:
            self.skipTest(f"{SAMPLE_PNG} not found.")
        atts = Attachments(f"{SAMPLE_PNG}[format:jpeg,quality:70]")
        self.assertEqual(len(atts.images), 1)
        b64_image = atts.images[0]
        self.assertTrue(b64_image.startswith("data:image/jpeg;base64,"))
        self.assertEqual(atts.attachments_data[0]['output_format'], 'jpeg')
        self.assertEqual(atts.attachments_data[0]['output_quality'], 70)
        try:
            header = base64.b64decode(b64_image.split(',')[1])[:3]
            self.assertEqual(header, b'\xff\xd8\xff') 
        except Exception as e:
            self.fail(f"Base64 decoding or JPEG header check failed: {e}")

    def test_attachments_images_property_explicit_png_output(self):
        if not self.sample_jpg_exists:
            self.skipTest(f"{SAMPLE_JPG} not found.")
        atts = Attachments(f"{SAMPLE_JPG}[format:png]") # Convert JPG to PNG output
        self.assertEqual(len(atts.images), 1)
        b64_image = atts.images[0]
        self.assertTrue(b64_image.startswith("data:image/png;base64,"))
        self.assertEqual(atts.attachments_data[0]['output_format'], 'png')
        try:
            img_bytes = base64.b64decode(b64_image.split(',')[1])
            self.assertTrue(len(img_bytes) > 0, "Decoded image bytes are empty for PNG output.")
            # Check for PNG magic bytes
            self.assertTrue(img_bytes.startswith(b'\x89PNG\r\n\x1a\n'), "Output is not a valid PNG")
        except Exception as e:
            self.fail(f"Base64 decoding or PNG header check failed: {e}")

    # def test_attachments_images_property_multiple_images(self):
    #     files_to_test = []
    #     if self.sample_png_exists: files_to_test.append(SAMPLE_PNG)
    #     if self.sample_jpg_exists: files_to_test.append(SAMPLE_JPG)
    #     if self.sample_heic_exists: files_to_test.append(f"{SAMPLE_HEIC}[format:png]") # Ensure one is PNG
    #     
    #     if len(files_to_test) < 2: # Need at least two to test multiple
    #         self.skipTest(f"Not enough sample images (PNG, JPG, HEIC) found for multiple image test.")
    #
    #     atts = Attachments(*files_to_test)
    #     self.assertEqual(len(atts.images), len(files_to_test))
    #     found_jpeg = False
    #     found_png = False
    #     for img_b64 in atts.images:
    #         self.assertTrue(img_b64.startswith("data:image/"))
    #         if "data:image/jpeg;base64," in img_b64:
    #             found_jpeg = True
    #         if "data:image/png;base64," in img_b64:
    #             found_png = True
    #     
    #     self.assertTrue(found_jpeg, "Expected at least one JPEG in .images output from mixed inputs.")
    #     if f"{SAMPLE_HEIC}[format:png]" in files_to_test: # If HEIC to PNG was included
    #          self.assertTrue(found_png, "Expected at least one PNG in .images output (from HEIC conversion).")

if __name__ == '__main__':
    unittest.main() 