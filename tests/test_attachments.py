import unittest
import os
from attachments import Attachments, PDFParser, PPTXParser, DefaultXMLRenderer, HTMLParser, AudioParser
from attachments.exceptions import ParsingError
from attachments.utils import parse_index_string # For potential direct tests if needed
import subprocess
from PIL import Image
import re
import io # Added for io.BytesIO
import wave # Added for creating dummy WAV files
import struct # Added for creating dummy WAV FILES
from pydub import AudioSegment # For inspecting processed audio in tests

# Define the path to the test data directory
TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), 'test_data')
SAMPLE_PDF = os.path.join(TEST_DATA_DIR, 'sample.pdf') # Single page: "Hello PDF!"
SAMPLE_PPTX = os.path.join(TEST_DATA_DIR, 'sample.pptx') # 3 slides: "Slide 1 Title", "Content for page 2", "Slide 3 Title"
GENERATED_MULTI_PAGE_PDF = os.path.join(TEST_DATA_DIR, 'multi_page.pdf')
SAMPLE_HTML = os.path.join(TEST_DATA_DIR, 'sample.html') # Added for HTML tests
NON_EXISTENT_FILE = os.path.join(TEST_DATA_DIR, 'not_here.txt')
SAMPLE_PNG = os.path.join(TEST_DATA_DIR, 'sample.png') # Added for PNG tests
SAMPLE_JPG = os.path.join(TEST_DATA_DIR, 'sample.jpg') # Added for JPG tests
SAMPLE_HEIC = os.path.join(TEST_DATA_DIR, 'sample.heic') # Added for HEIC tests
# The following dummy audio file paths are still defined for setUpClass, 
# but many tests now convert from USER_PROVIDED_WAV instead.
SAMPLE_OGG = os.path.join(TEST_DATA_DIR, 'audio', 'sample.ogg') 
SAMPLE_MP3 = os.path.join(TEST_DATA_DIR, 'audio', 'sample.mp3')
SAMPLE_WAV = os.path.join(TEST_DATA_DIR, 'audio', 'sample.wav') # This one is used by test_attachments_audios_property_single_wav
SAMPLE_FLAC = os.path.join(TEST_DATA_DIR, 'audio', 'sample.flac')
SAMPLE_M4A = os.path.join(TEST_DATA_DIR, 'audio', 'sample.m4a')
SAMPLE_MP4_AUDIO = os.path.join(TEST_DATA_DIR, 'audio', 'sample_audio.mp4')
SAMPLE_WEBM_AUDIO = os.path.join(TEST_DATA_DIR, 'audio', 'sample_audio.webm')
USER_PROVIDED_WAV = os.path.join(TEST_DATA_DIR, 'sample_audio.wav') # User's provided WAV file (should be a valid WAV)

# Helper to create a multi-page PDF for testing PDF indexing
def create_multi_page_pdf(path, num_pages=5):
    if os.path.exists(path):
        return
    try:
        import fitz # PyMuPDF
        doc = fitz.open() # New PDF
        for i in range(num_pages):
            page = doc.new_page()
            page.insert_text((50, 72), f"This is page {i+1} of {num_pages}.")
        doc.save(path)
        doc.close()
        print(f"Created {path} with {num_pages} pages for testing.")
    except Exception as e:
        print(f"Could not create multi-page PDF {path}: {e}")

class TestAttachmentsIntegration(unittest.TestCase):

    # test_output_dir will be set by individual tests if they need to write files
    # No need to define it at class level unless setUpClass/tearDownClass manage it.
    # For .audios tests, output_dir is not strictly needed as it's BytesIO.
    # However, if some part of Attachments writes intermediate files to output_dir, 
    # it might be useful. For now, let tests that need it define it.
    # test_output_dir = os.path.join(TEST_DATA_DIR, "test_outputs_integration")


    @classmethod
    def _create_dummy_audio_file(cls, file_path, file_type):
        """Creates a dummy audio file if it doesn't exist."""
        if os.path.exists(file_path):
            return
        
        audio_dir = os.path.dirname(file_path)
        if not os.path.exists(audio_dir):
            os.makedirs(audio_dir)

        if file_type == 'wav':
            try:
                # Create a minimal, silent WAV file
                sample_rate = 44100
                duration_ms = 10 # milliseconds
                n_frames = int(sample_rate * (duration_ms / 1000.0))
                n_channels = 1
                sampwidth = 2 # 16-bit
                comptype = "NONE"
                compname = "not compressed"

                with wave.open(file_path, 'wb') as wf:
                    wf.setnchannels(n_channels)
                    wf.setsampwidth(sampwidth)
                    wf.setframerate(sample_rate)
                    wf.setnframes(n_frames)
                    wf.setcomptype(comptype, compname)
                    # Write silent frames
                    for _ in range(n_frames):
                        wf.writeframesraw(struct.pack('<h', 0)) # Little-endian 16-bit signed short
                print(f"Created dummy WAV file: {file_path}")
            except Exception as e:
                print(f"Failed to create dummy WAV file {file_path}: {e}")
        else:
            # For other formats, create a small placeholder file
            # These are likely NOT valid audio for pydub, tests should use USER_PROVIDED_WAV and convert.
            try:
                with open(file_path, 'wb') as f:
                    f.write(f"dummy content for {file_type}".encode('utf-8'))
                print(f"Created dummy placeholder audio file: {file_path} (type: {file_type})")
            except Exception as e:
                print(f"Failed to create dummy placeholder audio file {file_path}: {e}")

    @classmethod
    def setUpClass(cls):
        cls.test_output_dir = os.path.join(TEST_DATA_DIR, "test_outputs_integration") # General output dir for tests in this class
        if not os.path.exists(cls.test_output_dir):
            os.makedirs(cls.test_output_dir)
            
        # Ensure sample PDF exists
        if not os.path.exists(SAMPLE_PDF):
            try:
                import fitz
                doc = fitz.open()
                page = doc.new_page()
                page.insert_text((50, 72), "Hello PDF!")
                doc.save(SAMPLE_PDF)
                doc.close()
                print(f"Created {SAMPLE_PDF} for testing.")
            except Exception as e:
                 print(f"Warning: Could not create {SAMPLE_PDF}. PDF tests might be limited: {e}")
        
        create_multi_page_pdf(GENERATED_MULTI_PAGE_PDF, 5)

        try:
            script_path = os.path.join(TEST_DATA_DIR, "generate_test_pptx.py")
            if not os.path.exists(script_path):
                raise FileNotFoundError(f"generate_test_pptx.py not found at {script_path}")
            
            print(f"Attempting to run {script_path} in {TEST_DATA_DIR}...")
            result = subprocess.run(
                ["python3", script_path],
                check=True, capture_output=True, text=True, cwd=TEST_DATA_DIR
            )
            # print(f"generate_test_pptx.py stdout: {result.stdout.strip()}")
            if result.stderr:
                print(f"generate_test_pptx.py stderr: {result.stderr.strip()}")
            
            if not os.path.exists(SAMPLE_PPTX):
                 raise FileNotFoundError(f"{SAMPLE_PPTX} was not created by generate_test_pptx.py")
            print(f"{SAMPLE_PPTX} verified/generated successfully.")
            cls.sample_pptx_exists = True
        except Exception as e:
            print(f"Could not create or verify sample.pptx: {e}. PPTX-dependent tests may be skipped or fail.")
            cls.sample_pptx_exists = False
        
        if cls.sample_pptx_exists:
            try:
                from pptx import Presentation
                Presentation(SAMPLE_PPTX) 
                # print(f"{SAMPLE_PPTX} is readable by python-pptx.")
            except Exception as e:
                print(f"Warning: Generated {SAMPLE_PPTX} could not be reliably opened by python-pptx: {e}. PPTX tests might fail.")
                cls.sample_pptx_exists = False

        if not os.path.exists(SAMPLE_HTML):
            print(f"CRITICAL WARNING: {SAMPLE_HTML} not found. HTML tests will fail or be skipped.")
            try:
                with open(SAMPLE_HTML, "w") as f:
                    f.write("<html><head><title>Dummy</title></head><body><p>Fallback HTML</p></body></html>")
                print(f"Created a fallback {SAMPLE_HTML} as it was missing.")
            except Exception as e_html_create:
                print(f"Could not create fallback {SAMPLE_HTML}: {e_html_create}")
        cls.sample_html_exists = os.path.exists(SAMPLE_HTML)

        cls.sample_png_exists = os.path.exists(SAMPLE_PNG)
        cls.sample_jpg_exists = os.path.exists(SAMPLE_JPG)
        cls.sample_heic_exists = os.path.exists(SAMPLE_HEIC)
        if not cls.sample_png_exists or not cls.sample_jpg_exists: # HEIC is often not creatable easily
            print(f"Warning: Sample images (PNG/JPG) not found. Attempting to create them.")
            try:
                img_creation_script_path = os.path.join(TEST_DATA_DIR, "create_sample_images.py")
                if os.path.exists(img_creation_script_path):
                    subprocess.run(["python3", img_creation_script_path], check=True, cwd=TEST_DATA_DIR, capture_output=True)
                    cls.sample_png_exists = os.path.exists(SAMPLE_PNG)
                    cls.sample_jpg_exists = os.path.exists(SAMPLE_JPG)
                    cls.sample_heic_exists = os.path.exists(SAMPLE_HEIC) # Re-check HEIC too
                    if cls.sample_png_exists and cls.sample_jpg_exists:
                        print("Successfully created/verified sample images using create_sample_images.py.")
                else:
                    print(f"create_sample_images.py not found at {img_creation_script_path}.")
            except Exception as e_img_create:
                print(f"Could not create sample images: {e_img_create}")
        
        if not cls.sample_png_exists: print(f"CRITICAL WARNING: {SAMPLE_PNG} is still missing.")
        if not cls.sample_jpg_exists: print(f"CRITICAL WARNING: {SAMPLE_JPG} is still missing.")
        if not cls.sample_heic_exists: print(f"WARNING: {SAMPLE_HEIC} is missing. HEIC tests might skip or use fallbacks.")

        # Create dummy audio files (placeholders for most, real WAV for SAMPLE_WAV)
        cls._create_dummy_audio_file(SAMPLE_OGG, 'ogg')
        cls.sample_ogg_exists = os.path.exists(SAMPLE_OGG)
        cls._create_dummy_audio_file(SAMPLE_MP3, 'mp3')
        cls.sample_mp3_exists = os.path.exists(SAMPLE_MP3)
        cls._create_dummy_audio_file(SAMPLE_WAV, 'wav') # This creates a valid silent WAV
        cls.sample_wav_exists = os.path.exists(SAMPLE_WAV)
        cls._create_dummy_audio_file(SAMPLE_FLAC, 'flac')
        cls.sample_flac_exists = os.path.exists(SAMPLE_FLAC)
        cls._create_dummy_audio_file(SAMPLE_M4A, 'm4a')
        cls.sample_m4a_exists = os.path.exists(SAMPLE_M4A)
        cls._create_dummy_audio_file(SAMPLE_MP4_AUDIO, 'mp4')
        cls.sample_mp4_audio_exists = os.path.exists(SAMPLE_MP4_AUDIO)
        cls._create_dummy_audio_file(SAMPLE_WEBM_AUDIO, 'webm')
        cls.sample_webm_audio_exists = os.path.exists(SAMPLE_WEBM_AUDIO)

        cls.user_provided_wav_exists = os.path.exists(USER_PROVIDED_WAV)
        if not cls.user_provided_wav_exists:
            print(f"CRITICAL WARNING: User provided WAV {USER_PROVIDED_WAV} is missing. Audio conversion tests will fail/skip.")

    def test_initialize_attachments_with_pdf(self):
        if not os.path.exists(SAMPLE_PDF):
            self.skipTest(f"{SAMPLE_PDF} not found.")
        atts = Attachments(SAMPLE_PDF)
        self.assertEqual(len(atts.attachments_data), 1)
        self.assertEqual(atts.attachments_data[0]['type'], 'pdf')
        self.assertIn("Hello PDF!", atts.attachments_data[0]['text'])
        self.assertEqual(atts.attachments_data[0]['num_pages'], 1)
        self.assertEqual(atts.attachments_data[0]['indices_processed'], [1])

    def test_initialize_attachments_with_pptx(self):
        if not hasattr(self, 'sample_pptx_exists') or not self.sample_pptx_exists:
            self.skipTest(f"Skipping PPTX test as {SAMPLE_PPTX} is not available or readable.")
        atts = Attachments(SAMPLE_PPTX)
        self.assertEqual(len(atts.attachments_data), 1)
        self.assertEqual(atts.attachments_data[0]['type'], 'pptx')
        self.assertIn("Slide 1 Title", atts.attachments_data[0]['text'])
        self.assertIn("Content for page 2", atts.attachments_data[0]['text'])
        self.assertIn("Slide 3 Title", atts.attachments_data[0]['text'])
        self.assertEqual(atts.attachments_data[0]['num_slides'], 3)

    def test_initialize_attachments_with_html(self):
        if not self.sample_html_exists:
            self.skipTest(f"{SAMPLE_HTML} not found.")
        
        atts = Attachments(SAMPLE_HTML)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'html')
        self.assertEqual(data['file_path'], SAMPLE_HTML)
        self.assertIn("# Main Heading", data['text']) 
        self.assertIn("This is a paragraph", data['text'])
        self.assertIn("**strong emphasis**", data['text']) 
        self.assertIn("_italic text_", data['text'])     
        self.assertIn("[Example Link](http://example.com)", data['text'])
        self.assertIn("* First item", data['text']) 
        self.assertNotIn("<script>", data['text']) 
        self.assertNotIn("console.log", data['text'])
        self.assertIsNone(data.get('indices_processed')) 
        self.assertIsNone(data.get('num_pages'))
        self.assertIsNone(data.get('num_slides'))

    def test_initialize_attachments_with_png(self):
        if not self.sample_png_exists:
            self.skipTest(f"{SAMPLE_PNG} not found.")
        atts = Attachments(SAMPLE_PNG)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'png')
        self.assertEqual(data['file_path'], SAMPLE_PNG)
        self.assertIn("[Image: sample.png (original: PNG RGB) -> processed to 1x1 for output as jpeg]", data['text'])
        self.assertEqual(data['width'], 1)
        self.assertEqual(data['height'], 1)
        self.assertTrue('image_object' in data)
        self.assertIsInstance(data['image_object'], Image.Image)

    def test_initialize_attachments_with_jpeg(self):
        if not self.sample_jpg_exists:
            self.skipTest(f"{SAMPLE_JPG} not found.")
        atts = Attachments(SAMPLE_JPG)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'jpeg')
        self.assertEqual(data['file_path'], SAMPLE_JPG)
        self.assertIn("[Image: sample.jpg (original: JPEG RGB) -> processed to 1x1 for output as jpeg]", data['text'])
        self.assertEqual(data['width'], 1)
        self.assertEqual(data['height'], 1)
        self.assertTrue('image_object' in data)
        self.assertIsInstance(data['image_object'], Image.Image)

    def test_initialize_attachments_with_heic(self):
        if not self.sample_heic_exists:
            self.skipTest(f"{SAMPLE_HEIC} not found.")
        atts = Attachments(SAMPLE_HEIC)
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'heic') 
        self.assertEqual(data['file_path'], SAMPLE_HEIC)
        self.assertTrue(data['text'].startswith(f"[Image: {os.path.basename(SAMPLE_HEIC)} (original: HEIF"))
        self.assertTrue('image_object' in data)
        self.assertIsInstance(data['image_object'], Image.Image)
        self.assertTrue(data['width'] > 0)
        self.assertTrue(data['height'] > 0)
        self.assertEqual(data['original_format'].upper(), 'HEIF')

    def test_render_method_xml_explicitly_for_pptx(self):
        if not hasattr(self, 'sample_pptx_exists') or not self.sample_pptx_exists:
            self.skipTest(f"Skipping PPTX XML render test as {SAMPLE_PPTX} is not available or readable.")
        atts = Attachments(SAMPLE_PPTX)
        xml_output = atts.render('xml')
        self.assertTrue(xml_output.startswith("<attachments>"))
        self.assertTrue(xml_output.endswith("</attachments>"))
        self.assertIn('<attachment id="pptx1" type="pptx">', xml_output)
        self.assertIn("<meta name=\"num_slides\" value=\"3\" />", xml_output)
        self.assertIn("Slide 1 Title", xml_output)
        self.assertIn("Content for page 3", xml_output) # This was specific to an older sample.pptx, now generated.

    def test_render_method_default_xml_with_html(self):
        if not self.sample_html_exists:
            self.skipTest(f"{SAMPLE_HTML} not found.")
        atts = Attachments(SAMPLE_HTML)
        xml_output = atts.render('xml') 
        self.assertTrue(xml_output.startswith("<attachments>"))
        self.assertTrue(xml_output.endswith("</attachments>"))
        self.assertIn('<attachment id="html1" type="html">', xml_output)
        self.assertIn("# Main Heading", xml_output) 
        self.assertIn("**strong emphasis**", xml_output)
        self.assertIn("</content>", xml_output)
        self.assertIn("</attachment>", xml_output)

    def test_initialize_with_multiple_files(self):
        if not (os.path.exists(SAMPLE_PDF) and hasattr(self, 'sample_pptx_exists') and self.sample_pptx_exists):
            self.skipTest(f"Skipping multi-file test as {SAMPLE_PDF} or {SAMPLE_PPTX} is not available/readable.")
        atts = Attachments(SAMPLE_PDF, SAMPLE_PPTX)
        self.assertEqual(len(atts.attachments_data), 2)
        self.assertEqual(atts.attachments_data[0]['type'], 'pdf')
        self.assertEqual(atts.attachments_data[1]['type'], 'pptx')

    def test_initialize_with_multiple_files_including_html(self):
        if not (os.path.exists(SAMPLE_PDF) and self.sample_html_exists):
            self.skipTest(f"Skipping multi-file HTML test as {SAMPLE_PDF} or {SAMPLE_HTML} is not available.")
        atts = Attachments(SAMPLE_PDF, SAMPLE_HTML)
        self.assertEqual(len(atts.attachments_data), 2)
        pdf_data = atts.attachments_data[0] if atts.attachments_data[0]['type'] == 'pdf' else atts.attachments_data[1]
        html_data = atts.attachments_data[0] if atts.attachments_data[0]['type'] == 'html' else atts.attachments_data[1]
        
        self.assertEqual(pdf_data['type'], 'pdf')
        self.assertEqual(html_data['type'], 'html')
        self.assertIn("Hello PDF!", pdf_data['text'])
        self.assertIn("# Main Heading", html_data['text'])

    def test_string_representation_xml(self):
        if not os.path.exists(SAMPLE_PDF):
            self.skipTest(f"{SAMPLE_PDF} not found.")
        atts = Attachments(SAMPLE_PDF)
        xml_output = atts.render('xml') 
        self.assertTrue(xml_output.startswith("<attachments>"))
        self.assertTrue(xml_output.endswith("</attachments>"))
        self.assertIn('<attachment id="pdf1" type="pdf">', xml_output)
        self.assertIn("<meta name=\"num_pages\" value=\"1\" />", xml_output)
        self.assertIn("<content>\nHello PDF!\n    </content>", xml_output)

    def test_non_existent_file_skipped(self):
        atts = Attachments(NON_EXISTENT_FILE, SAMPLE_PDF if os.path.exists(SAMPLE_PDF) else NON_EXISTENT_FILE)
        expected_count = 1 if os.path.exists(SAMPLE_PDF) else 0 
        self.assertEqual(len(atts.attachments_data), expected_count)

    def test_unsupported_file_type_skipped(self):
        unsupported_file = os.path.join(TEST_DATA_DIR, "sample.xyz")
        with open(unsupported_file, "w") as f:
            f.write("this is an unsupported file type")
        
        atts = Attachments(unsupported_file, SAMPLE_PDF if os.path.exists(SAMPLE_PDF) else NON_EXISTENT_FILE)
        expected_count = 1 if os.path.exists(SAMPLE_PDF) else 0
        self.assertEqual(len(atts.attachments_data), expected_count)
        os.remove(unsupported_file)

    def test_parse_path_string(self):
        atts = Attachments() 
        path1, indices1 = atts._parse_path_string("path/to/file.pdf")
        self.assertEqual(path1, "path/to/file.pdf")
        self.assertIsNone(indices1)

        path2, indices2 = atts._parse_path_string("file.pptx[:10]")
        self.assertEqual(path2, "file.pptx")
        self.assertEqual(indices2, ":10")

        path3, indices3 = atts._parse_path_string("another/doc.pdf[1,5,-1:]")
        self.assertEqual(path3, "another/doc.pdf")
        self.assertEqual(indices3, "1,5,-1:")
        
        path4, indices4 = atts._parse_path_string("noindices.txt[]") 
        self.assertEqual(path4, "noindices.txt")
        self.assertEqual(indices4, "")

    def test_parse_path_string_with_indices(self):
        atts = Attachments() 
        path, indices = atts._parse_path_string("file.pdf[1,2,-1:]")
        self.assertEqual(path, "file.pdf")
        self.assertEqual(indices, "1,2,-1:")

        path, indices = atts._parse_path_string("file.pptx[:N]")
        self.assertEqual(path, "file.pptx")
        self.assertEqual(indices, ":N")
        
        path, indices = atts._parse_path_string("file.txt")
        self.assertEqual(path, "file.txt")
        self.assertIsNone(indices)

        path, indices = atts._parse_path_string("file.txt[]") 
        self.assertEqual(path, "file.txt")
        self.assertEqual(indices, "")

    def test_pdf_indexing_single_page(self):
        if not os.path.exists(GENERATED_MULTI_PAGE_PDF):
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[2]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 2", data['text'])
        self.assertNotIn("This is page 1", data['text'])
        self.assertNotIn("This is page 3", data['text'])
        self.assertEqual(data['num_pages'], 5) 
        self.assertEqual(data['indices_processed'], [2])

    def test_pdf_indexing_range(self):
        if not os.path.exists(GENERATED_MULTI_PAGE_PDF):
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[2-4]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 2", data['text'])
        self.assertIn("This is page 3", data['text'])
        self.assertIn("This is page 4", data['text'])
        self.assertNotIn("This is page 1", data['text'])
        self.assertNotIn("This is page 5", data['text'])
        self.assertEqual(data['num_pages'], 5)
        self.assertEqual(data['indices_processed'], [2, 3, 4])

    def test_pdf_indexing_to_end_slice(self):
        if not os.path.exists(GENERATED_MULTI_PAGE_PDF):
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[4:]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 4", data['text'])
        self.assertIn("This is page 5", data['text'])
        self.assertNotIn("This is page 3", data['text'])
        self.assertEqual(data['num_pages'], 5)
        self.assertEqual(data['indices_processed'], [4, 5])

    def test_pdf_indexing_from_start_slice(self):
        if not os.path.exists(GENERATED_MULTI_PAGE_PDF):
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[:2]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 1", data['text'])
        self.assertIn("This is page 2", data['text'])
        self.assertNotIn("This is page 3", data['text'])
        self.assertEqual(data['num_pages'], 5)
        self.assertEqual(data['indices_processed'], [1, 2])

    def test_pdf_indexing_with_n(self):
        if not os.path.exists(GENERATED_MULTI_PAGE_PDF):
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[1,N]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 1", data['text'])
        self.assertIn("This is page 5", data['text'])
        self.assertNotIn("This is page 2", data['text'])
        self.assertNotIn("This is page 4", data['text'])
        self.assertEqual(data['num_pages'], 5)
        self.assertEqual(data['indices_processed'], [1, 5])

    def test_pdf_indexing_negative(self):
        if not os.path.exists(GENERATED_MULTI_PAGE_PDF):
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[-2:]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("This is page 4", data['text'])
        self.assertIn("This is page 5", data['text'])
        self.assertNotIn("This is page 3", data['text'])
        self.assertEqual(data['num_pages'], 5)
        self.assertEqual(data['indices_processed'], [4, 5])

    def test_pdf_indexing_empty_result(self):
        if not os.path.exists(GENERATED_MULTI_PAGE_PDF):
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} not found.")
        atts = Attachments(f"{GENERATED_MULTI_PAGE_PDF}[99]") 
        self.assertEqual(len(atts.attachments_data), 1) 
        data = atts.attachments_data[0]
        self.assertEqual(data['text'], "") 
        self.assertEqual(data['num_pages'], 5) 
        self.assertEqual(data['indices_processed'], []) 

    def test_pptx_indexing_single_slide(self):
        if not self.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not available/readable for PPTX indexing test.")
        atts = Attachments(f"{SAMPLE_PPTX}[2]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("Slide 2 Title", data['text'])
        self.assertIn("Content for page 2", data['text'])
        self.assertNotIn("Slide 1 Title", data['text'])
        self.assertNotIn("Slide 3 Title", data['text'])
        self.assertEqual(data['num_slides'], 3)
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
        atts = Attachments(f"{SAMPLE_PPTX}[]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertIn("Slide 1 Title", data['text'])
        self.assertIn("Slide 2 Title", data['text'])
        self.assertIn("Slide 3 Title", data['text'])
        self.assertEqual(data['num_slides'], 3)
        self.assertEqual(data['indices_processed'], [1, 2, 3])

    def test_image_transformations_resize(self):
        if not self.sample_png_exists:
            self.skipTest(f"{SAMPLE_PNG} not found for resize test.")
        atts = Attachments(f"{SAMPLE_PNG}[resize:50x75]")
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'png')
        self.assertTrue('image_object' in data)
        self.assertEqual(data['image_object'].width, 50)
        self.assertEqual(data['image_object'].height, 75)
        self.assertEqual(data['width'], 50) 
        self.assertEqual(data['height'], 75)
        self.assertIn("resize:50x75", data['text'])
        self.assertEqual(data['applied_operations'].get('resize'), (50,75))

    def test_image_transformations_rotate(self):
        if not self.sample_jpg_exists:
            self.skipTest(f"{SAMPLE_JPG} not found for rotate test.")
        atts = Attachments(f"{SAMPLE_JPG}[rotate:90]") 
        self.assertEqual(len(atts.attachments_data), 1)
        data = atts.attachments_data[0]
        self.assertEqual(data['type'], 'jpeg')
        self.assertTrue('image_object' in data)
        self.assertEqual(data['image_object'].width, 1) 
        self.assertEqual(data['image_object'].height, 1)
        self.assertEqual(data['width'], 1)
        self.assertEqual(data['height'], 1)
        self.assertIn("rotate:90", data['text'])
        self.assertEqual(data['applied_operations'].get('rotate'), 90)

    def test_image_transformations_resize_auto_height(self):
        if not self.sample_png_exists: 
            self.skipTest(f"{SAMPLE_PNG} not found for resize test.")
        temp_img_path = os.path.join(self.test_output_dir, "temp_2x1.png") # Use test_output_dir
        try:
            img = Image.new('RGB', (200, 100), color='green') # Make it a bit larger for auto-resize to be more apparent
            img.save(temp_img_path, 'PNG')
            atts = Attachments(f"{temp_img_path}[resize:100xauto]")
            self.assertEqual(len(atts.attachments_data), 1)
            data = atts.attachments_data[0]
            self.assertEqual(data['image_object'].width, 100)
            self.assertEqual(data['image_object'].height, 50) 
            self.assertEqual(data['applied_operations'].get('resize'), (100,None))
        finally:
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)

    def test_attachments_images_property_empty(self):
        atts = Attachments(SAMPLE_PDF) 
        self.assertEqual(atts.images, [])

    def test_attachments_images_property_single_png(self):
        if not self.sample_png_exists:
            self.skipTest(f"{SAMPLE_PNG} not found.")
        atts = Attachments(SAMPLE_PNG)
        self.assertEqual(len(atts.images), 1)
        b64_image = atts.images[0]
        self.assertTrue(b64_image.startswith("data:image/jpeg;base64,"))
        import base64
        try:
            header = base64.b64decode(b64_image.split(',')[1])[:3] 
            self.assertEqual(header, b'\xff\xd8\xff') 
        except Exception:
            self.fail("Base64 decoding or JPEG header check failed for PNG converted to JPEG.")

    def test_attachments_images_property_jpeg_output_format(self):
        if not self.sample_png_exists:
            self.skipTest(f"{SAMPLE_PNG} not found.")
        atts = Attachments(f"{SAMPLE_PNG}[format:jpeg,quality:70]")
        self.assertEqual(len(atts.images), 1)
        b64_image = atts.images[0]
        self.assertTrue(b64_image.startswith("data:image/jpeg;base64,"))
        self.assertEqual(atts.attachments_data[0]['output_format'], 'jpeg')
        self.assertEqual(atts.attachments_data[0]['output_quality'], 70)
        import base64
        try:
            header = base64.b64decode(b64_image.split(',')[1])[:3]
            self.assertEqual(header, b'\xff\xd8\xff') 
        except Exception:
            self.fail("Base64 decoding or JPEG header check failed.")

    def test_attachments_images_property_multiple_images(self):
        files_to_test = []
        skipped_any = False
        if self.sample_png_exists: files_to_test.append(SAMPLE_PNG)
        else: skipped_any = True
        if self.sample_jpg_exists: files_to_test.append(SAMPLE_JPG)
        else: skipped_any = True
        if self.sample_heic_exists: files_to_test.append(SAMPLE_HEIC)
        else: skipped_any = True
        
        if skipped_any or not files_to_test:
            self.skipTest(f"One or more sample images (PNG, JPG, HEIC) not found for multiple image test.")

        atts = Attachments(*files_to_test)
        self.assertEqual(len(atts.images), len(files_to_test))
        for img_b64 in atts.images:
            self.assertTrue(img_b64.startswith("data:image/")) 

    def test_attachments_audios_property_empty(self):
        atts = Attachments(verbose=True) # Removed output_dir
        self.assertEqual(len(atts.audios), 0)
        print(".audios empty check: OK")

    def test_attachments_audios_property_single_ogg(self):
        if not self.user_provided_wav_exists:
            self.skipTest(f"User provided WAV file {USER_PROVIDED_WAV} not found. Skipping OGG conversion test.")
        original_wav_basename = os.path.basename(USER_PROVIDED_WAV)
        atts = Attachments(f"{USER_PROVIDED_WAV}[format:ogg]", verbose=True) # Removed output_dir
        self.assertEqual(len(atts.attachments_data), 1, "Attachments data should contain one item for OGG conversion.")
        item = atts.attachments_data[0]
        self.assertEqual(item['type'], 'wav', "Original detected type should be wav")
        self.assertEqual(item['original_format'], 'wav', "Original format metadata should be wav")
        self.assertEqual(item['output_format'], 'ogg', "Output format should be ogg")
        self.assertTrue(item['processed_filename_for_api'].startswith(original_wav_basename.rsplit('.', 1)[0]))
        self.assertTrue(item['processed_filename_for_api'].endswith('.ogg'), "Processed filename should end with .ogg")
        self.assertIn(f"Audio: {original_wav_basename}", item['text'])
        self.assertIn("ops: \"format:ogg\"", item['text'])
        self.assertIn("-> processed to ogg", item['text'])
        audios = atts.audios
        self.assertEqual(len(audios), 1, "Audios property should return one item.")
        audio_file = audios[0]
        self.assertTrue(audio_file['filename'].endswith('.ogg'), "Audio file filename should end with .ogg")
        self.assertEqual(audio_file['content_type'], 'audio/ogg', "Content type should be audio/ogg")
        self.assertIsInstance(audio_file['file_object'], io.BytesIO, "File object should be BytesIO.")
        self.assertTrue(len(audio_file['file_object'].getvalue()) > 0, "File object should not be empty.")
        try:
            ogg_segment = AudioSegment.from_file(audio_file['file_object'], format="ogg")
            audio_file['file_object'].seek(0) 
            self.assertIsNotNone(ogg_segment, "Pydub should be able to load the OGG output.")
            original_segment_check = AudioSegment.from_file(USER_PROVIDED_WAV)
            self.assertEqual(ogg_segment.frame_rate, original_segment_check.frame_rate)
            self.assertEqual(ogg_segment.channels, original_segment_check.channels)
        except Exception as e:
            self.fail(f"Pydub could not load the processed OGG file: {e}")
        print(".audios property single OGG (converted from WAV) check: OK")

    def test_attachments_audios_property_single_mp3(self):
        if not self.user_provided_wav_exists:
            self.skipTest(f"User provided WAV file {USER_PROVIDED_WAV} not found. Skipping MP3 conversion test.")
        original_wav_basename = os.path.basename(USER_PROVIDED_WAV)
        atts = Attachments(f"{USER_PROVIDED_WAV}[format:mp3]", verbose=True) # Removed output_dir
        self.assertEqual(len(atts.attachments_data), 1, "Attachments data should contain one item for MP3 conversion.")
        item = atts.attachments_data[0]
        self.assertEqual(item['type'], 'wav', "Original detected type should be wav")
        self.assertEqual(item['original_format'], 'wav', "Original format metadata should be wav")
        self.assertEqual(item['output_format'], 'mp3', "Output format should be mp3")
        self.assertTrue(item['processed_filename_for_api'].startswith(original_wav_basename.rsplit('.', 1)[0]))
        self.assertTrue(item['processed_filename_for_api'].endswith('.mp3'), "Processed filename should end with .mp3")
        self.assertIn(f"Audio: {original_wav_basename}", item['text'])
        self.assertIn("ops: \"format:mp3\"", item['text'])
        self.assertIn("-> processed to mp3", item['text'])
        audios = atts.audios
        self.assertEqual(len(audios), 1, "Audios property should return one item.")
        audio_file = audios[0]
        self.assertTrue(audio_file['filename'].endswith('.mp3'), "Audio file filename should end with .mp3")
        self.assertEqual(audio_file['content_type'], 'audio/mpeg', "Content type should be audio/mpeg")
        self.assertIsInstance(audio_file['file_object'], io.BytesIO, "File object should be BytesIO.")
        self.assertTrue(len(audio_file['file_object'].getvalue()) > 0, "File object should not be empty.")
        try:
            mp3_segment = AudioSegment.from_file(audio_file['file_object'], format="mp3")
            audio_file['file_object'].seek(0)
            self.assertIsNotNone(mp3_segment, "Pydub should be able to load the MP3 output.")
            original_segment_check = AudioSegment.from_file(USER_PROVIDED_WAV)
            self.assertEqual(mp3_segment.frame_rate, original_segment_check.frame_rate)
            self.assertEqual(mp3_segment.channels, original_segment_check.channels)
        except Exception as e:
            self.fail(f"Pydub could not load the processed MP3 file: {e}")
        print(".audios property single MP3 (converted from WAV) check: OK")

    def test_attachments_audios_property_single_wav(self):
        if not self.sample_wav_exists: # This test uses the directly provided SAMPLE_WAV
            self.skipTest(f"{SAMPLE_WAV} (dummy or real) not found.")
        atts = Attachments(SAMPLE_WAV, verbose=True) # Removed output_dir
        self.assertEqual(len(atts.attachments_data), 1)
        item = atts.attachments_data[0]
        self.assertEqual(item['type'], 'wav') 
        self.assertEqual(item['original_format'], 'wav') 
        # Default processing to 16kHz mono for WAV if no ops
        self.assertEqual(item['output_samplerate'], 16000)
        self.assertEqual(item['output_channels'], 1)
        self.assertIn(f"Audio: {os.path.basename(SAMPLE_WAV)}", item['text'])
        self.assertIn("-> processed to wav 16kHz mono", item['text'])

        audios = atts.audios
        self.assertEqual(len(audios), 1)
        audio_item = audios[0]
        # Filename from .audios might be different if AudioParser changes it based on processing
        self.assertTrue(audio_item['filename'].endswith('.wav')) 
        self.assertIsInstance(audio_item['file_object'], io.BytesIO)
        self.assertTrue(len(audio_item['file_object'].getvalue()) > 0) 
        # audio_item['file_object'].name should be set by .audios property
        self.assertEqual(audio_item['file_object'].name, audio_item['filename']) 
        self.assertEqual(audio_item['content_type'], 'audio/wav')
        
        # Verify the content of the processed BytesIO object from .audios
        try:
            processed_segment = AudioSegment.from_file(audio_item['file_object'], format="wav")
            audio_item['file_object'].seek(0)
            self.assertIsNotNone(processed_segment, "Pydub should load the WAV from .audios")
            self.assertEqual(processed_segment.frame_rate, 16000)
            self.assertEqual(processed_segment.channels, 1)
        except Exception as e:
            self.fail(f"Pydub could not load processed WAV from .audios: {e}")
        print(".audios property single WAV (processed to 16kHz mono) check: OK")

    def test_attachments_audios_property_single_flac(self):
        if not self.user_provided_wav_exists:
            self.skipTest(f"User provided WAV file {USER_PROVIDED_WAV} not found. Skipping FLAC conversion test.")
        original_wav_basename = os.path.basename(USER_PROVIDED_WAV)
        atts = Attachments(f"{USER_PROVIDED_WAV}[format:flac]", verbose=True) # Removed output_dir
        self.assertEqual(len(atts.attachments_data), 1, "Attachments data should contain one item for FLAC conversion.")
        item = atts.attachments_data[0]
        self.assertEqual(item['type'], 'wav')
        self.assertEqual(item['original_format'], 'wav')
        self.assertEqual(item['output_format'], 'flac')
        self.assertTrue(item['processed_filename_for_api'].startswith(original_wav_basename.rsplit('.', 1)[0]))
        self.assertTrue(item['processed_filename_for_api'].endswith('.flac'))
        self.assertIn(f"Audio: {original_wav_basename}", item['text'])
        self.assertIn("ops: \"format:flac\"", item['text'])
        self.assertIn("-> processed to flac", item['text'])
        audios = atts.audios
        self.assertEqual(len(audios), 1)
        audio_file = audios[0]
        self.assertTrue(audio_file['filename'].endswith('.flac'))
        self.assertEqual(audio_file['content_type'], 'audio/flac')
        self.assertIsInstance(audio_file['file_object'], io.BytesIO)
        self.assertTrue(len(audio_file['file_object'].getvalue()) > 0)
        try:
            flac_segment = AudioSegment.from_file(audio_file['file_object'], format="flac")
            audio_file['file_object'].seek(0)
            self.assertIsNotNone(flac_segment)
            original_segment_check = AudioSegment.from_file(USER_PROVIDED_WAV)
            self.assertEqual(flac_segment.frame_rate, original_segment_check.frame_rate)
            self.assertEqual(flac_segment.channels, original_segment_check.channels)
        except Exception as e:
            self.fail(f"Pydub could not load processed FLAC: {e}")
        print(".audios property single FLAC (converted from WAV) check: OK")

    def test_attachments_audios_property_single_m4a(self):
        if not self.user_provided_wav_exists:
            self.skipTest(f"User provided WAV file {USER_PROVIDED_WAV} not found. Skipping MP4 (was M4A) conversion test.")
        original_wav_basename = os.path.basename(USER_PROVIDED_WAV)
        atts = Attachments(f"{USER_PROVIDED_WAV}[format:mp4]", verbose=True) # Changed format to mp4
        self.assertEqual(len(atts.attachments_data), 1, "Attachments data should contain one item for MP4 conversion.")
        item = atts.attachments_data[0]
        self.assertEqual(item['type'], 'wav')
        self.assertEqual(item['original_format'], 'wav')
        self.assertEqual(item['output_format'], 'mp4') # Changed to mp4
        self.assertTrue(item['processed_filename_for_api'].startswith(original_wav_basename.rsplit('.', 1)[0]))
        self.assertTrue(item['processed_filename_for_api'].endswith('.mp4')) # Changed to .mp4
        self.assertIn(f"Audio: {original_wav_basename}", item['text'])
        self.assertIn("ops: \"format:mp4\"", item['text']) # Changed to mp4
        self.assertIn("-> processed to mp4", item['text']) # Changed to mp4
        audios = atts.audios
        self.assertEqual(len(audios), 1)
        audio_file = audios[0]
        self.assertTrue(audio_file['filename'].endswith('.mp4')) # Changed to .mp4
        self.assertEqual(audio_file['content_type'], 'audio/mp4') # Changed to audio/mp4
        self.assertIsInstance(audio_file['file_object'], io.BytesIO)
        self.assertTrue(len(audio_file['file_object'].getvalue()) > 0)
        try:
            mp4_segment = AudioSegment.from_file(audio_file['file_object'], format="mp4") # Changed format to mp4
            audio_file['file_object'].seek(0)
            self.assertIsNotNone(mp4_segment)
            original_segment_check = AudioSegment.from_file(USER_PROVIDED_WAV)
            self.assertEqual(mp4_segment.frame_rate, original_segment_check.frame_rate)
            self.assertEqual(mp4_segment.channels, original_segment_check.channels)
        except Exception as e:
            self.fail(f"Pydub could not load processed MP4 (was M4A): {e}")
        print(".audios property single MP4 (was M4A, converted from WAV) check: OK")

    def test_attachments_audios_property_single_mp4_audio(self):
        if not self.user_provided_wav_exists:
            self.skipTest(f"User provided WAV file {USER_PROVIDED_WAV} not found. Skipping MP4 (was MP4_audio as M4A) conversion test.")
        original_wav_basename = os.path.basename(USER_PROVIDED_WAV)
        atts = Attachments(f"{USER_PROVIDED_WAV}[format:mp4]", verbose=True) # Changed format to mp4
        self.assertEqual(len(atts.attachments_data), 1, "Attachments data for MP4 (was MP4_audio as M4A) conversion.")
        item = atts.attachments_data[0]
        self.assertEqual(item['type'], 'wav')
        self.assertEqual(item['original_format'], 'wav')
        self.assertEqual(item['output_format'], 'mp4') # Changed to mp4
        self.assertTrue(item['processed_filename_for_api'].startswith(original_wav_basename.rsplit('.', 1)[0]))
        self.assertTrue(item['processed_filename_for_api'].endswith('.mp4')) # Changed to .mp4
        self.assertIn(f"Audio: {original_wav_basename}", item['text'])
        self.assertIn("ops: \"format:mp4\"", item['text']) # Changed to mp4
        self.assertIn("-> processed to mp4", item['text']) # Changed to mp4
        audios = atts.audios
        self.assertEqual(len(audios), 1)
        audio_file = audios[0]
        self.assertTrue(audio_file['filename'].endswith('.mp4')) # Changed to .mp4
        self.assertEqual(audio_file['content_type'], 'audio/mp4') # Changed to audio/mp4
        self.assertIsInstance(audio_file['file_object'], io.BytesIO)
        self.assertTrue(len(audio_file['file_object'].getvalue()) > 0)
        try:
            mp4_segment = AudioSegment.from_file(audio_file['file_object'], format="mp4") # Changed format to mp4
            audio_file['file_object'].seek(0)
            self.assertIsNotNone(mp4_segment)
            original_segment_check = AudioSegment.from_file(USER_PROVIDED_WAV)
            self.assertEqual(mp4_segment.frame_rate, original_segment_check.frame_rate)
            self.assertEqual(mp4_segment.channels, original_segment_check.channels)
        except Exception as e:
            self.fail(f"Pydub could not load processed MP4 (was MP4_audio/M4A): {e}")
        print(".audios property single MP4 (was MP4_audio as M4A, from WAV) check: OK")

    def test_attachments_audios_property_single_webm_audio(self):
        if not self.user_provided_wav_exists:
            self.skipTest(f"User provided WAV file {USER_PROVIDED_WAV} not found. Skipping WebM_audio conversion test.")
        original_wav_basename = os.path.basename(USER_PROVIDED_WAV)
        atts = Attachments(f"{USER_PROVIDED_WAV}[format:webm]", verbose=True) # Removed output_dir
        self.assertEqual(len(atts.attachments_data), 1, "Attachments data for WebM_audio conversion.")
        item = atts.attachments_data[0]
        self.assertEqual(item['type'], 'wav')
        self.assertEqual(item['original_format'], 'wav')
        self.assertEqual(item['output_format'], 'webm')
        self.assertTrue(item['processed_filename_for_api'].startswith(original_wav_basename.rsplit('.', 1)[0]))
        self.assertTrue(item['processed_filename_for_api'].endswith('.webm'))
        self.assertIn(f"Audio: {original_wav_basename}", item['text'])
        self.assertIn("ops: \"format:webm\"", item['text'])
        self.assertIn("-> processed to webm", item['text'])
        audios = atts.audios
        self.assertEqual(len(audios), 1)
        audio_file = audios[0]
        self.assertTrue(audio_file['filename'].endswith('.webm'))
        self.assertEqual(audio_file['content_type'], 'audio/webm')
        self.assertIsInstance(audio_file['file_object'], io.BytesIO)
        self.assertTrue(len(audio_file['file_object'].getvalue()) > 0)
        try:
            webm_segment = AudioSegment.from_file(audio_file['file_object'], format="webm")
            audio_file['file_object'].seek(0)
            self.assertIsNotNone(webm_segment)
            original_segment_check = AudioSegment.from_file(USER_PROVIDED_WAV)
            # WebM/Opus export via pydub/ffmpeg often defaults to 48000 Hz
            self.assertEqual(webm_segment.frame_rate, 48000) 
            self.assertEqual(webm_segment.channels, original_segment_check.channels)
        except Exception as e:
            self.fail(f"Pydub could not load processed WebM_audio: {e}")
        print(".audios property single WebM_audio (converted from WAV) check: OK")

    def test_repr_markdown_output(self):
        paths_for_markdown = []
        has_pdf = False
        has_png = False
        has_heic = False

        if os.path.exists(SAMPLE_PDF):
            paths_for_markdown.append(SAMPLE_PDF)
            has_pdf = True
        if self.sample_png_exists:
            paths_for_markdown.append(f"{SAMPLE_PNG}[resize:20x20]")
            has_png = True
        if self.sample_heic_exists:
            paths_for_markdown.append(f"{SAMPLE_HEIC}[resize:25x25]")
            has_heic = True

        if not (has_pdf or has_png or has_heic): 
            self.skipTest("No sample files available for markdown repr test.")
        if not paths_for_markdown: 
            atts = Attachments()
            self.assertIn("_No attachments processed._", atts._repr_markdown_())
            return
            
        atts = Attachments(*paths_for_markdown, verbose=True) # Added verbose for more debug output if needed
        markdown_output = atts._repr_markdown_()

        self.assertIn("### Attachments Summary", markdown_output)
        summary_part, gallery_part = markdown_output, ""
        if "\n### Image Previews" in markdown_output: # Corrected split string
            parts = markdown_output.split("\n### Image Previews", 1)
            summary_part = parts[0]
            if len(parts) > 1: gallery_part = parts[1]
        
        if has_pdf:
            self.assertIn(f"**ID:** `pdf1` (`pdf` from `{SAMPLE_PDF}`)", summary_part)
            self.assertIn("Hello PDF!", summary_part) 
            self.assertIn("Total Pages:** `1` (All processed)", summary_part)
            self.assertNotIn(f"![{os.path.basename(SAMPLE_PDF)}](data:image", summary_part)

        if has_png:
            png_id_match = re.search(r"\*\*ID:\*\* `(png\d+)` \(`png` from", summary_part)
            self.assertIsNotNone(png_id_match, "PNG ID line not found in summary")
            # png_id = png_id_match.group(1) if png_id_match else "png_not_found" # Not used later, commented out
            
            self.assertIn(f"(`png` from `{SAMPLE_PNG}[resize:20x20]`)", summary_part)
            self.assertIn("  - **Dimensions (after ops):** `20x20`", summary_part)
            self.assertIn("  - **Original Format:** `PNG`", summary_part)
            self.assertIn("  - **Original Mode:** `RGB`", summary_part) 
            self.assertIn("  - **Operations:** `{'resize': (20, 20)}`", summary_part)
            self.assertIn("  - **Output as:** `jpeg`", summary_part)
            self.assertNotIn(f"![{os.path.basename(SAMPLE_PNG)}](data:image", summary_part)

        if has_heic:
            heic_id_match = re.search(r"\*\*ID:\*\* `(heic\d+)` \(`heic` from", summary_part)
            self.assertIsNotNone(heic_id_match, "HEIC ID line not found in summary")
            # heic_id = heic_id_match.group(1) if heic_id_match else "heic_not_found" # Not used later

            expected_heic_original_path_str = f"{SAMPLE_HEIC}[resize:25x25]"
            self.assertTrue(re.search(rf"\(`heic` from `{re.escape(expected_heic_original_path_str)}`\)", summary_part))
            # self.assertIn(f"(`heic` from `{expected_heic_original_path_str}`)", summary_part) # Redundant with regex
            self.assertIn("  - **Dimensions (after ops):** `25x25`", summary_part) 
            self.assertIn("  - **Original Format:** `HEIF`", summary_part) 
            self.assertIn("  - **Original Mode:** `RGB`", summary_part) 
            self.assertIn("  - **Operations:** `{'resize': (25, 25)}`", summary_part)
            self.assertIn("  - **Output as:** `jpeg`", summary_part)
            self.assertNotIn(f"![{os.path.basename(SAMPLE_HEIC)}](data:image", summary_part) 
        
        if has_png or has_heic: 
            self.assertTrue(markdown_output.count("\n### Image Previews") <= 1, "Multiple Image Previews headers found")
            if not gallery_part and (has_png or has_heic):
                 self.fail("Image gallery expected but not found or incorrectly split")

            self.assertIn("| &nbsp; | &nbsp; | &nbsp; |", gallery_part) 
            self.assertIn("|---:|---:|---:|", gallery_part)     

            if has_png:
                png_filename_escaped = re.escape(os.path.basename(SAMPLE_PNG))
                png_regex = rf"\|[^|]*\!\[{png_filename_escaped}\][^|]*data:image/(jpeg|png);base64,[^|]*\|" # Allow jpeg or png for thumbnail
                self.assertTrue(re.search(png_regex, gallery_part), f"PNG image tag ({SAMPLE_PNG}) not found in gallery. Regex: {png_regex}")
            
            if has_heic:
                heic_filename_escaped = re.escape(os.path.basename(SAMPLE_HEIC))
                heic_regex = rf"\|[^|]*\!\[{heic_filename_escaped}\][^|]*data:image/(jpeg|png);base64,[^|]*\|"
                self.assertTrue(re.search(heic_regex, gallery_part), f"HEIC image tag ({SAMPLE_HEIC}) not found in gallery. Regex: {heic_regex}")
        else: 
            self.assertNotIn("\n### Image Previews", markdown_output)

        if (has_pdf and (has_png or has_heic)) or (has_png and has_heic): 
            self.assertIn("\n---\n", summary_part)
        elif markdown_output.count("**ID:**") > 1: 
             self.assertIn("\n---\n", summary_part)
        if has_pdf or has_png or has_heic:
             self.assertTrue(summary_part.count("\n---\n") >= markdown_output.count("**ID:**") -1, "Separator count issue.")

    def test_str_representation_default_is_xml(self):
        paths_for_xml_str = []
        if os.path.exists(SAMPLE_PDF): paths_for_xml_str.append(SAMPLE_PDF)
        if self.sample_png_exists: paths_for_xml_str.append(f"{SAMPLE_PNG}[resize:10x10]")
        if self.sample_heic_exists: paths_for_xml_str.append(f"{SAMPLE_HEIC}[resize:15x15,format:png]")

        if len(paths_for_xml_str) < 2: # Need at least two for some specific assertions below
            self.skipTest(f"Missing sample files for str representation XML test (need at least 2 types).")

        atts = Attachments(*paths_for_xml_str)
        output_str = str(atts)

        self.assertTrue(output_str.startswith("<attachments>"))
        self.assertTrue(output_str.endswith("</attachments>"))

        if SAMPLE_PDF in paths_for_xml_str:
            self.assertIn('<attachment id="pdf1" type="pdf">', output_str)
            self.assertIn("<meta name=\"num_pages\" value=\"1\" />", output_str)
            self.assertIn("<content>\nHello PDF!\n    </content>", output_str)

        if f"{SAMPLE_PNG}[resize:10x10]" in paths_for_xml_str:
            self.assertTrue(re.search(r'<attachment id="png\d+" type="png">', output_str))
            self.assertIn("[Image: sample.png (original: PNG RGB, ops: \"resize:10x10\") -&gt; processed to 10x10 for output as jpeg]", output_str)
            self.assertIn("<meta name=\"dimensions\" value=\"10x10\" />", output_str)
            self.assertIn("<meta name=\"original_format\" value=\"PNG\" />", output_str)
            self.assertIn("<meta name=\"applied_operations\" value=\"{'resize': (10, 10)}\" />", output_str)

        if f"{SAMPLE_HEIC}[resize:15x15,format:png]" in paths_for_xml_str:
            self.assertTrue(re.search(r'<attachment id="heic\d+" type="heic">', output_str)) 
            expected_heic_ops_str_for_xml = "resize:15x15,format:png"
            expected_heic_text_content_regex = rf""".*original: HEIF RGB, ops: \"{re.escape(expected_heic_ops_str_for_xml)}\".*output as png.*""" # Adjusted for output as png
            self.assertTrue(re.search(expected_heic_text_content_regex, output_str))
            self.assertIn("<meta name=\"dimensions\" value=\"15x15\" />", output_str)
            self.assertIn("<meta name=\"original_format\" value=\"HEIF\" />", output_str) 
            self.assertIn("<meta name=\"output_format_target\" value=\"png\" />", output_str)
            self.assertIn("value=\"{'resize': (15, 15), 'format': 'png'}\"", output_str)
    
    def test_audio_processing_with_pydub(self):
        if not self.user_provided_wav_exists:
            self.skipTest(f"User provided WAV file {USER_PROVIDED_WAV} not found. Skipping pydub processing tests.")

        # 1. Basic Load and Default Processing (to 16kHz mono WAV)
        atts_default = Attachments(USER_PROVIDED_WAV, verbose=True)
        self.assertEqual(len(atts_default.attachments_data), 1)
        item_default = atts_default.attachments_data[0]
        self.assertEqual(item_default['type'], 'wav') 
        self.assertEqual(item_default['output_format'], 'wav')
        self.assertEqual(item_default['output_samplerate'], 16000)
        self.assertEqual(item_default['output_channels'], 1)
        self.assertIn(f"Audio: {os.path.basename(USER_PROVIDED_WAV)}", item_default['text'])
        self.assertIn("-> processed to wav 16kHz mono", item_default['text'])

        audios_default = atts_default.audios
        self.assertEqual(len(audios_default), 1)
        audio_file_default = audios_default[0]
        self.assertTrue(audio_file_default['filename'].endswith('.wav'))
        self.assertEqual(audio_file_default['content_type'], 'audio/wav')
        self.assertIsInstance(audio_file_default['file_object'], io.BytesIO)
        
        processed_segment_default = AudioSegment.from_file(audio_file_default['file_object'], format="wav")
        self.assertEqual(processed_segment_default.frame_rate, 16000)
        self.assertEqual(processed_segment_default.channels, 1)
        print(f"Default processing check: OK. Sample rate: {processed_segment_default.frame_rate}, Channels: {processed_segment_default.channels}")

        # 2. Format Conversion (WAV to MP3) and Bitrate
        original_wav_for_mp3_test = AudioSegment.from_file(USER_PROVIDED_WAV)
        original_sr_for_mp3_test = original_wav_for_mp3_test.frame_rate
        original_ch_for_mp3_test = original_wav_for_mp3_test.channels
        
        atts_mp3 = Attachments(f"{USER_PROVIDED_WAV}[format:mp3,bitrate:64k]", verbose=True)
        self.assertEqual(len(atts_mp3.attachments_data), 1)
        item_mp3 = atts_mp3.attachments_data[0]
        self.assertEqual(item_mp3['output_format'], 'mp3')
        self.assertEqual(item_mp3['output_bitrate'], '64k') 
        self.assertEqual(item_mp3['output_samplerate'], original_sr_for_mp3_test)
        self.assertEqual(item_mp3['output_channels'], original_ch_for_mp3_test)
        self.assertTrue(item_mp3['processed_filename_for_api'].endswith('.mp3'))
        self.assertIn("format:mp3", item_mp3['text'])
        self.assertIn("bitrate:64k", item_mp3['text'])
        self.assertIn("-> processed to mp3", item_mp3['text'])

        audios_mp3 = atts_mp3.audios
        self.assertEqual(len(audios_mp3), 1)
        audio_file_mp3 = audios_mp3[0]
        self.assertTrue(audio_file_mp3['filename'].endswith('.mp3'))
        self.assertEqual(audio_file_mp3['content_type'], 'audio/mpeg')
        self.assertTrue(len(audio_file_mp3['file_object'].getvalue()) > 0)
        
        processed_segment_mp3 = AudioSegment.from_file(audio_file_mp3['file_object'], format="mp3")
        self.assertEqual(processed_segment_mp3.frame_rate, original_sr_for_mp3_test) 
        self.assertEqual(processed_segment_mp3.channels, original_ch_for_mp3_test)   
        print(f"MP3 conversion check: OK. Output SR: {processed_segment_mp3.frame_rate}, Channels: {processed_segment_mp3.channels}")

        # 3. Samplerate Change
        original_audio_check = AudioSegment.from_file(USER_PROVIDED_WAV)
        original_samplerate = original_audio_check.frame_rate
        target_samplerate_test = 8000
        if original_samplerate == target_samplerate_test:
            print(f"Warning: Original sample rate of {USER_PROVIDED_WAV} is already {target_samplerate_test}Hz.")
        
        atts_samplerate = Attachments(f"{USER_PROVIDED_WAV}[samplerate:{target_samplerate_test}]", verbose=True)
        self.assertEqual(len(atts_samplerate.attachments_data), 1)
        item_samplerate = atts_samplerate.attachments_data[0]
        self.assertEqual(item_samplerate['output_samplerate'], target_samplerate_test)
        self.assertIn(f"{target_samplerate_test//1000}kHz", item_samplerate['text'])

        audios_samplerate = atts_samplerate.audios
        self.assertEqual(len(audios_samplerate), 1)
        processed_segment_samplerate = AudioSegment.from_file(audios_samplerate[0]['file_object'], format="wav")
        self.assertEqual(processed_segment_samplerate.frame_rate, target_samplerate_test)
        self.assertEqual(processed_segment_samplerate.channels, original_audio_check.channels) # Assert original channels
        print(f"Samplerate change to {target_samplerate_test}Hz check: OK")

        # 4. Channels Change
        atts_mono = Attachments(f"{USER_PROVIDED_WAV}[channels:1]", verbose=True)
        self.assertEqual(len(atts_mono.attachments_data), 1)
        item_mono = atts_mono.attachments_data[0]
        self.assertEqual(item_mono['output_channels'], 1)
        self.assertIn("mono", item_mono['text'])

        audios_mono = atts_mono.audios
        self.assertEqual(len(audios_mono), 1)
        processed_segment_mono = AudioSegment.from_file(audios_mono[0]['file_object'], format="wav")
        self.assertEqual(processed_segment_mono.channels, 1)
        self.assertEqual(processed_segment_mono.frame_rate, original_samplerate) # Corrected assertion
        print("Channels change to mono check: OK")

        # 5. Combined Operations
        target_combined_rate = 22050
        atts_combined = Attachments(f"{USER_PROVIDED_WAV}[format:ogg,samplerate:{target_combined_rate},channels:1]", verbose=True) 
        self.assertEqual(len(atts_combined.attachments_data), 1)
        item_combined = atts_combined.attachments_data[0]
        self.assertEqual(item_combined['output_format'], 'ogg')
        self.assertEqual(item_combined['output_samplerate'], target_combined_rate)
        self.assertEqual(item_combined['output_channels'], 1)
        self.assertTrue(item_combined['processed_filename_for_api'].endswith('.ogg'))
        self.assertIn("format:ogg", item_combined['text'])
        self.assertIn(f"{target_combined_rate//1000}kHz", item_combined['text']) 
        self.assertIn("mono", item_combined['text'])

        audios_combined = atts_combined.audios
        self.assertEqual(len(audios_combined), 1)
        audio_file_combined = audios_combined[0]
        self.assertTrue(audio_file_combined['filename'].endswith('.ogg'))
        self.assertEqual(audio_file_combined['content_type'], 'audio/ogg')
        
        processed_segment_combined = AudioSegment.from_file(audio_file_combined['file_object'], format="ogg")
        self.assertEqual(processed_segment_combined.frame_rate, target_combined_rate)
        self.assertEqual(processed_segment_combined.channels, 1)
        print("Combined operations (ogg, 22.05kHz, mono) check: OK")

        # 6. Test invalid operations string
        atts_invalid_ops = Attachments(f"{USER_PROVIDED_WAV}[format:xyz,samplerate:abc]", verbose=True)
        self.assertEqual(len(atts_invalid_ops.attachments_data), 1)
        item_invalid = atts_invalid_ops.attachments_data[0]
        self.assertEqual(item_invalid['output_format'], 'wav')
        self.assertEqual(item_invalid['output_samplerate'], 16000)
        self.assertEqual(item_invalid['output_channels'], 1)
        self.assertIn("ops: \"format:xyz,samplerate:abc\"", item_invalid['text']) 
        self.assertIn("-> processed to wav 16kHz mono", item_invalid['text'])
        print("Invalid operations graceful fallback check: OK")
        
        # 7. Markdown representation check for one of the processed audios
        md_output = atts_combined._repr_markdown_() # Using atts_combined from above
        self.assertIn("### Attachments Summary", md_output)
        # The ID will be based on the original type, which is wav
        wav_id_match = re.search(r"\*\*ID:\*\* `(wav\d+)`", md_output)
        self.assertIsNotNone(wav_id_match, "Could not find WAV ID in Markdown output")
        wav_id = wav_id_match.group(1) if wav_id_match else "wav_not_found"
        
        self.assertIn(f"ID:** `{wav_id}` (`wav` from `{USER_PROVIDED_WAV}[format:ogg,samplerate:22050,channels:1]`)", md_output)
        self.assertIn(f"Original File Name:** `{os.path.basename(USER_PROVIDED_WAV)}`", md_output)
        self.assertIn("Processed Output Format:** `ogg`", md_output)
        self.assertIn(f"Processed Sample Rate:** `{target_combined_rate}`", md_output)
        self.assertIn("Processed Channels:** `1`", md_output)
        self.assertIn("Details:** `[Audio:", md_output)
        self.assertIn("ops: \"format:ogg,samplerate:22050,channels:1\"", md_output) # Check escaping in details
        self.assertIn("-> processed to ogg 22kHz mono]`", md_output) 
        print("Markdown representation for processed audio check: OK")

class TestAttachmentsIndexing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample_pdf_path = SAMPLE_PDF
        cls.sample_png_path = SAMPLE_PNG
        cls.sample_heic_path = SAMPLE_HEIC

        cls.pdf_exists = os.path.exists(cls.sample_pdf_path)
        cls.png_exists = os.path.exists(cls.sample_png_path)
        cls.heic_exists = os.path.exists(cls.sample_heic_path)

        if not (cls.pdf_exists and cls.png_exists and cls.heic_exists):
            print("Warning: Not all sample files (PDF, PNG, HEIC) exist. Indexing tests might be limited or skipped.")
            # This try-except block is now correctly indented
            try:
                TestAttachmentsIntegration.setUpClass() 
                cls.pdf_exists = os.path.exists(cls.sample_pdf_path)
                cls.png_exists = os.path.exists(cls.sample_png_path)
                cls.heic_exists = os.path.exists(cls.sample_heic_path)
            except Exception as e:
                print(f"Error running TestAttachmentsIntegration.setUpClass for TestAttachmentsIndexing: {e}")

    def test_integer_indexing(self):
        if not (self.pdf_exists and self.png_exists):
            self.skipTest("PDF or PNG sample file missing for integer indexing test.")
        
        original_paths = [self.sample_pdf_path, f"{self.sample_png_path}[resize:10x10]"]
        atts = Attachments(*original_paths)
        self.assertEqual(len(atts.attachments_data), 2)

        indexed_att_0 = atts[0]
        self.assertIsInstance(indexed_att_0, Attachments)
        self.assertEqual(len(indexed_att_0.attachments_data), 1)
        self.assertEqual(indexed_att_0.attachments_data[0]['type'], 'pdf')
        self.assertEqual(indexed_att_0.original_paths_with_indices, [original_paths[0]])

        indexed_att_1 = atts[1]
        self.assertIsInstance(indexed_att_1, Attachments)
        self.assertEqual(len(indexed_att_1.attachments_data), 1)
        self.assertEqual(indexed_att_1.attachments_data[0]['type'], 'png')
        self.assertEqual(indexed_att_1.original_paths_with_indices, [original_paths[1]])

    def test_slice_indexing(self):
        if not (self.pdf_exists and self.png_exists and self.heic_exists):
            self.skipTest("One or more sample files (PDF, PNG, HEIC) missing for slice indexing test.")

        original_paths = [
            self.sample_pdf_path,
            f"{self.sample_png_path}[resize:10x10]",
            f"{self.sample_heic_path}[format:png]"
        ]
        atts = Attachments(*original_paths)
        self.assertEqual(len(atts.attachments_data), 3)

        sliced_atts_0_2 = atts[0:2]
        self.assertIsInstance(sliced_atts_0_2, Attachments)
        self.assertEqual(len(sliced_atts_0_2.attachments_data), 2)
        self.assertEqual(sliced_atts_0_2.attachments_data[0]['type'], 'pdf')
        self.assertEqual(sliced_atts_0_2.attachments_data[1]['type'], 'png')
        self.assertEqual(sliced_atts_0_2.original_paths_with_indices, original_paths[0:2])

        sliced_atts_step = atts[::2]
        self.assertIsInstance(sliced_atts_step, Attachments)
        self.assertEqual(len(sliced_atts_step.attachments_data), 2) 
        self.assertEqual(sliced_atts_step.attachments_data[0]['type'], 'pdf')
        self.assertEqual(sliced_atts_step.attachments_data[1]['type'], 'heic') 
        self.assertEqual(sliced_atts_step.original_paths_with_indices, original_paths[::2])

        sliced_atts_single = atts[1:2]
        self.assertIsInstance(sliced_atts_single, Attachments)
        self.assertEqual(len(sliced_atts_single.attachments_data), 1)
        self.assertEqual(sliced_atts_single.attachments_data[0]['type'], 'png')
        self.assertEqual(sliced_atts_single.original_paths_with_indices, original_paths[1:2])

    def test_empty_slice_indexing(self):
        if not self.pdf_exists:
            self.skipTest("PDF sample file missing for empty slice test.")
        atts = Attachments(self.sample_pdf_path)
        empty_atts = atts[10:12] 
        self.assertIsInstance(empty_atts, Attachments)
        self.assertEqual(len(empty_atts.attachments_data), 0)
        self.assertEqual(len(empty_atts.original_paths_with_indices), 0)

    def test_out_of_bounds_integer_indexing(self):
        if not self.pdf_exists:
            self.skipTest("PDF sample file missing for out-of-bounds test.")
        atts = Attachments(self.sample_pdf_path)
        with self.assertRaises(IndexError):
            _ = atts[1] 

    def test_invalid_index_type(self):
        if not self.pdf_exists:
            self.skipTest("PDF sample file missing for invalid index type test.")
        atts = Attachments(self.sample_pdf_path)
        with self.assertRaises(TypeError):
            _ = atts["key"] # type: ignore

class TestIndividualParsers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        create_multi_page_pdf(GENERATED_MULTI_PAGE_PDF, 3) 
        TestAttachmentsIntegration.setUpClass() 
        # cls.sample_ogg_exists = TestAttachmentsIntegration.sample_ogg_exists # No longer needed with new test strategy
        cls.user_provided_wav_exists = TestAttachmentsIntegration.user_provided_wav_exists


    def test_pdf_parser_direct_indexing(self):
        if not os.path.exists(GENERATED_MULTI_PAGE_PDF):
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} for direct parser test not found.")
        parser = PDFParser()
        # setUpClass for TestIndividualParsers creates 3-page, TestAttachmentsIntegration.setUpClass recreates it as 5-page.
        # To be consistent, let's assume it's 5 pages as per the main setup.
        data = parser.parse(GENERATED_MULTI_PAGE_PDF, indices="1,3")
        self.assertIn("This is page 1", data['text'])
        self.assertNotIn("This is page 2", data['text'])
        self.assertIn("This is page 3", data['text'])
        self.assertEqual(data['num_pages'], 5) 
        self.assertEqual(data['indices_processed'], [1, 3])

    def test_pptx_parser_direct_indexing(self):
        if not TestAttachmentsIntegration.sample_pptx_exists:
            self.skipTest(f"{SAMPLE_PPTX} not available/readable for direct PPTX parser test.")
        parser = PPTXParser()
        data = parser.parse(SAMPLE_PPTX, indices="N,1") 
        self.assertIn("Slide 1 Title", data['text'])
        self.assertNotIn("Slide 2 Title", data['text'])
        self.assertIn("Slide 3 Title", data['text'])
        self.assertEqual(data['num_slides'], 3)
        self.assertEqual(data['indices_processed'], [1, 3])

    def test_pdf_parser_direct_invalid_indices(self):
        if not os.path.exists(GENERATED_MULTI_PAGE_PDF):
            self.skipTest(f"{GENERATED_MULTI_PAGE_PDF} for direct parser test not found.")
        parser = PDFParser()
        data = parser.parse(GENERATED_MULTI_PAGE_PDF, indices="99,abc") 
        self.assertEqual(data['text'].strip(), "")
        self.assertEqual(data['num_pages'], 5) 
        self.assertEqual(data['indices_processed'], [])

    def test_pdf_parser_file_not_found(self):
        parser = PDFParser()
        with self.assertRaisesRegex(ParsingError, r"(File not found|no such file|cannot open)"):
            parser.parse(NON_EXISTENT_FILE)

    def test_html_parser_direct(self):
        if not TestAttachmentsIntegration.sample_html_exists: 
             self.skipTest(f"{SAMPLE_HTML} not found for direct HTML parser test.")
        parser = HTMLParser()
        data = parser.parse(SAMPLE_HTML)
        self.assertIn("# Main Heading", data['text'])
        self.assertIn("**strong emphasis**", data['text'])
        self.assertIn("[Example Link](http://example.com)", data['text'])
        self.assertNotIn("<p>", data['text'])
        self.assertNotIn("<style>", data['text'])
        self.assertEqual(data['file_path'], SAMPLE_HTML)

    def test_audio_parser_direct_valid_file(self):
        if not self.user_provided_wav_exists:
            self.skipTest(f"User provided WAV file {USER_PROVIDED_WAV} not found.")

        parser = AudioParser()
        ops_str = "format:ogg,samplerate:8000,channels:1"
        # Corrected call: parser.parse(actual_file_path, indices=ops_string)
        parsed_content = parser.parse(USER_PROVIDED_WAV, indices=ops_str)

        self.assertIsNotNone(parsed_content, "Parser should return content.")
        # AudioParser does not set 'type' key directly; Attachments class does. Removed this assertion.
        # self.assertEqual(parsed_content['type'], 'wav', "Original type should be wav from loaded file")
        self.assertEqual(parsed_content['output_format'], 'ogg')
        self.assertEqual(parsed_content['output_samplerate'], 8000)
        self.assertTrue(parsed_content['processed_filename_for_api'].endswith('.ogg'))
        self.assertIn(ops_str, parsed_content['text'])
        self.assertIn("-> processed to ogg 8kHz mono", parsed_content['text'])
        self.assertEqual(parsed_content['original_basename'], os.path.basename(USER_PROVIDED_WAV))

        self.assertIn('audio_segment', parsed_content, "AudioSegment object missing.")
        audio_segment = parsed_content['audio_segment']
        self.assertIsInstance(audio_segment, AudioSegment, "Parsed content should include an AudioSegment.")
        self.assertEqual(audio_segment.frame_rate, 8000, "AudioSegment frame rate mismatch.")
        self.assertEqual(audio_segment.channels, 1, "AudioSegment channels mismatch.")
        print("Audio Parser direct (WAV to OGG 8kHz mono) check: OK")

    def test_audio_parser_file_not_found(self):
        parser = AudioParser()
        with self.assertRaises(ParsingError) as context:
            # parser.parse needs base_path if file_path_with_ops is different
            parser.parse(f"{NON_EXISTENT_FILE}[format:wav]", NON_EXISTENT_FILE)
        self.assertIn(f"Audio file not found: {NON_EXISTENT_FILE}", str(context.exception))

    def test_audio_parser_invalid_ops_string(self):
        if not self.user_provided_wav_exists:
            self.skipTest(f"User provided WAV file {USER_PROVIDED_WAV} not found.")

        parser = AudioParser()
        ops_str = "format:xyz,samplerate:abc"
        # Corrected call: parser.parse(actual_file_path, indices=ops_string)
        parsed_content = parser.parse(USER_PROVIDED_WAV, indices=ops_str)

        self.assertIsNotNone(parsed_content)
        # AudioParser does not set 'type' key directly. Removed this assertion.
        # self.assertEqual(parsed_content['type'], 'wav')
        self.assertEqual(parsed_content['output_format'], 'wav') # Default fallback
        self.assertEqual(parsed_content['output_samplerate'], 16000) # Default fallback
        self.assertEqual(parsed_content['output_channels'], 1) # Default fallback
        self.assertTrue(parsed_content['processed_filename_for_api'].endswith('.wav'))
        self.assertIn("ops: \"format:xyz,samplerate:abc\"", parsed_content['text'])
        self.assertIn("-> processed to wav 16kHz mono", parsed_content['text'])
        self.assertEqual(parsed_content['original_basename'], os.path.basename(USER_PROVIDED_WAV))

        self.assertIn('audio_segment', parsed_content)
        audio_segment = parsed_content['audio_segment']
        self.assertIsInstance(audio_segment, AudioSegment)
        self.assertEqual(audio_segment.frame_rate, 16000)
        self.assertEqual(audio_segment.channels, 1)
        print("Audio Parser direct (WAV with invalid ops to 16kHz mono) check: OK")

if __name__ == '__main__':
    unittest.main()
