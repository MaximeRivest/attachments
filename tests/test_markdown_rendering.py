import unittest
import os
import re

from attachments import Attachments
from tests.conftest import (
    SAMPLE_PDF, SAMPLE_PNG, SAMPLE_HEIC, SAMPLE_AUDIO_WAV, SAMPLE_DOCX, SAMPLE_JPG, SAMPLE_ODT,
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
        atts = Attachments(SAMPLE_PDF)
        markdown_output = atts._repr_markdown_()
        # print(f"PDF MD: {markdown_output}") # Debugging line
        self.assertIn("### Attachments Summary", markdown_output)
        self.assertIn(f"**ID:** `pdf1` (`pdf` from `{SAMPLE_PDF}`)", markdown_output)
        self.assertIn("Hello PDF!", markdown_output) # Content from sample.pdf
        self.assertIn("  - **Pages:** `1`", markdown_output) # Check for the specific Pages line
        self.assertNotIn("### Image Previews", markdown_output)
        self.assertNotIn("### Audio Previews", markdown_output)
        self.assertNotIn("\n---\n", markdown_output) # No separator for single item

    def test_repr_markdown_image_only_with_gallery(self):
        if not self.sample_png_exists:
            self.skipTest(f"{SAMPLE_PNG} not found.")
        
        atts = Attachments(f"{SAMPLE_PNG}[resize:20x20]", verbose=True)
        markdown_output = atts._repr_markdown_()
        summary_part, gallery_part = markdown_output, ""
        if "\n### Image Previews" in markdown_output:
            parts = markdown_output.split("\n### Image Previews", 1)
            summary_part = parts[0]
            if len(parts) > 1: gallery_part = parts[1]
        else:
            summary_part = markdown_output # No gallery if split failed
            self.fail("Image Previews section expected for an image attachment.")

        self.assertIn("### Attachments Summary", summary_part)
        png_id_match = re.search(r"\*\*ID:\*\* `(png\d+)`", summary_part)
        self.assertIsNotNone(png_id_match, "PNG ID not found in summary.")
        self.assertIn(f"(`png` from `{SAMPLE_PNG}[resize:20x20]`)", summary_part)
        self.assertIn("**Dimensions (after ops):** `20x20`", summary_part)
        self.assertIn("**Original Format:** `PNG`", summary_part)
        self.assertIn("**Operations:** `resize: 20x20`", summary_part)
        self.assertIn("**Output as:** `png`", summary_part)
        
        self.assertIn("\n### Image Previews", markdown_output) # Header must exist
        
        # Check for HTML image tag directly
        # Expected output format is png because original is png and no format op specified
        png_filename_escaped = re.escape(os.path.basename(SAMPLE_PNG))
        expected_img_tag_regex = rf'<img src="data:image/png;base64,[^"]*" alt="{png_filename_escaped}"'
        
        self.assertTrue(re.search(expected_img_tag_regex, gallery_part), 
                        f"Expected HTML img tag for {SAMPLE_PNG} (as PNG) not found in gallery part. Gallery part:\n{gallery_part}")
        
        self.assertNotIn("### Audio Previews", markdown_output)

    def test_repr_markdown_audio_only_with_preview_section(self):
        self.skipTestIfNoFFmpeg()
        if not self.sample_audio_wav_exists:
            self.skipTest(f"{SAMPLE_AUDIO_WAV} not found.")
        ops_str = "format:mp3"
        atts = Attachments(f"{SAMPLE_AUDIO_WAV}[{ops_str}]", verbose=True)
        markdown_output = atts._repr_markdown_()
        # print(f"Audio MD: {markdown_output}") # Debugging

        self.assertIn("### Attachments Summary", markdown_output)
        wav_id_match = re.search(r"\*\*ID:\*\* `(wav\d+|audio\d+)`", markdown_output)
        self.assertIsNotNone(wav_id_match, "Audio ID (wav\d+ or audio\d+) not found in summary.")
        wav_id = wav_id_match.group(1)
        # The input string (containing filename and ops) is part of the ID line
        self.assertIn(f"ID:** `{wav_id}` (`wav` from `{SAMPLE_AUDIO_WAV}[{ops_str}]`)", markdown_output)
        # Check for specific metadata lines
        self.assertIn("  - **Original Format:** `WAV`", markdown_output)
        self.assertIn("  - **Output as:** `mp3`", markdown_output)
        # Check for content which includes original filename
        self.assertIn(f"Content:** `[Audio: {os.path.basename(SAMPLE_AUDIO_WAV)}]", markdown_output)
        
        # Check for audio preview section and base64 data for mp3
        self.assertIn("\n### Audio Previews", markdown_output)
        # General check for an MP3 audio tag
        self.assertIn("<audio controls", markdown_output)
        self.assertIn("data:audio/mpeg", markdown_output) # Check for correct MIME type indication
        self.assertNotIn("Image Previews", markdown_output) # Ensure no image section

    def test_repr_markdown_docx_only(self):
        if not self.sample_docx_exists:
            self.skipTest(f"{SAMPLE_DOCX} not found.")
        atts = Attachments(SAMPLE_DOCX)
        markdown_output = atts._repr_markdown_()
        # print(f"DOCX MD: {markdown_output}") # Debugging
        self.assertIn("### Attachments Summary", markdown_output)
        self.assertIn(f"**ID:** `docx1` (`docx` from `{SAMPLE_DOCX}`)", markdown_output)
        # Check for specific content from the sample.docx
        self.assertIn("Header is here", markdown_output)
        self.assertIn("Hello this is a test document", markdown_output)
        # The source path is part of the ID line, so no separate "Source:" assertion needed.
        self.assertNotIn("### Image Previews", markdown_output)
        self.assertNotIn("### Audio Previews", markdown_output)

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
            
        atts = Attachments(*paths_for_markdown, verbose=True)
        markdown_output = atts._repr_markdown_()

        self.assertIn("### Attachments Summary", markdown_output)
        num_attachments = len(paths_for_markdown)
        self.assertTrue(markdown_output.count("**ID:**") == num_attachments, f"Expected {num_attachments} ID sections.")
        # Check for horizontal rule separators between items
        # Expect num_attachments - 1 separators if num_attachments > 1
        if num_attachments > 1:
            self.assertTrue(markdown_output.count("\n---\n") >= num_attachments - 1, "Missing separators between attachments.")

        if has_pdf:
            self.assertIn(f"(`pdf` from `{SAMPLE_PDF}`)", markdown_output)
            self.assertIn("Hello PDF!", markdown_output)
        if has_png:
            self.assertIn(f"(`png` from `{SAMPLE_PNG}[resize:20x20]`)", markdown_output)
            self.assertIn("**Dimensions (after ops):** `20x20`", markdown_output)
        if has_heic:
            # HEIC converted to PNG, so its type in summary might be 'heic' but output format png
            self.assertIn(f"(`heic` from `{SAMPLE_HEIC}[resize:25x25,format:png]`)", markdown_output)
            self.assertIn("**Dimensions (after ops):** `25x25`", markdown_output)
            self.assertIn("**Output as:** `png`", markdown_output)

        if has_png or has_heic:
            self.assertIn("\n### Image Previews", markdown_output)
            gallery_split = markdown_output.split("\n### Image Previews", 1)
            gallery_part = gallery_split[1] if len(gallery_split) > 1 else ""
            if has_png:
                # Check for the PNG image (sample.png) rendered as PNG in the gallery
                # It was processed with f"{SAMPLE_PNG}[resize:20x20]", so output format should be PNG
                self.assertTrue(re.search(rf"<img src=\"data:image/png;base64,[^\"]*\" alt=\"{re.escape(os.path.basename(SAMPLE_PNG))}\"", gallery_part),
                                "Resized PNG (sample.png) not found as PNG image in gallery part.")
            if has_heic:
                # Check for the HEIC image (sample.heic) rendered as PNG (due to format:png op)
                self.assertTrue(re.search(rf"<img src=\"data:image/png;base64,[^\"]*\" alt=\"{re.escape(os.path.basename(SAMPLE_HEIC))}\"", gallery_part),
                                "Converted HEIC (sample.heic) not found as PNG image in gallery part.")
        else:
            self.assertNotIn("\n### Image Previews", markdown_output)

        if has_audio:
            self.assertIn("\n### Audio Previews", markdown_output)
            self.assertTrue(re.search(rf"\`(wav|audio)` from `{re.escape(SAMPLE_AUDIO_WAV)}.+`\)", markdown_output),
                            f"Audio entry for {SAMPLE_AUDIO_WAV} not found in summary as expected.")
            self.assertIn("Output as:** `ogg`", markdown_output)
            self.assertIn("samplerate to 8000Hz", markdown_output)
            # self.assertIn("<audio controls src=\"data:audio/ogg;base64,", markdown_output) # Old specific assertion
            # General checks for OGG audio tag
            self.assertIn("<audio controls", markdown_output) 
            self.assertIn("data:audio/ogg", markdown_output)
        else:
            self.assertNotIn("\n### Audio Previews", markdown_output)

if __name__ == '__main__':
    unittest.main() 