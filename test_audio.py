from attachments import Attachments
import io
import os

# Ensure the example audio file exists
sample_audio_path = "examples/A_Tone.ogg"
if not os.path.exists(sample_audio_path):
    print(f"Error: Sample audio file not found at {sample_audio_path}")
    print("Please make sure 'A_Tone.ogg' is in the 'examples' directory.")
    exit()

print(f"Testing audio processing with: {sample_audio_path}\n")

# Instantiate Attachments with verbose mode for more output
try:
    a = Attachments(sample_audio_path, verbose=True)
except Exception as e:
    print(f"Error during Attachments instantiation: {e}")
    exit()

# Access the .audios property
print("\n--- Accessing .audios property ---")
prepared_audios = None
try:
    prepared_audios = a.audios
except Exception as e:
    print(f"Error accessing .audios property: {e}")
    exit()

if prepared_audios is None:
    print("The .audios property returned None.")
    exit()

print(f"Found {len(prepared_audios)} audio attachment(s).")

# Verify the structure and content
if prepared_audios:
    for i, audio_data in enumerate(prepared_audios):
        print(f"\n--- Audio Attachment #{i+1} ---")
        print(f"Filename: {audio_data.get('filename')}")
        print(f"Content Type (MIME): {audio_data.get('content_type')}")
        
        file_object = audio_data.get('file_object')
        print(f"File Object Type: {type(file_object)}")
        
        if isinstance(file_object, io.BytesIO):
            print(f"File Object Name (.name attribute): {getattr(file_object, 'name', 'Not set')}")
            # Get the size of the BytesIO stream
            file_object.seek(0, io.SEEK_END)
            size_in_bytes = file_object.tell()
            file_object.seek(0) # Reset stream position
            print(f"File Object Size: {size_in_bytes} bytes")
            
            # Check if content seems plausible (first few bytes)
            # For Ogg, it should start with 'OggS'
            first_bytes = file_object.read(4)
            file_object.seek(0) # Reset stream position
            print(f"First 4 bytes of file_object: {first_bytes}")
            if first_bytes == b'OggS':
                print("File object starts with 'OggS', which is correct for an Ogg file.")
            else:
                print(f"Warning: File object does not start with expected Ogg signature. Starts with: {first_bytes}")

        else:
            print("Warning: file_object is not an instance of io.BytesIO.")
            
        print(f"Original item data from attachments_data for this audio file:")
        # Find the corresponding item in a.attachments_data to show what was parsed
        # This relies on original_filename_for_api matching and type.
        original_data = None
        for item in a.attachments_data:
            if item.get('type') in ['oga', 'ogg_audio'] and item.get('original_filename_for_api') == audio_data.get('filename'):
                original_data = item
                break
        if original_data:
            print(f"  ID: {original_data.get('id')}")
            print(f"  Type: {original_data.get('type')}")
            print(f"  Original Path String: {original_data.get('original_path_str')}")
            print(f"  File Path (source): {original_data.get('file_path')}")
            print(f"  Raw Path (used by .audios): {original_data.get('raw_path')}")
            print(f"  Text Representation: {original_data.get('text')}")
            print(f"  MIME Type (in attachments_data): {original_data.get('mime_type')}")
        else:
            print("  Could not find matching original data in a.attachments_data based on filename and type.")

else:
    print("No audio attachments were prepared.")

print("\n--- XML Output (str(a)) ---")
try:
    print(str(a))
except Exception as e:
    print(f"Error generating XML output: {e}")

print("\nTest script finished.") 