#!/usr/bin/env python3
"""
Tests for the Attachments high-level API with image loading
"""
#%%
import pytest
from attachments import Attachments
from attachments.data import get_sample_path

# %% [markdown]
# # Testing Attachments Image Loading
# This test suite demonstrates the functionality of the Attachments class with different image formats.
# It includes tests for PNG, HEIC, SVG, and multiple image loading.

# %%
class TestAttachmentsImageLoading:
    """Test the Attachments class with different image formats."""
    
    def test_attachments_png_image(self):
        """Test loading a PNG image using Attachments."""
        # %% [markdown]
        # # Testing PNG Image Loading with Attachments
        # This test demonstrates loading a PNG image file using the high-level Attachments API.
        
        # %%
        png_path = get_sample_path("Figure_1.png")
        ctx = Attachments(png_path)
        
        # %%
        # Verify we have one attachment
        assert len(ctx) == 1
        
        # %%
        # Check that we have extracted images
        assert len(ctx.images) > 0, "Should have extracted at least one image"
        
        # %%
        # Verify the first image is a base64 string
        first_image = ctx.images[0]
        assert isinstance(first_image, str), "Image should be a base64 string"
        assert first_image.startswith('data:image/'), "Should be a data URL"
        
        # %%
        # Check that we have some text content (metadata or description)
        text_content = str(ctx)
        assert len(text_content) > 0, "Should have some text content"
        
        # %%
        # Verify metadata contains useful information
        metadata = ctx.metadata
        assert metadata['file_count'] == 1
        assert metadata['image_count'] > 0
        assert metadata['files'][0]['path'] == png_path
        
        # %%
        print(f"Successfully loaded PNG image: {len(ctx.images)} images extracted")
        print(f"Text content length: {len(text_content)} characters")
    
    def test_attachments_heic_image(self):
        """Test loading a HEIC image using Attachments."""
        # %% [markdown]
        # # Testing HEIC Image Loading with Attachments
        # This test demonstrates loading a HEIC image file (Apple's format) using the Attachments API.
        
        # %%
        heic_path = get_sample_path("sample.HEIC")
        ctx = Attachments(heic_path)
        
        # %%
        # Verify we have one attachment
        assert len(ctx) == 1
        
        # %%
        # Check that we have extracted images
        assert len(ctx.images) > 0, "Should have extracted at least one image"
        
        # %%
        # Verify the first image is a base64 string
        first_image = ctx.images[0]
        assert isinstance(first_image, str), "Image should be a base64 string"
        assert first_image.startswith('data:image/'), "Should be a data URL"
        
        # %%
        # Check that we have some text content
        text_content = str(ctx)
        assert len(text_content) > 0, "Should have some text content"
        
        # %%
        # Verify metadata
        metadata = ctx.metadata
        assert metadata['file_count'] == 1
        assert metadata['image_count'] > 0
        assert metadata['files'][0]['path'] == heic_path
        
        # %%
        print(f"Successfully loaded HEIC image: {len(ctx.images)} images extracted")
        print(f"Text content length: {len(text_content)} characters")
    
    def test_attachments_svg_image(self):
        """Test loading an SVG image using Attachments."""
        # %% [markdown]
        # # Testing SVG Image Loading with Attachments
        # This test demonstrates loading an SVG vector image using the Attachments API.
        # SVG files contain both code and visual representation.
        
        # %%
        svg_path = get_sample_path("sample.svg")
        ctx = Attachments(svg_path)
        
        # %%
        # Verify we have one attachment
        assert len(ctx) == 1
        
        # %%
        # Check that we have extracted images (SVG should be converted to raster)
        assert len(ctx.images) > 0, "Should have extracted at least one image"
        
        # %%
        # Verify the first image is a base64 string
        first_image = ctx.images[0]
        assert isinstance(first_image, str), "Image should be a base64 string"
        assert first_image.startswith('data:image/'), "Should be a data URL"
        
        # %%
        # Check that we have text content (should include SVG code)
        text_content = str(ctx)
        assert len(text_content) > 0, "Should have some text content"
        assert "svg" in text_content.lower(), "Should contain SVG-related content"
        
        # %%
        # Verify metadata
        metadata = ctx.metadata
        assert metadata['file_count'] == 1
        assert metadata['image_count'] > 0
        assert metadata['files'][0]['path'] == svg_path
        
        # %%
        print(f"Successfully loaded SVG image: {len(ctx.images)} images extracted")
        print(f"Text content length: {len(text_content)} characters")
        print(f"SVG content preview: {text_content[:200]}...")
    
    def test_attachments_multiple_images(self):
        """Test loading multiple images at once using Attachments."""
        # %% [markdown]
        # # Testing Multiple Image Loading with Attachments
        # This test demonstrates loading multiple image files simultaneously.
        
        # %%
        png_path = get_sample_path("Figure_1.png")
        heic_path = get_sample_path("sample.HEIC")
        svg_path = get_sample_path("sample.svg")
        
        ctx = Attachments(png_path, heic_path, svg_path)
        
        # %%
        # Verify we have three attachments
        assert len(ctx) == 3, f"Expected 3 attachments, got {len(ctx)}"
        
        # %%
        # Check that we have extracted images from all files
        assert len(ctx.images) >= 3, f"Should have at least 3 images, got {len(ctx.images)}"
        
        # %%
        # Verify all images are base64 strings
        for i, image in enumerate(ctx.images):
            assert isinstance(image, str), f"Image {i} should be a base64 string"
            assert image.startswith('data:image/'), f"Image {i} should be a data URL"
        
        # %%
        # Check that we have combined text content
        text_content = str(ctx)
        assert len(text_content) > 0, "Should have combined text content"
        
        # %%
        # Verify metadata reflects all files
        metadata = ctx.metadata
        assert metadata['file_count'] == 3
        assert metadata['image_count'] >= 3
        assert len(metadata['files']) == 3
        
        # %%
        # Check that all file paths are present
        file_paths = [f['path'] for f in metadata['files']]
        assert png_path in file_paths
        assert heic_path in file_paths
        assert svg_path in file_paths
        
        # %%
        print(f"Successfully loaded {len(ctx)} image files")
        print(f"Total images extracted: {len(ctx.images)}")
        print(f"Combined text content length: {len(text_content)} characters")
    
    def test_attachments_image_with_list_input(self):
        """Test loading images using list input format."""
        # %% [markdown]
        # # Testing Image Loading with List Input
        # This test demonstrates using a list of paths as input to Attachments.
        
        # %%
        image_paths = [
            get_sample_path("Figure_1.png"),
            get_sample_path("sample.svg")
        ]
        
        ctx = Attachments(image_paths)
        
        # %%
        # Verify we have two attachments
        assert len(ctx) == 2
        
        # %%
        # Check that we have extracted images
        assert len(ctx.images) >= 2, "Should have at least 2 images"
        
        # %%
        # Verify metadata
        metadata = ctx.metadata
        assert metadata['file_count'] == 2
        assert metadata['image_count'] >= 2
        
        # %%
        print(f"Successfully loaded images from list: {len(ctx.images)} images extracted")
    
    def test_attachments_image_properties(self):
        """Test accessing image properties and methods."""
        # %% [markdown]
        # # Testing Attachments Image Properties and Methods
        # This test demonstrates various ways to access image data and properties.
        
        # %%
        png_path = get_sample_path("Figure_1.png")
        ctx = Attachments(png_path)
        
        # %%
        # Test different ways to access content
        text_via_str = str(ctx)
        text_via_property = ctx.text
        assert text_via_str == text_via_property, "str() and .text should return same content"
        
        # %%
        # Test iteration
        attachments_list = list(ctx)
        assert len(attachments_list) == 1
        
        # %%
        # Test indexing
        first_attachment = ctx[0]
        assert first_attachment.path == png_path
        
        # %%
        # Test representation
        repr_str = repr(ctx)
        assert "Attachments" in repr_str
        assert "png" in repr_str.lower()
        
        # %%
        print(f"Attachments representation: {repr_str}")
        print(f"Text content matches: {text_via_str == text_via_property}")
        print(f"First attachment path: {first_attachment.path}")


if __name__ == "__main__":
    # %% [markdown]
    # # Running Image Loading Tests
    # Execute the tests to verify image loading functionality.
    
    # %%
    pytest.main([__file__, "-v"])
