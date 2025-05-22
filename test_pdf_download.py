from attachments import Attachments
import os

print("[TestScript] Starting PDF download verification test.")
pdf_url = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
output_pdf_filename = "downloaded_dummy.pdf"

# Clean up previous downloaded PDF if it exists
if os.path.exists(output_pdf_filename):
    os.remove(output_pdf_filename)
    print(f"[TestScript] Removed existing {output_pdf_filename}")

print(f"[TestScript] Initializing Attachments with URL: {pdf_url}")
attachments_collection = Attachments(pdf_url)

if not attachments_collection:
    print("[TestScript] Attachments collection is empty. Could not fetch the URL.")
else:
    # Assuming the URL results in a single attachment
    # If Attachments(url) can return multiple, you might need to iterate
    # or be more specific. For a direct URL, it's usually one.
    if len(attachments_collection) > 0:
        a = attachments_collection[0] # Get the first attachment object
        print(f"\n[TestScript] Attachment object: {a}")
        print(f"[TestScript] Attachment original URL (a.original): {a.original}")
        print(f"[TestScript] Attachment path (a.path where loader might save it): {a.path}")
        
        # Check the stream
        if hasattr(a, 'stream') and a.stream is not None:
            try:
                a.stream.seek(0) # Ensure we are at the beginning of the stream
                pdf_bytes = a.stream.read()
                a.stream.seek(0) # Reset stream position again for further use by other parts

                print(f"[TestScript] Length of a.stream content: {len(pdf_bytes)} bytes")
                print(f"[TestScript] First 200 bytes of a.stream: {pdf_bytes[:200]}")

                if pdf_bytes.startswith(b'%PDF-'):
                    print("[TestScript] Stream starts with PDF magic bytes. Looks like a PDF.")
                else:
                    print("[TestScript] Stream does NOT start with PDF magic bytes. Problem with download or content type.")

                # Save the stream content to a file for manual inspection
                with open(output_pdf_filename, "wb") as f_out:
                    f_out.write(pdf_bytes)
                print(f"[TestScript] Saved downloaded PDF content to: {output_pdf_filename}")
                print(f"[TestScript] Please open {output_pdf_filename} with a PDF viewer to check its integrity.")
            
            except Exception as e_stream:
                print(f"[TestScript] Error reading or saving stream: {e_stream}")
        else:
            print("[TestScript] Attachment object does not have a 'stream' attribute or it is None.")
            
        print("\n[TestScript] Full attachment dictionary for inspection:")
        # Be careful with printing __dict__ directly if it has very large items like full byte content
        # For now, let's try a.debug() which is designed for this
        print(a.debug())

    else:
        print("[TestScript] Attachments collection was initialized but contains no items.")

print("\n[TestScript] PDF download verification test finished.") 