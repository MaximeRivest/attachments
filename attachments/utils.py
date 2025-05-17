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
                if angle not in [0, 90, 180, 270]:
                    print(f"Warning: Invalid rotation angle '{value}'. Only 0, 90, 180, 270 are currently directly supported for exact rotations without expansion.")
                    # Or we can map to transpose operations for 90, 270 to avoid black borders / expansion issues
                    # e.g., if angle == 90: operations[key] = Image.Transpose.ROTATE_90
                else:
                    operations[key] = angle
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
            # Supported output formats by pydub (common ones)
            # Users might need ffmpeg for some of these.
            supported_formats = ['wav', 'mp3', 'flac', 'ogg', 'opus', 'm4a', 'aac', 'webm', 'mp4'] 
            value_lower = value.lower()
            if value_lower in supported_formats:
                operations[key] = value_lower
            else:
                print(f"Warning: Unsupported audio format '{value}' for output. Supported: {supported_formats}.")
        elif key == 'samplerate' or key == 'rate':
            try:
                operations['samplerate'] = int(value) # pydub expects frame_rate as int
            except ValueError:
                print(f"Warning: Invalid samplerate value '{value}'. Expected an integer (e.g., 16000).")
        elif key == 'channels':
            try:
                channels_val = int(value)
                if channels_val in [1, 2]: # Mono or Stereo
                    operations[key] = channels_val
                else:
                    print(f"Warning: Invalid channels value '{value}'. Expected 1 (mono) or 2 (stereo).")
            except ValueError:
                print(f"Warning: Invalid channels value '{value}'. Expected an integer.")
        elif key == 'bitrate':
            # pydub expects bitrate like "128k", "192k" etc.
            if isinstance(value, str) and (value.endswith('k') or value.endswith('K')):
                try:
                    # Check if the numeric part is valid
                    int(value[:-1]) 
                    operations[key] = value
                except ValueError:
                    print(f"Warning: Invalid bitrate value '{value}'. Numeric part of bitrate is not an integer (e.g., 128k).")
            else:
                try:
                    # Allow raw numbers, assume kbps, will append 'k' later if pydub needs it stringified
                    # For now, let's just store what user gives if it looks like a number or valid string.
                    # Pydub's export function often takes bitrate as a string e.g. "192k"
                    int_val = int(value)
                    operations[key] = f"{int_val}k" # Store as string with k for pydub
                except ValueError:
                    print(f"Warning: Invalid bitrate value '{value}'. Expected a string like '128k' or an integer number of kbps.")
        else:
            print(f"Warning: Unknown audio operation key: '{key}'.")
            
    return operations

if __name__ == '__main__':
    # Test cases with N replacement integrated
    print("--- Test Cases ---")
    print(f"Total: 10, Input: '1,3-5,N' -> {parse_index_string('1,3-5,N', 10)}")
    # Expected: [0, 2, 3, 4, 9] (Correct: N becomes 10, so 10-1=9)
    
    print(f"Total: 10, Input: ':3' -> {parse_index_string(':3', 10)}")
    # Expected: [0, 1, 2] (Correct: items 1,2,3 -> indices 0,1,2; end=3 for range(0,3))

    print(f"Total: 10, Input: '8:' -> {parse_index_string('8:', 10)}")
    # Expected: [7, 8, 9] (Correct: start=7 for item 8, end=10 for range(7,10))

    print(f"Total: 10, Input: '-3:' -> {parse_index_string('-3:', 10)}")
    # Expected: [7, 8, 9] (Correct: start=10-3=7, end=10 for range(7,10))

    print(f"Total: 5, Input: '1-N' -> {parse_index_string('1-N', 5)}")
    # Expected: [0, 1, 2, 3, 4] (Correct: N=5, 1-5 -> 0-indexed 0 to 4)

    print(f"Total: 5, Input: 'N-N' -> {parse_index_string('N-N', 5)}")
    # Expected: [4] (Correct: N=5, 5-5 -> 0-indexed 4 to 4)
    
    print(f"Total: 10, Input: 'N-2-N' - This syntax is not supported well by simple split and N replace.")
    # It becomes '10-2-10'. If this is not a part, it errors.
    # If it's a single part '10-2-10', it fails range regex.
    # We should instruct users to use separate terms or simple ranges. E.g. "8-10" or "N-2,N-1,N"
    # Let's test 'N-2' as a single term: parse_index_string('N-2', 10)
    # 'N-2' becomes '10-2' which is '8'. int('8') -> 8. 1-idx 8 -> 0-idx 7.
    print(f"Total: 10, Input: 'N-2' (interpreted as single number '8' post N-subst) -> {parse_index_string('N-2', 10)}")
    # Expected: [7] (Correct: '10-2' is not a number. This will fail int(). This test is flawed)
    # Ah, 'N-2' is not an int. This test needs 'N' replaced, then '10-2' is passed to int() which fails.
    # This implies that calculations like N-2 are not supported, only literal N.
    # Correct, only N is replaced. "N-2" as a string will not be evaluated as math.
    # User should write "-2" for 2nd to last or "8" if N=10.
    # My test description was leading. The code is correct in not evaluating "N-2".

    print(f"Total: 10, Input: '1, N-1, N' (N=10 -> '1, 9, 10') -> {parse_index_string('1, 10-1, 10', 10)}") # '10-1' is not int
    # This also shows '10-1' is not '9'.
    # Test actual supported cases:
    print(f"Total: 10, Input: '1,9,N' -> {parse_index_string('1,9,N', 10)}")
    # Expected for '1,9,N' (N=10): [0, 8, 9]

    print(f"Total: 5, Input: '  ' -> {parse_index_string('  ', 5)}") # Expected: []
    print(f"Total: 5, Input: '1,bad,3' -> {parse_index_string('1,bad,3', 5)}") # Expected: [0, 2] with warning
    print(f"Total: 10, Input: '11' -> {parse_index_string('11', 10)}") # Expected: []
    print(f"Total: 10, Input: '-11' -> {parse_index_string('-11', 10)}") # Expected: []
    print(f"Total: 5, Input: '1-3, 2-4' -> {parse_index_string('1-3, 2-4', 5)}") # Expected: [0,1,2,3]
    print(f"Total: 5, Input: '1,1,1' -> {parse_index_string('1,1,1', 5)}") # Expected: [0]
    
    print(f"Total: 3, Input: '1-2,:1,3:' -> {parse_index_string('1-2,:1,3:', 3)}")
    # 1-2 -> [0,1]
    # :1  -> [0] (item 1, index 0; end=1 for range(0,1))
    # 3:  -> [2] (item 3, index 2; start=2, end=3 for range(2,3))
    # Expected: [0, 1, 2]

    print(f"Total: 5, Input: '' -> {parse_index_string('', 5)}") # Expected: []
    print(f"Total: 0, Input: '1,3-2,N' -> {parse_index_string('1,3-2,N', 0)}") # Expected: []
    
    print(f"Total: 10, Input: '0' -> {parse_index_string('0', 10)}") # Expected: [] (0 is ignored for single numbers)
    print(f"Total: 10, Input: ':0' -> {parse_index_string(':0', 10)}") # Expected: [] (slice up to 0, exclusive)
    print(f"Total: 10, Input: '0:' -> {parse_index_string('0:', 10)}") 
    # Expected: [0,1,2,3,4,5,6,7,8,9] (slice from 0 to end) - start_val=0 -> start=0
    
    print(f"Total: 3, Input: 'N+1:' (N=3 -> '4:') -> {parse_index_string('N+1:', 3)}") # becomes '4:', start=3, end=3. range(3,3) is empty
    # Expected: []
    print(f"Total: 3, Input: ':N+1' (N=3 -> ':4') -> {parse_index_string(':N+1', 3)}") # becomes ':4', start=0, end=4 (clamped to 3). range(0,3)
    # Expected: [0,1,2]
    
    print(f"Total: 5, Input: '3:3' (slice) -> {parse_index_string('3:3', 5)}") # start_val=3, end_val=3. start=2, end=3. range(2,3) -> [2]
    # This is tricky. Python s[3:3] is empty. User "3:3" might mean page 3 to 3.
    # Current slice logic: start=2, end=3 (from end_val=3). range(2,3) gives [2].
    # This means "X:X" gives page X. If that's desired, it's okay.
    # Python slice s[i:i] is empty. User s[i:i+1] gets item i.
    # Our user index "3" gets page 3 (index 2).
    # Our user index ":3" gets pages 1,2,3 (indices 0,1,2). End is exclusive for user here.
    # Our user index "3:" gets pages 3,4,5 (indices 2,3,4). Start is inclusive for user.
    # If user writes "3:3", for slice interpretation, if start is 1-idx 3 (0-idx 2)
    # and end is 1-idx 3 (meaning up to item 3, so range goes up to 3).
    # start_str=3 -> start=2. end_str=3 -> end=3. range(2,3) => [2]. This is item 3.
    # Seems consistent. "3:3" yields item 3.

    print(f"Total: 5, Input: '2:4' -> {parse_index_string('2:4', 5)}")
    # start_val=2 -> start=1. end_val=4 -> end=4. range(1,4) -> [1,2,3] (pages 2,3,4)

    print(f"Total: 5, Input: 'blah,1-N,foo' -> {parse_index_string('blah,1-N,foo', 5)}")
    # Expected: [0,1,2,3,4] with warnings

    # Test cases
    print(f"Input: '1,3-5,N', Total: 10 -> {parse_index_string('1,3-5,N', 10)}")
    # Expected: [0, 2, 3, 4, 9]
    print(f"Input: ':3,7:,N-1', Total: 10 -> {parse_index_string(':3,7:,N-1', 10)}") # N-1 is tricky, let's simplify to N. Range N-1 - N.
    # Expected: [0, 1, 2, 6, 7, 8, 9] (for :3, 7:, N) - Assuming N-1 meant 2nd to last as a single index is harder.
    # Let's test N-1 as a range "N-1 - N" or just "N-1" as an index.
    # The current code handles "N" not "N-1" as a single token.
    # "N-1" would be int(N-1) which fails.
    # The current logic for "X-Y" will handle "8-N" if N is replaced.
    # For "N-1" as a literal for "second to last", that is not directly supported.
    # Users would use -2.
    
    print(f"Input: '1', Total: 5 -> {parse_index_string('1', 5)}") # Expected: [0]
    print(f"Input: 'N', Total: 5 -> {parse_index_string('N', 5)}") # Expected: [4]
    print(f"Input: '-1', Total: 5 -> {parse_index_string('-1', 5)}") # Expected: [4]
    print(f"Input: '-2', Total: 5 -> {parse_index_string('-2', 5)}") # Expected: [3]
    print(f"Input: '2-4', Total: 5 -> {parse_index_string('2-4', 5)}") # Expected: [1, 2, 3]
    print(f"Input: '4-2', Total: 5 -> {parse_index_string('4-2', 5)}") # Expected: [1, 2, 3]
    print(f"Input: ':3', Total: 10 -> {parse_index_string(':3', 10)}") # Expected: [0, 1, 2] (pages 1,2,3)
    print(f"Input: '8:', Total: 10 -> {parse_index_string('8:', 10)}") # Expected: [7, 8, 9] (pages 8,9,10)
    print(f"Input: '-3:', Total: 10 -> {parse_index_string('-3:', 10)}") # Expected: [7, 8, 9] (last 3 pages)
    print(f"Input: '1,N,-1', Total: 5 -> {parse_index_string('1,N,-1', 5)}") # Expected: [0, 4]
    print(f"Input: '1-N', Total: 5 -> {parse_index_string('1-N', 5)}") # "N" in range needs total_items for substitution before int().
                                                                    # This requires pre-processing 'N' in ranges.
                                                                    # Current code fails on this.

    # How to handle "1-N"? The regex '([-]?\\d+)-([-]?\\d+)' expects digits.
    # We'd need to substitute N with total_items *before* regex matching for ranges.

    # Revised approach for N in ranges:
    # Pre-substitute N in the index_str
    index_str_n_resolved = '1-N, N-2 - N'.replace('N', str(10))
    print(f"Input: '1-10, 8-10', Total: 10 -> {parse_index_string(index_str_n_resolved, 10)}")
    # Expected for '1-N, N-2 - N' with N=10:
    # 1-10 -> [0,1,2,3,4,5,6,7,8,9]
    # 8-10 -> [7,8,9]
    # Union -> [0,1,2,3,4,5,6,7,8,9]
    
    print(f"Input: '1, 3-N', Total: 5. N -> 5 => '1, 3-5' -> {parse_index_string('1, 3-'.replace('N',str(5)) + str(5), 5)}")
    # Test N substitution more directly:
    def pre_process_n(idx_str, total):
        if total == 0: return idx_str # Avoid N -> 0 replacement issues if total_items is 0
        return idx_str.replace('N', str(total))

    print(f"Pre-processing '1-N, N-2 - N', N=10 -> '{pre_process_n('1-N, N-2 - N', 10)}'")
    # Then parse '1-10, 10-2 - 10' (note '10-2 - 10' is not a valid range, should be '8-10')
    # The user means (N-2) as start. So ' (N-2) - N '.
    # This implies we should parse math expressions or stick to simple N.
    # For now, only 'N' as a standalone number, or as part of X-N or N-X (if N is endpoint) will be supported by pre-replacement.
    # Let's update the main function.

    print(f"Input: '  ', Total: 5 -> {parse_index_string('  ', 5)}") # Expected: []
    print(f"Input: '1,bad,3', Total: 5 -> {parse_index_string('1,bad,3', 5)}") # Expected: [0, 2] with warning
    print(f"Input: '11', Total: 10 -> {parse_index_string('11', 10)}") # Expected: []
    print(f"Input: '-11', Total: 10 -> {parse_index_string('-11', 10)}") # Expected: []
    print(f"Input: '1-3, 2-4', Total: 5 -> {parse_index_string('1-3, 2-4', 5)}") # Expected: [0,1,2,3]
    print(f"Input: '1,1,1', Total: 5 -> {parse_index_string('1,1,1', 5)}") # Expected: [0]
    print(f"Input: '1-2,:1,3:', Total: 3 -> {parse_index_string('1-2,:1,3:', 3)}") # Expected: [0,1,2]
    # :1 means item 1 (0-idx 0)
    # 3: means item 3 to end (0-idx 2 to end)
    # 1-2 means item 1,2 (0-idx 0,1)

    print(f"Input: '', Total: 5 -> {parse_index_string('', 5)}") # Expected: []
    print(f"Input: '1,3-2,N', Total: 0 -> {parse_index_string('1,3-2,N', 0)}") # Expected: []


    # Test with N replacement in parse_index_string itself
    print("--- With N replacement integrated ---")
    print(f"Input: '1-N', Total: 5 -> {parse_index_string('1-N', 5)}") 
    # Expected: [0, 1, 2, 3, 4]
    print(f"Input: 'N-2 - N', Total: 10 (interpreted as (N-2) to N) -> {parse_index_string('N-2-N', 10)}") 
    # This 'N-2-N' will likely fail with current regex.
    # 'N-2' is not an int. 'N' is.
    # Needs careful tokenization or specific patterns for 'N-k'.
    # Let's simplify: 'N' is a direct substitute for total_items (1-indexed value).
    # So 'N-2' becomes 'total_items-2'. E.g., '10-2' -> '8'.
    # This math expression parsing is getting complex.
    # Simpler: only support N as a standalone number or endpoint in a simple range (e.g., "1-N", "N-N" - though "N-N" is just N).
    # Let's refine `parse_index_string` to pre-process 'N' more robustly. 