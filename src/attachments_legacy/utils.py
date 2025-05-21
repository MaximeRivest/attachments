"""Utility functions for the attachments library."""

import re

def parse_index_string(index_str: str, total_items: int) -> list[int]:
    """
    Parses an index string (e.g., "1,3-5,N,:10,-2:") into a sorted list
    of unique 0-indexed integers.

    Args:
        index_str: The string to parse.
                   Examples: "1", "1,3", "3-5", "N", ":5" (first 5), 
                             "5:" (from 5th to end), "-1" (last), 
                             "-3:" (last 3 items).
                             "1-N" (from 1 to last item).
                             Python slice-like syntax like [start:stop:step] is not supported,
                             only comma-separated items.
        total_items: The total number of items available (e.g., pages, slides).

    Returns:
        A sorted list of unique 0-indexed integers.
        Returns an empty list if index_str is empty, None, or total_items is 0.
    """
    if not index_str or total_items == 0:
        return []

    # Replace 'N' with total_items (1-indexed value of the last item)
    # This must be done carefully if 'N' could be part of a word, but here it's a specific marker.
    # Using regex to replace 'N' as a whole word/token to avoid partial replacements if 'N' appears in file names or paths
    # if those were ever part of the index_str (they are not, currently).
    # Simpler string replace is fine given the context of "1,N,3-N".
    index_str_processed = index_str.replace('N', str(total_items))

    processed_indices = set()
    parts = index_str_processed.split(',')

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # No longer need special 'N' handling here as it's replaced by a number.
        # if part.upper() == 'N':
        #     if total_items > 0:
        #         processed_indices.add(total_items - 1)
        #     continue

        # Handle slices like ":X", "X:", "-X:" (numbers can now be from 'N' replacement)
        slice_match = re.match(r'^([-]?\d+)?:([-]?\d+)?$', part)
        if slice_match:
            start_str, end_str = slice_match.groups()

            start = 0 # Default for [:X]
            if start_str:
                start_val = int(start_str)
                if start_val > 0: # 1-indexed start
                    start = start_val - 1
                elif start_val < 0: # Negative index from end
                    start = total_items + start_val
                # if start_val == 0, can be ambiguous. Treat as 0 for Python-like slicing from start.
                # Or raise error for 0 in 1-based context. Let's stick to Python way for slices.
            
            end = total_items # Default for [X:]
            if end_str:
                end_val = int(end_str)
                if end_val > 0: # 1-indexed end (user means item 'end_val' included)
                                # For Python range, this means end_val
                    end = end_val 
                elif end_val < 0: # Negative index from end
                    end = total_items + end_val 
                # if end_val == 0, for a slice X:0, this means up to (but not including) 0.
                # If user means "0" as an index, it should be handled by single number.
                # Here, it implies an empty range if start is not also 0.

            # Clamp to bounds after initial calculation
            start = max(0, min(start, total_items))
            # For `end`, if user specifies `:5` (meaning items 1,2,3,4,5 -> indices 0,1,2,3,4),
            # then `end` should be 5. `range(start, end)` will go up to `end-1`.
            # So if `end_val` was positive, `end` is already `end_val`.
            # If `end_val` was negative, `end` is `total_items + end_val`.
            end = max(0, min(end, total_items)) 
            
            if start < end:
                processed_indices.update(range(start, end))
            elif start_str is None and end_str is not None and int(end_str) == 0: # Handle ":0" as empty
                pass # Results in empty set for this part
            elif end_str is None and start_str is not None and int(start_str) == total_items + 1 and total_items > 0: # Handle "N+1:" as empty
                 pass # e.g. if N=5, "6:" should be empty
            elif start == end and start_str is not None and end_str is not None : # e.g. "3:3" is empty in Python, user might mean page 3.
                                                                                 # This is complex. Let's assume Python slicing: empty.
                                                                                 # Single numbers are for single items.
                 pass


            continue

        # Handle ranges like "X-Y" (numbers can now be from 'N' replacement)
        range_match = re.match(r'^([-]?\d+)-([-]?\d+)$', part)
        if range_match:
            start_str, end_str = range_match.groups()
            start_val = int(start_str)
            end_val = int(end_str)

            # Convert 1-indexed or negative to 0-indexed
            start_idx = (start_val - 1) if start_val > 0 else (total_items + start_val if start_val < 0 else 0)
            # For end_val, it's inclusive in user's mind "3-5" means 3,4,5.
            end_idx = (end_val - 1) if end_val > 0 else (total_items + end_val if end_val < 0 else 0) 
            
            # Ensure start_idx <= end_idx
            if start_idx > end_idx:
                start_idx, end_idx = end_idx, start_idx 

            for i in range(start_idx, end_idx + 1): # end_idx should be inclusive
                if 0 <= i < total_items:
                    processed_indices.add(i)
            continue

        # Handle single numbers (1-indexed or negative, or from 'N' replacement)
        try:
            num = int(part)
            if num > 0: # 1-indexed
                if 1 <= num <= total_items:
                    processed_indices.add(num - 1)
            elif num < 0: # Negative index
                idx = total_items + num
                if 0 <= idx < total_items:
                    processed_indices.add(idx)
            # We ignore 0 if it's not part of a slice, as it's ambiguous for 1-based user input.
            # Alternatively, treat 0 as an error or map to first element.
            # Current: single '0' is ignored. ':0' is empty. '0:' is all.
        except ValueError:
            print(f"Warning: Could not parse index part \'{part}\' (original from \'{index_str}\'). Skipping this part.")
            # Optionally, raise an error or return all items on parsing failure
            # return list(range(total_items)) 

    return sorted(list(processed_indices))

def parse_image_operations(ops_str):
    """Parses image operation strings like 'resize:100x100,rotate:90,format:jpeg,quality:80'.
    Returns a dictionary of operations.
    Example: {
        'resize': (100, 100), 
        'rotate': 90, 
        'format': 'jpeg', 
        'quality': 80,
        'max_size': (1024,1024) # Example for a potential future op
    }
    """
    operations = {}
    if not ops_str or not isinstance(ops_str, str):
        return operations

    ops_list = ops_str.split(',')
    for op_item in ops_list:
        op_item = op_item.strip()
        if not op_item:
            continue
        
        parts = op_item.split(':', 1)
        if len(parts) != 2:
            print(f"Warning: Could not parse image operation part: '{op_item}'. Expected key:value format.")
            continue
        
        key = parts[0].strip().lower()
        value = parts[1].strip()

        if key == 'resize':
            try:
                w_str, h_str = value.lower().split('x')
                w = int(w_str) if w_str != 'auto' and w_str != '' and w_str != '?' else None
                h = int(h_str) if h_str != 'auto' and h_str != '' and h_str != '?' else None
                if w is None and h is None:
                    print(f"Warning: Invalid resize value '{value}'. Both width and height cannot be auto/empty.")
                    continue
                operations[key] = (w, h)
            except ValueError:
                print(f"Warning: Invalid resize value '{value}'. Expected WxH format (e.g., 100x100, 100xauto, autox100).")
        elif key == 'rotate':
            try:
                # Common rotations. Pillow's rotate expands image if not multiple of 90.
                # For simplicity, let's only allow specific degrees that don't require expand=True or cropping.
                # Or, use transpose for 90/270 if that's preferred for exact rotations.
                # Image.rotate(angle, expand=True) is better for arbitrary angles.
                # Let's allow 0, 90, 180, 270 for now.
                angle = int(value)
                # if angle not in [0, 90, 180, 270]:
                    # print(f"Warning: Invalid rotation angle '{value}'. Only 0, 90, 180, 270 are currently directly supported for exact rotations without expansion.")
                    # Or we can map to transpose operations for 90, 270 to avoid black borders / expansion issues
                    # e.g., if angle == 90: operations[key] = Image.Transpose.ROTATE_90
                # else:
                operations[key] = angle # Allow any integer angle, parser will handle it
            except ValueError:
                print(f"Warning: Invalid rotate value '{value}'. Expected an integer angle (e.g., 90).")
        elif key == 'format':
            value_lower = value.lower()
            if value_lower in ['jpeg', 'jpg', 'png', 'webp']:
                operations[key] = 'jpeg' if value_lower == 'jpg' else value_lower
            else:
                print(f"Warning: Unsupported image format '{value}' for output. Supported: jpeg, png, webp.")
        elif key == 'quality':
            try:
                quality_val = int(value)
                if 1 <= quality_val <= 100:
                    operations[key] = quality_val
                else:
                    print(f"Warning: Invalid quality value '{value}'. Expected integer between 1 and 100.")
            except ValueError:
                print(f"Warning: Invalid quality value '{value}'. Expected an integer.")
        # Example for a new operation, can be extended
        # elif key == 'max_size': 
        #     try:
        #         mw_str, mh_str = value.lower().split('x')
        #         mw = int(mw_str) if mw_str != '?' else None
        #         mh = int(mh_str) if mh_str != '?' else None
        #         if mw is None and mh is None: continue
        #         operations[key] = (mw, mh)
        #     except ValueError:
        #         print(f"Warning: Invalid max_size value '{value}'.")
        else:
            print(f"Warning: Unknown image operation key: '{key}'.")
            
    return operations

def parse_audio_operations(ops_str: str) -> dict:
    """Parses audio operation strings like 'format:wav,samplerate:16000,channels:1,bitrate:128k'.
    Returns a dictionary of operations.
    Example: {
        'format': 'wav',
        'samplerate': 16000,
        'channels': 1,
        'bitrate': '128k'
    }
    """
    operations = {}
    if not ops_str or not isinstance(ops_str, str):
        return operations

    ops_list = ops_str.split(',')
    for op_item in ops_list:
        op_item = op_item.strip()
        if not op_item:
            continue
        
        parts = op_item.split(':', 1)
        if len(parts) != 2:
            print(f"Warning: Could not parse audio operation part: '{op_item}'. Expected key:value format.")
            continue
        
        key = parts[0].strip().lower()
        value = parts[1].strip()

        if key == 'format':
            value_lower = value.lower()
            # Looser validation, let pydub handle if format is supported at export time
            # Common formats: wav, mp3, flac, ogg, opus, m4a, aac etc.
            if value_lower: # Basic check that value is not empty
                operations[key] = value_lower
            else:
                print(f"Warning: Audio format value for '{key}' is empty.")
        elif key == 'samplerate':
            try:
                sr = int(value)
                if sr > 0:
                    operations[key] = sr
                else:
                    print(f"Warning: Invalid audio samplerate '{value}'. Expected positive integer.")
            except ValueError:
                print(f"Warning: Invalid audio samplerate '{value}'. Expected an integer.")
        elif key == 'channels':
            try:
                ch = int(value)
                if ch > 0: # Typically 1 (mono) or 2 (stereo)
                    operations[key] = ch
                else:
                    print(f"Warning: Invalid audio channels value '{value}'. Expected positive integer.")
            except ValueError:
                print(f"Warning: Invalid audio channels value '{value}'. Expected an integer.")
        elif key == 'bitrate':
            # Bitrate is often a string like '128k', pydub handles this string format.
            if value: # Basic check
                operations[key] = value
            else:
                print(f"Warning: Audio bitrate value for '{key}' is empty.")
        else:
            print(f"Warning: Unknown audio operation key: '{key}'.")
            
    return operations

def pre_process_n(idx_str, total):
    """Helper to replace 'N' and handle its 1-based nature for range calculations.
    This is a simplified version assuming N appears in contexts like "1-N" or "N-5".
    DEPRECATED: parse_index_string handles 'N' more robustly.
    """
    if not isinstance(idx_str, str):
        return idx_str # Or raise error
    return idx_str.replace('N', str(total))

def convert_to_0_indexed(val_str, total_items):
    """Converts a string value (potentially 1-indexed or negative) to 0-indexed integer.
    DEPRECATED: Logic is now part of parse_index_string.
    """
    val = int(val_str)
    if val > 0: # 1-indexed
        return val - 1
    elif val < 0: # Negative index from end
        return total_items + val
    return 0 # Or raise error for 0, depending on convention


# Example Usage:
if __name__ == '__main__':
    print("--- Testing parse_index_string ---")
    total = 10
    print(f"Total items: {total}")
    tests = [
        ("1,3-5,N", [0, 2, 3, 4, 9]),
        ("", []), 
        (None, []),
        (":", list(range(total))), # All items
        (":3", [0, 1, 2]),       # First 3 (1,2,3)
        ("8:", [7, 8, 9]),       # From 8th to end (8,9,10)
        ("-2:", [8, 9]),      # Last 2 (9,10)
        (":-1", list(range(total-1))), # All except last one (1 to 9)
        ("1-N", list(range(total))),
        ("N-N", [9]),
        ("5", [4]),
        ("-1", [9]),
        ("1, 1, 2, 2-3", [0,1,2]), # Duplicates and overlaps
        ("11,0,-11", []),          # Out of bounds (for positive/negative)
        ("N+1", []),             # Invalid single item (N is 10, N+1 is 11)
        ("N, N-1, N-2", [7,8,9]),
        ("invalid,1", [0]),       # Invalid part ignored
        ("1, 3-2, 5", [0,1,2,4]),   # Range 3-2 becomes 2-3
        ("2-N, 1", list(range(total))),
        (":0", []),                 # Slice up to 0 (exclusive) is empty
        ("1:1", []),               # Slice 1:1 is empty
        ("1:2", [0]),              # Slice 1:2 gives item 1 (index 0)
        ("N:N", []),              # Slice N:N is empty
        ("N:N+1", [9]),            # Slice N:N+1 gives item N (index N-1)
        ("-1:-1", []),            # Empty slice
        ("-2:-1", [8]),            # Slice from second to last up to (not incl) last
    ]

    for test_str, expected in tests:
        result = parse_index_string(test_str, total)
        print(f"Input: '{test_str}' -> Result: {result}, Expected: {expected}, Match: {result == expected}")

    total_0 = 0
    print(f"\nTotal items: {total_0}")
    tests_0 = [
        ("1", []),
        ("N", []),
        (":", []),
    ]
    for test_str, expected in tests_0:
        result = parse_index_string(test_str, total_0)
        print(f"Input: '{test_str}' -> Result: {result}, Expected: {expected}, Match: {result == expected}")

    print("\n--- Testing parse_image_operations ---")
    ops_tests = [
        ("resize:100x200,rotate:90,format:png,quality:75", {'resize': (100,200), 'rotate': 90, 'format': 'png', 'quality': 75}),
        ("resize:autox300", {'resize': (None, 300)}),
        ("rotate:180, resize:?x?", {'rotate': 180, 'resize': (None,None)}), # ? implies auto
        ("format:JPEG", {'format': 'jpeg'}),
        ("quality:101, quality:0", {}), # Invalid qualities ignored
        ("resize:100, rotate", {}), # Malformed ignored
        ("unknownop:value", {}),
        ("rotate:45", {'rotate': 45}), # Arbitrary angle
        ("resize:100xauto,rotate:90,format:webp,quality:80", {'resize': (100,None), 'rotate': 90, 'format': 'webp', 'quality': 80})
    ]
    for ops_str, expected in ops_tests:
        result = parse_image_operations(ops_str)
        print(f"Input: '{ops_str}' -> Result: {result}, Expected: {expected}, Match: {result == expected}")

    print("\n--- Testing parse_audio_operations ---")
    audio_ops_tests = [
        ("format:wav,samplerate:16000,channels:1,bitrate:128k", 
         {'format': 'wav', 'samplerate': 16000, 'channels': 1, 'bitrate': '128k'}),
        ("samplerate:44100, format:mp3", {'samplerate': 44100, 'format': 'mp3'}),
        ("channels:2, bitrate:256k", {'channels': 2, 'bitrate': '256k'}),
        ("format:", {}), # Empty value ignored
        ("samplerate:-100", {}), # Invalid samplerate
        ("channels:0", {}), # Invalid channels
        ("unknown:value, format:opus", {'format':'opus'})
    ]

    for ops_str, expected in audio_ops_tests:
        result = parse_audio_operations(ops_str)
        print(f"Input: '{ops_str}' -> Result: {result}, Expected: {expected}, Match: {result == expected}") 