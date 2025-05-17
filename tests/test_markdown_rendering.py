import unittest
import os
import re

from attachments import Attachments
from attachments.config import Config
from tests.conftest import (
    SAMPLE_PDF, SAMPLE_PNG, SAMPLE_HEIC, SAMPLE_AUDIO_WAV, SAMPLE_DOCX, SAMPLE_JPG, SAMPLE_ODT, SAMPLE_PPTX,
    BaseTestSetup
)

class TestMarkdownRendering(BaseTestSetup):

    def test_repr_markdown_empty_attachments(self):
        atts = Attachments()
        markdown_output = atts._repr_markdown_()
        self.assertIn("### Attachments Summary", markdown_output)
        self.assertIn("_No attachments processed and no processing errors._", markdown_output)
        self.assertNotIn("### Image Previews", markdown_output)
        self.assertNotIn("### Audio Previews", markdown_output)

    def test_repr_markdown_pdf_only(self):
        if not self.sample_pdf_exists:
            self.skipTest(f"{SAMPLE_PDF} not found.")
        
        cfg_galleries_true = Config()
        cfg_galleries_true.MARKDOWN_RENDER_GALLERIES = True

        cfg_galleries_false = Config()
        cfg_galleries_false.MARKDOWN_RENDER_GALLERIES = False

        # Test with verbose=False, galleries True (gallery expected for PDF)
        atts_galleries_true_not_verbose = Attachments(SAMPLE_PDF, config=cfg_galleries_true, verbose=False)
        md_galleries_true_not_verbose = atts_galleries_true_not_verbose._repr_markdown_()
        self.assertIn("### Image Previews", md_galleries_true_not_verbose)

        # Test with verbose=False, galleries False (gallery not expected for PDF)
        atts_galleries_false_not_verbose = Attachments(SAMPLE_PDF, config=cfg_galleries_false, verbose=False)
        md_galleries_false_not_verbose = atts_galleries_false_not_verbose._repr_markdown_()
        self.assertNotIn("### Image Previews", md_galleries_false_not_verbose)

    def test_repr_markdown_image_only_with_gallery(self):
        if not self.sample_png_exists:
            self.skipTest(f"{SAMPLE_PNG} not found.")
        
        cfg_galleries_true = Config()
        cfg_galleries_true.MARKDOWN_RENDER_GALLERIES = True
        atts_gallery = Attachments(f"{SAMPLE_PNG}[resize:20x20]", config=cfg_galleries_true, verbose=True) # Verbose for summary, config for gallery
        markdown_output_gallery = atts_gallery._repr_markdown_()
        
        self.assertIn("\n### Image Previews", markdown_output_gallery)
        summary_part, gallery_part = markdown_output_gallery, ""
        if "\n### Image Previews" in markdown_output_gallery:
            parts = markdown_output_gallery.split("\n### Image Previews", 1)
            summary_part = parts[0]
            if len(parts) > 1: gallery_part = parts[1]
        else:
            summary_part = markdown_output_gallery # No gallery if split failed
            self.fail("Image Previews section expected for an image attachment.")

        self.assertIn("### Attachments Summary", summary_part)
        png_id_match = re.search(r"\*\*ID:\*\* `(png\d+)`", summary_part)
        self.assertIsNotNone(png_id_match, "PNG ID not found in summary.")
        self.assertIn(f"(`png` from `{SAMPLE_PNG}[resize:20x20]`)", summary_part)
        # Accept any operations string that includes 'resize: 20x20'
        ops_line = next((line for line in summary_part.splitlines() if line.strip().startswith("- **Operations:**")), None)
        self.assertIsNotNone(ops_line, "No operations line found in summary.")
        self.assertIn("resize: 20x20", ops_line, f"Expected 'resize: 20x20' in operations line, got: {ops_line}")
        self.assertIn("**Original Format:** `PNG`", summary_part)
        self.assertIn("**Output as:** `jpeg`", summary_part)
        
        self.assertIn("\n<img src=\"data:image/jpeg;base64,", gallery_part)
        self.assertTrue(re.search(rf"<img src=\"data:image/jpeg;base64,[^\"]*\" alt=\"{re.escape(os.path.basename(SAMPLE_PNG))}\"", gallery_part),
                        f"Expected HTML img tag for {SAMPLE_PNG} (as JPEG) not found in gallery part. Gallery part:\n{gallery_part}")
        
        cfg_galleries_false = Config()
        cfg_galleries_false.MARKDOWN_RENDER_GALLERIES = False
        atts_no_gallery = Attachments(f"{SAMPLE_PNG}[resize:20x20]", config=cfg_galleries_false, verbose=True)
        markdown_output_no_gallery = atts_no_gallery._repr_markdown_()
        self.assertNotIn("\n### Image Previews", markdown_output_no_gallery)
        self.assertIn("Successfully processed", markdown_output_no_gallery) # Verbose summary should still be there

    def test_repr_markdown_audio_only_with_preview_section(self):
        self.skipTestIfNoFFmpeg()
        if not self.sample_audio_wav_exists:
            self.skipTest(f"{SAMPLE_AUDIO_WAV} not found.")
        ops_str = "format:mp3"

        cfg_galleries_true = Config()
        cfg_galleries_true.MARKDOWN_RENDER_GALLERIES = True
        atts_gallery = Attachments(f"{SAMPLE_AUDIO_WAV}[{ops_str}]", config=cfg_galleries_true, verbose=True)
        markdown_output_gallery = atts_gallery._repr_markdown_()
        self.assertIn("\n### Audio Previews", markdown_output_gallery)
        self.assertIn("<audio controls", markdown_output_gallery)
        self.assertIn("data:audio/mpeg", markdown_output_gallery)

        cfg_galleries_false = Config()
        cfg_galleries_false.MARKDOWN_RENDER_GALLERIES = False
        atts_no_gallery = Attachments(f"{SAMPLE_AUDIO_WAV}[{ops_str}]", config=cfg_galleries_false, verbose=True)
        markdown_output_no_gallery = atts_no_gallery._repr_markdown_()
        self.assertNotIn("\n### Audio Previews", markdown_output_no_gallery)
        self.assertIn("Successfully processed", markdown_output_no_gallery) # Verbose summary

    def test_repr_markdown_docx_only(self):
        if not self.sample_docx_exists:
            self.skipTest(f"{SAMPLE_DOCX} not found.")
        
        cfg_galleries_true = Config()
        cfg_galleries_true.MARKDOWN_RENDER_GALLERIES = True

        cfg_galleries_false = Config()
        cfg_galleries_false.MARKDOWN_RENDER_GALLERIES = False

        # Test with verbose=False, galleries True (gallery expected for DOCX)
        atts_galleries_true_not_verbose = Attachments(SAMPLE_DOCX, config=cfg_galleries_true, verbose=False)
        md_galleries_true_not_verbose = atts_galleries_true_not_verbose._repr_markdown_()
        self.assertIn("### Image Previews", md_galleries_true_not_verbose)

        # Test with verbose=False, galleries False (gallery not expected for DOCX)
        atts_galleries_false_not_verbose = Attachments(SAMPLE_DOCX, config=cfg_galleries_false, verbose=False)
        md_galleries_false_not_verbose = atts_galleries_false_not_verbose._repr_markdown_()
        self.assertNotIn("### Image Previews", md_galleries_false_not_verbose)

    def test_repr_markdown_multiple_mixed_attachments(self):
        self.skipTestIfNoFFmpeg()
        paths_for_markdown = []
        has_pdf, has_png, has_heic, has_audio = False, False, False, False

        if self.sample_pdf_exists: 
            paths_for_markdown.append(SAMPLE_PDF); has_pdf = True
        if self.sample_png_exists: 
            paths_for_markdown.append(f"{SAMPLE_PNG}[resize:20x20]"); has_png = True
        if self.sample_heic_exists: 
            paths_for_markdown.append(f"{SAMPLE_HEIC}[resize:25x25,format:png]"); has_heic = True
        if self.sample_audio_wav_exists:
            paths_for_markdown.append(f"{SAMPLE_AUDIO_WAV}[format:ogg,samplerate:8000]"); has_audio = True

        if not paths_for_markdown or len(paths_for_markdown) < 2:
            self.skipTest("Not enough diverse sample files for comprehensive markdown test.")
            
        cfg_galleries_true = Config()
        cfg_galleries_true.MARKDOWN_RENDER_GALLERIES = True
        atts_gallery = Attachments(*paths_for_markdown, config=cfg_galleries_true, verbose=True)
        markdown_output_gallery = atts_gallery._repr_markdown_()

        self.assertIn("Successfully processed", markdown_output_gallery)
        # Each document (pdf) now adds a contact sheet image, so +1 per doc
        num_attachments = len(paths_for_markdown)
        num_extra = 0
        if has_pdf:
            num_extra += 1
        if self.sample_docx_exists and SAMPLE_DOCX in paths_for_markdown:
            num_extra += 1
        if self.sample_pptx_exists and SAMPLE_PPTX in paths_for_markdown:
            num_extra += 1
        # If you add XLSX, add here
        self.assertTrue(markdown_output_gallery.count("**ID:**") == num_attachments + num_extra, f"Expected {num_attachments + num_extra} ID sections.")
        # Check for horizontal rule separators between items
        # Expect num_attachments - 1 separators if num_attachments > 1
        if num_attachments > 1:
            self.assertTrue(markdown_output_gallery.count("\n---\n") >= num_attachments - 1, "Missing separators between attachments.")

        if has_pdf:
            self.assertIn(f"(`pdf` from `{SAMPLE_PDF}`)", markdown_output_gallery)
            self.assertIn("Hello PDF!", markdown_output_gallery)
        if has_png:
            self.assertIn(f"(`png` from `{SAMPLE_PNG}[resize:20x20]`)", markdown_output_gallery)
            self.assertIn("**Dimensions (after ops):** `20x20`", markdown_output_gallery)
        if has_heic:
            # HEIC converted to PNG, so its type in summary might be 'heic' but output format png
            self.assertIn(f"(`heic` from `{SAMPLE_HEIC}[resize:25x25,format:png]`)", markdown_output_gallery)
            self.assertIn("**Dimensions (after ops):** `25x25`", markdown_output_gallery)
            self.assertIn("**Output as:** `png`", markdown_output_gallery)

        if has_png or has_heic:
            self.assertIn("\n### Image Previews", markdown_output_gallery)
            gallery_split = markdown_output_gallery.split("\n### Image Previews", 1)
            gallery_part = gallery_split[1] if len(gallery_split) > 1 else ""
            if has_png:
                # Check for the PNG image (sample.png) rendered as JPEG (default) in the gallery
                self.assertTrue(re.search(rf"<img src=\"data:image/jpeg;base64,[^\"]*\" alt=\"{re.escape(os.path.basename(SAMPLE_PNG))}\"", gallery_part),
                                "Resized PNG (sample.png) not found as JPEG image in gallery part.")
            if has_heic:
                # Check for the HEIC image (sample.heic) rendered as PNG (due to ops string) in the gallery
                self.assertTrue(re.search(rf"<img src=\"data:image/png;base64,[^\"]*\" alt=\"{re.escape(os.path.basename(SAMPLE_HEIC))}\"", gallery_part),
                                "Converted HEIC (sample.heic) not found as PNG image in gallery part.")
        else:
            self.assertNotIn("\n### Image Previews", markdown_output_gallery)

        if has_audio:
            self.assertIn("\n### Audio Previews", markdown_output_gallery)
            self.assertTrue(re.search(rf"\`(wav|audio)\` from \`{re.escape(SAMPLE_AUDIO_WAV)}.+\`\)", markdown_output_gallery),
                            f"Audio entry for {SAMPLE_AUDIO_WAV} not found in summary as expected.")
            self.assertIn("Output as:** `ogg`", markdown_output_gallery)
            self.assertIn("samplerate: 8000", markdown_output_gallery)
            # self.assertIn("<audio controls src=\"data:audio/ogg;base64,", markdown_output_gallery) # Old specific assertion
            # General checks for OGG audio tag
            self.assertIn("<audio controls", markdown_output_gallery) 
            self.assertIn("data:audio/ogg", markdown_output_gallery)
        else:
            self.assertNotIn("\n### Audio Previews", markdown_output_gallery)

        cfg_galleries_false = Config()
        cfg_galleries_false.MARKDOWN_RENDER_GALLERIES = False
        atts_no_gallery = Attachments(*paths_for_markdown, config=cfg_galleries_false, verbose=True) # Verbose for summary
        markdown_output_no_gallery = atts_no_gallery._repr_markdown_()
        self.assertIn("Successfully processed", markdown_output_no_gallery) # Summary detail still there
        self.assertNotIn("\n### Image Previews", markdown_output_no_gallery)
        self.assertNotIn("\n### Audio Previews", markdown_output_no_gallery)

if __name__ == '__main__':
    unittest.main()