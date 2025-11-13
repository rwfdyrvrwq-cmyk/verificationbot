import cv2
import numpy as np
import pytesseract
from PIL import Image
from io import BytesIO
import re
from difflib import SequenceMatcher
from typing import Optional

def preprocess_image_for_ocr(image_bytes: BytesIO) -> np.ndarray:
    """
    Preprocess screenshot for better OCR accuracy on white text with black outlines
    
    Args:
        image_bytes: BytesIO object containing PNG screenshot
        
    Returns:
        Preprocessed image as numpy array optimized for OCR
    """
    # Convert BytesIO to PIL Image
    image_bytes.seek(0)
    pil_image = Image.open(image_bytes)
    
    # Convert to OpenCV format (BGR)
    image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    
    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Upscale 2x for better text recognition
    height, width = gray.shape
    gray = cv2.resize(gray, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
    
    # Denoise using Non-local Means Denoising
    denoised = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
    
    # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) for better contrast
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(denoised)
    
    # Apply Otsu's thresholding for better binarization
    _, thresh = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Apply slight morphological opening to remove small noise
    kernel = np.ones((2, 2), np.uint8)
    cleaned = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
    
    return cleaned

def extract_text_from_region(image: np.ndarray, x: int, y: int, width: int, height: int) -> str:
    """
    Extract text from a specific region of the image
    
    Args:
        image: Preprocessed image
        x, y: Top-left coordinates of region
        width, height: Dimensions of region
        
    Returns:
        Extracted text string
    """
    # Crop to region
    region = image[y:y+height, x:x+width]
    
    # Configure Tesseract for single line of text
    custom_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789\' '
    
    # Extract text
    text = pytesseract.image_to_string(region, config=custom_config)
    
    return text.strip()

def fix_common_ocr_errors(text: str) -> str:
    """Fix common OCR errors in item names"""
    # Step 1: Remove ALL leading special characters, including ligatures like ﬁ
    # Match: quotes, parens, special chars, ligatures, unicode symbols
    text = re.sub(r'^[\W\u0080-\uFFFF]*', '', text).strip()
    
    # Step 2: Remove common icon prefixes that survived step 1
    text = re.sub(r'^(QE|P|R|&|\\|\/|\))\s+', '', text)
    
    # Step 3: Common character substitutions for AQW item names
    # Order matters - do specific patterns before general ones
    replacements = {
        # Specific multi-word corrections first
        r'\bQE\s+Jester\b': 'Montresor Jester',
        r'\bEllvontresor\b': 'Montresor',
        r'\b%ontresor\b': 'Montresor',
        
        # Single word corrections
        r'\bKnite\b': 'Knife',
        r'\bnistor\b': 'Sinister',
        r'\bLocl\b': 'Looks',
        r'\bLocks\b': 'Looks',
        r'\bBaiisd\b': 'Balloons',
        r'\bBalloon\b(?!s)': 'Balloons',
        r'\beyt\b': 'Crystallis',
        r'LightBaiisd': 'Light Balloons',
        r'Luvul': 'Level',
        r'Yevel': 'Level',
        r"AI'[(\[]m": "Alter",
        r"A;l'ter": "Alter",
        r'Wingf\.s': "King's",
    }
    
    corrected = text
    for pattern, replacement in replacements.items():
        corrected = re.sub(pattern, replacement, corrected, flags=re.IGNORECASE)
    
    # Step 4: Remove duplicate consecutive words (e.g., "Montresor Montresor" → "Montresor")
    corrected = re.sub(r'\b(\w+)\s+\1\b', r'\1', corrected, flags=re.IGNORECASE)
    
    # Step 5: Clean up extra spaces
    corrected = ' '.join(corrected.split())
    
    # Step 6: Remove trailing punctuation artifacts
    # Remove: '(s, '(s., "(s, (s., (s, etc.
    corrected = re.sub(r"['\"\`]?\s*\(\s*s\.?$", '', corrected)
    
    # Remove trailing quotes/apostrophes UNLESS it's a possessive (word + 's)
    # This preserves "King's" but removes "Looks'" 
    corrected = re.sub(r"(?<![s])['\"\`]+$", '', corrected)  # Remove if NOT after 's'
    
    # Remove other trailing special chars (but preserve possessive 's)
    corrected = re.sub(r"\s*[^\w\s']+$", '', corrected)
    corrected = re.sub(r"'s'$", "'s", corrected)  # Fix cases like "King's'"
    
    return corrected.strip()

def extract_item_from_region(image: np.ndarray, y_start: int, y_end: int) -> str:
    """
    Extract item name from a specific vertical region
    
    Args:
        image: Preprocessed grayscale image
        y_start: Starting Y coordinate
        y_end: Ending Y coordinate
        
    Returns:
        Extracted and cleaned item name
    """
    # Crop to the region
    region = image[y_start:y_end, :]
    
    # Upscale 3x for better OCR
    height, width = region.shape
    upscaled = cv2.resize(region, (width * 3, height * 3), interpolation=cv2.INTER_CUBIC)
    
    # Apply additional sharpening
    kernel_sharp = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
    sharpened = cv2.filter2D(upscaled, -1, kernel_sharp)
    
    # Try multiple OCR configurations
    configs = [
        r'--oem 3 --psm 7',  # Single line
        r'--oem 3 --psm 8',  # Single word
        r'--oem 1 --psm 7',  # Legacy engine
    ]
    
    best_result = ''
    max_length = 0
    
    for config in configs:
        try:
            text = pytesseract.image_to_string(sharpened, config=config).strip()
            # Choose the longest reasonable result
            if len(text) > max_length and len(text) < 50:
                best_result = text
                max_length = len(text)
        except:
            continue
    
    # Clean up result
    cleaned = fix_common_ocr_errors(best_result)
    
    return cleaned

def build_inventory_map(inventory_items: list) -> dict:
    """
    Build a map of inventory items grouped by type
    
    Args:
        inventory_items: List of inventory item dicts from API
        
    Returns:
        Dict mapping item types to lists of item names
        Example: {'Weapon': ['Cultist Knife', ...], 'Armor': [...]}
    """
    inventory_map = {}
    
    for item in inventory_items:
        item_type = item.get('strType', '')
        item_name = item.get('strName', '')
        
        if item_type and item_name:
            if item_type not in inventory_map:
                inventory_map[item_type] = []
            inventory_map[item_type].append(item_name)
    
    return inventory_map

def fuzzy_match_item(ocr_text: str, inventory_list: list, threshold: float = 0.6) -> Optional[str]:
    """
    Find the best matching item from inventory using fuzzy string matching
    
    Args:
        ocr_text: Text extracted from OCR
        inventory_list: List of possible item names from inventory
        threshold: Minimum similarity ratio (0-1) to accept a match
        
    Returns:
        Best matching item name or None if no good match found
    """
    if not ocr_text or not inventory_list:
        return None
    
    best_match = None
    best_ratio = 0.0
    ocr_lower = ocr_text.lower()
    ocr_len = len(ocr_text)
    
    # Special handling for very short OCR results (1-2 characters)
    if ocr_len <= 2:
        for item_name in inventory_list:
            item_lower = item_name.lower()
            ratio = 0.0
            
            # Very high score if OCR matches start of item name
            if item_lower.startswith(ocr_lower):
                ratio = 0.9
            # High score if OCR matches any word start in item name
            elif any(word.startswith(ocr_lower) for word in item_lower.split()):
                ratio = 0.7
            # Medium score if OCR character is in item name
            elif ocr_lower in item_lower:
                ratio = 0.5
            # Base similarity for anything else
            else:
                ratio = SequenceMatcher(None, ocr_lower, item_lower).ratio()
            
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = item_name
        
        # Higher threshold for short OCR to avoid false positives (0.7 instead of 0.6)
        if best_ratio >= 0.7:
            print(f'  → Fuzzy match (short): "{ocr_text}" → "{best_match}" (similarity: {best_ratio:.2f})')
            return best_match
    else:
        # Normal fuzzy matching for longer OCR results
        for item_name in inventory_list:
            item_lower = item_name.lower()
            
            # Calculate similarity ratio
            ratio = SequenceMatcher(None, ocr_lower, item_lower).ratio()
            
            # Bonus for exact substring match
            if ocr_lower in item_lower or item_lower in ocr_lower:
                ratio += 0.15
            
            # Bonus for word match
            ocr_words = set(ocr_lower.split())
            item_words = set(item_lower.split())
            if ocr_words & item_words:  # If any words match
                ratio += 0.1
            
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = item_name
        
        # Only return if above threshold
        if best_ratio >= threshold:
            print(f'  → Fuzzy match: "{ocr_text}" → "{best_match}" (similarity: {best_ratio:.2f})')
            return best_match
    
    return None

def extract_cosmetics_items(cosmetics_screenshot: BytesIO, inventory_items: list = None) -> dict:
    """
    Extract cosmetics item names from screenshot using OCR with Y-coordinate band matching
    
    Args:
        cosmetics_screenshot: BytesIO object containing cosmetics view screenshot
        
    Returns:
        Dictionary mapping equipment slots to item names
        Example: {'Weapon': 'Cultist Knife', 'Armor': 'Montresor Jester'}
    """
    try:
        # Build inventory map for fuzzy matching if available
        inventory_map = {}
        if inventory_items:
            inventory_map = build_inventory_map(inventory_items)
            print(f'Loaded inventory: {sum(len(items) for items in inventory_map.values())} items across {len(inventory_map)} types')
            print(f'Inventory types available: {list(inventory_map.keys())}')
        
        # Read image
        cosmetics_screenshot.seek(0)
        pil_image = Image.open(cosmetics_screenshot)
        image = np.array(pil_image)
        
        height, width = image.shape[:2]
        
        # Crop to left panel where item names are displayed (left 250px)
        left_panel = image[:, :250]
        
        # Convert to grayscale
        gray = cv2.cvtColor(left_panel, cv2.COLOR_RGB2GRAY)
        
        # Try multiple preprocessing methods and combine results
        preprocessed_images = []
        
        # Method 1: Simple upscale + invert + Otsu threshold (original working method)
        gray_2x = cv2.resize(gray, (gray.shape[1] * 2, gray.shape[0] * 2), interpolation=cv2.INTER_CUBIC)
        inv1 = cv2.bitwise_not(gray_2x)
        _, binary1 = cv2.threshold(inv1, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        denoised1 = cv2.fastNlMeansDenoising(binary1, None, 10, 7, 21)
        preprocessed_images.append(('simple_2x', denoised1, 2))
        
        # Method 2: CLAHE + 3x upscale + Otsu
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        gray_3x = cv2.resize(enhanced, (enhanced.shape[1] * 3, enhanced.shape[0] * 3), interpolation=cv2.INTER_CUBIC)
        inv2 = cv2.bitwise_not(gray_3x)
        _, binary2 = cv2.threshold(inv2, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        preprocessed_images.append(('clahe_3x', binary2, 3))
        
        # Method 3: Sharp filter + 2x upscale
        kernel_sharpen = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
        sharpened = cv2.filter2D(gray, -1, kernel_sharpen)
        sharp_2x = cv2.resize(sharpened, (sharpened.shape[1] * 2, sharpened.shape[0] * 2), interpolation=cv2.INTER_CUBIC)
        inv3 = cv2.bitwise_not(sharp_2x)
        _, binary3 = cv2.threshold(inv3, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        preprocessed_images.append(('sharp_2x', binary3, 2))
        
        # Run OCR on all methods and collect results by Y-coordinate
        all_results = []
        
        for method_name, processed_img, scale_factor in preprocessed_images:
            cv2.imwrite(f'/tmp/debug_{method_name}.png', processed_img)
            
            custom_config = r'--oem 3 --psm 6'
            data = pytesseract.image_to_data(processed_img, config=custom_config, output_type=pytesseract.Output.DICT)
            
            for i in range(len(data['text'])):
                text = data['text'][i].strip()
                conf = int(data['conf'][i])
                
                if text and conf > 30:
                    y = data['top'][i] // scale_factor
                    all_results.append((y, text, conf, method_name))
        
        # Group all results by Y position across all methods
        combined_lines_by_y = {}
        for y, text, conf, method in all_results:
            found_line = False
            for line_y in list(combined_lines_by_y.keys()):
                if abs(line_y - y) < 12:
                    combined_lines_by_y[line_y].append((text, conf, method))
                    found_line = True
                    break
            
            if not found_line:
                combined_lines_by_y[y] = [(text, conf, method)]
        
        # For each Y position, pick best text from all methods
        lines_by_y = {}
        for y_pos in combined_lines_by_y:
            texts = combined_lines_by_y[y_pos]
            # Pick the text with highest confidence
            best_text, best_conf, best_method = max(texts, key=lambda x: x[1])
            lines_by_y[y_pos] = [(best_text, best_conf)]
        
        # Sort lines by Y position and combine words on same line with avg confidence
        sorted_lines = []
        for y_pos in sorted(lines_by_y.keys()):
            words_with_conf = lines_by_y[y_pos]
            words = [text for text, _ in words_with_conf]
            avg_conf = sum(conf for _, conf in words_with_conf) / len(words_with_conf)
            combined_text = ' '.join(words)
            sorted_lines.append((y_pos, combined_text, avg_conf))
        
        print('DEBUG: Detected text lines:')
        for y, text, conf in sorted_lines:
            print(f'  Y={y} (conf={conf:.0f}): {text}')
        
        # Define expected Y-coordinate bands for each item slot (based on typical UI layout)
        # Items appear between Y=160 and Y=290, with wider bands to capture multi-line items
        slot_bands = {
            'Weapon': (160, 190),
            'Armor': (190, 220),
            'Helm': (220, 255),  # Wider to capture "Sinister Clown Looks" across 2 lines
            'Cape': (255, 285),
            'Pet': (285, 315),
            'Misc': (315, 345),
        }
        
        cosmetics_items = {}
        
        # UI text patterns to skip (check on RAW text before correction)
        ui_skip_patterns = [
            r'Level\s*\d+',  # Level 100
            r'Guild',
            r'Faction',
            r'Class',
            r'Profile',
            r'Cosmetics',
            r'Good\s*Hero',
            r'Echo',  # King's Echo (class name)
            r'Alter',  # Guild name
            r"King['\s]",  # King's
        ]
        
        # For each slot, find and merge matching lines in its Y-coordinate band
        for slot, (y_min, y_max) in slot_bands.items():
            # Collect all valid lines in this band
            candidate_lines = []
            
            for y, raw_text, conf in sorted_lines:
                # Check if Y is in this slot's band
                if not (y_min <= y < y_max):
                    continue
                
                # Skip UI text patterns on RAW text (before error correction)
                if any(re.search(pattern, raw_text, re.IGNORECASE) for pattern in ui_skip_patterns):
                    print(f'  [{slot}] Skipping UI text at Y={y}: {raw_text}')
                    continue
                
                # Skip if line confidence is too low (lower threshold to catch more text)
                if conf < 40:
                    print(f'  [{slot}] Skipping low confidence at Y={y} (conf={conf}): {raw_text}')
                    continue
                
                # Apply error correction
                cleaned = fix_common_ocr_errors(raw_text)
                print(f'  [{slot}] Y={y} cleaned: "{raw_text}" → "{cleaned}"')
                
                # Skip garbage: low confidence + very short text
                if conf < 60 and len(cleaned) <= 2:
                    print(f'  [{slot}] Skipping low conf + short text at Y={y} (conf={conf}, len={len(cleaned)}): "{cleaned}"')
                    continue
                
                # Adjust minimum thresholds based on whether we have inventory for fuzzy matching
                # With inventory, we can accept shorter OCR results and fuzzy match them
                min_length = 1 if inventory_map else 3
                min_alpha = 1 if inventory_map else 3
                
                # Skip "None" or too short
                if not cleaned or cleaned.lower() in ['none', 'nonc', 'nc'] or len(cleaned) < min_length:
                    print(f'  [{slot}] Skipping too short: "{cleaned}"')
                    continue
                
                # Count alphabetic characters
                alpha_count = sum(c.isalpha() for c in cleaned)
                
                # Skip if too few alphabetic characters (likely garbage)
                if alpha_count < min_alpha:
                    print(f'  [{slot}] Skipping low alpha count ({alpha_count}): "{cleaned}"')
                    continue
                
                # Skip if mostly special characters
                special_ratio = len(re.sub(r'[a-zA-Z0-9\s]', '', cleaned)) / max(len(cleaned), 1)
                if special_ratio > 0.3:
                    print(f'  [{slot}] Skipping high special char ratio ({special_ratio:.2f}): "{cleaned}"')
                    continue
                
                # Skip single characters (except "I" for items starting with I) only if no inventory
                # With inventory, allow single characters for fuzzy matching
                if not inventory_map and len(cleaned) == 1 and cleaned.upper() not in ['I']:
                    print(f'  [{slot}] Skipping single character: "{cleaned}"')
                    continue
                
                # Skip common garbage patterns
                if re.match(r'^[^\w\s]+$', cleaned):  # Only special chars
                    print(f'  [{slot}] Skipping special chars only: "{cleaned}"')
                    continue
                
                candidate_lines.append((y, cleaned, conf))
                print(f'  [{slot}] Added candidate: Y={y}, "{cleaned}", conf={conf}')
            
            # If we have candidates, merge consecutive lines that are close together
            if candidate_lines:
                print(f'  [{slot}] Processing {len(candidate_lines)} candidate(s) for merging')
                
                # Sort by Y position
                candidate_lines.sort(key=lambda x: x[0])
                
                # Try to merge lines that are within 25px of each other (increased from 20)
                merged_items = []
                i = 0
                while i < len(candidate_lines):
                    y1, text1, conf1 = candidate_lines[i]
                    merged_text = text1
                    merged_conf = conf1
                    merge_count = 1
                    j = i + 1
                    
                    print(f'  [{slot}] Starting merge from Y={y1}: "{text1}"')
                    
                    # Look ahead for lines within 25px
                    while j < len(candidate_lines):
                        y2, text2, conf2 = candidate_lines[j]
                        distance = y2 - y1
                        print(f'  [{slot}] Checking Y={y2} (distance={distance}px): "{text2}"')
                        
                        if distance < 25:  # Close together, likely same item
                            print(f'  [{slot}] → Merging: "{merged_text}" + "{text2}"')
                            merged_text += ' ' + text2
                            merged_conf = (merged_conf + conf2) / 2
                            merge_count += 1
                            j += 1
                        else:
                            print(f'  [{slot}] → Too far apart ({distance}px), stopping merge')
                            break
                    
                    print(f'  [{slot}] Final merged ({merge_count} line(s)): "{merged_text}" (conf={merged_conf:.0f})')
                    merged_items.append((merged_text, merged_conf))
                    i = j if j > i + 1 else i + 1
                
                # Pick the best merged item (highest confidence)
                if merged_items:
                    best_item = max(merged_items, key=lambda x: x[1])
                    ocr_result = best_item[0]
                    
                    # Try fuzzy matching with inventory
                    final_result = ocr_result
                    if inventory_map:
                        # Map UI slot names to inventory types
                        # Weapon slot can contain Sword, Dagger, Mace, Staff, etc.
                        inventory_types_to_check = []
                        if slot == 'Weapon':
                            inventory_types_to_check = ['Sword', 'Dagger', 'Mace', 'Staff', 'Axe', 'Polearm', 'Bow', 'Gun']
                        else:
                            inventory_types_to_check = [slot]
                        
                        # Try fuzzy matching across all relevant inventory types
                        all_items = []
                        for inv_type in inventory_types_to_check:
                            if inv_type in inventory_map:
                                all_items.extend(inventory_map[inv_type])
                        
                        if all_items:
                            fuzzy_match = fuzzy_match_item(ocr_result, all_items)
                            if fuzzy_match:
                                final_result = fuzzy_match
                            else:
                                print(f'  ⚠ No fuzzy match found for "{ocr_result}" in {slot} inventory')
                        else:
                            print(f'  ⚠ No inventory items found for slot {slot} (checked: {inventory_types_to_check})')
                    
                    cosmetics_items[slot] = final_result
                    print(f'  {slot}: {final_result} (conf={best_item[1]:.0f})')
        
        print(f'Extracted cosmetics items: {cosmetics_items}')
        return cosmetics_items
        
    except Exception as e:
        print(f'Error extracting cosmetics items via OCR: {e}')
        import traceback
        traceback.print_exc()
        return {}
