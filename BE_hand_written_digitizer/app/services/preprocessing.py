import os

import cv2
import numpy as np
from typing import List, Dict, Tuple

def preprocess_image(image: np.ndarray) -> np.ndarray:
    """
    Preprocess the input image using OpenCV:
    1. Convert to grayscale.
    2. Apply Gaussian blur to reduce noise.
    3. Apply Otsu's thresholding to get a clean binary image.
    4. Clear a 10px border to remove edge noise.
    """
    # 1. Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # 2. Apply Gaussian blur
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # 3. Apply adaptive Gaussian thresholding to handle shadows and screen/noise patterns
    # Calculate a local block size that scales with image resolution (approx 3% of width)
    rows, cols = gray.shape
    block_size = int(cols // 30)
    if block_size % 2 == 0:
        block_size += 1
    block_size = max(11, block_size)
    
    binary = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, block_size, 10
    )
    
    # 4. Clear a 10px border around the binary image to eliminate boundary noise/artifacts
    border = 10
    binary[0:border, :] = 0
    binary[-border:, :] = 0
    binary[:, 0:border] = 0
    binary[:, -border:] = 0
    
    # 5. Remove only page-wide notebook ruling.  The former implementation used
    # very short kernels (roughly 4% of the page size), so it removed diagram
    # boxes, arrows and even parts of letters before OCR saw the image.
    rows, cols = binary.shape
    horizontal_size = max(80, int(cols * 0.60))
    vertical_size = max(120, int(rows * 0.55))
    horizontal_structure = cv2.getStructuringElement(cv2.MORPH_RECT, (horizontal_size, 1))
    vertical_structure = cv2.getStructuringElement(cv2.MORPH_RECT, (1, vertical_size))

    # A word written over a rule creates small gaps in that rule.  Close only
    # those short gaps before selecting page-wide lines; this must happen before
    # the long opening so a notebook line is still removed beneath handwriting.
    horizontal_seed = cv2.morphologyEx(
        binary,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(9, int(cols * 0.025)), 1)),
    )
    vertical_seed = cv2.morphologyEx(
        binary,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(9, int(rows * 0.025)))),
    )
    ruled_horizontal = cv2.morphologyEx(horizontal_seed, cv2.MORPH_OPEN, horizontal_structure)
    ruled_vertical = cv2.morphologyEx(vertical_seed, cv2.MORPH_OPEN, vertical_structure)
    ruled_lines = cv2.bitwise_or(ruled_horizontal, ruled_vertical)
    ruled_lines = cv2.dilate(
        ruled_lines,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
        iterations=1,
    )

    binary_clean = cv2.bitwise_and(binary, cv2.bitwise_not(ruled_lines))

    # Adaptive thresholding keeps pale notebook rules as foreground under
    # uneven lighting. Keep only dark handwriting/diagram ink so horizontal
    # projection can split real text lines for the handwriting recognizer.
    dark_ink_threshold = int(os.getenv("OCR_DARK_INK_THRESHOLD", "150"))
    dark_ink = cv2.threshold(gray, dark_ink_threshold, 255, cv2.THRESH_BINARY_INV)[1]
    binary_clean = cv2.bitwise_and(binary_clean, dark_ink)

    # Morphological opening only finds perfectly horizontal rules. Phone
    # photos contain slightly slanted/curved notebook lines, so detect their
    # long edges in the original grayscale image and remove them from the OCR
    # mask. Short underlines and diagram strokes are intentionally preserved.
    edges = cv2.Canny(gray, 40, 120)
    detected_lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 720,
        threshold=70,
        minLineLength=max(80, int(cols * 0.55)),
        maxLineGap=max(20, int(cols * 0.09)),
    )
    if detected_lines is not None:
        rule_mask = np.zeros_like(binary_clean)
        thickness = max(3, int(rows * 0.005))
        for x1, y1, x2, y2 in detected_lines[:, 0]:
            angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
            length = np.hypot(x2 - x1, y2 - y1)
            is_horizontal_rule = angle < 5.0
            is_vertical_margin = angle > 85.0 and length >= rows * 0.45
            if is_horizontal_rule or is_vertical_margin:
                cv2.line(rule_mask, (x1, y1), (x2, y2), 255, thickness)
        # Never erase strong black/blue pen strokes merely because they cross
        # a detected notebook rule. The pale paper ruling is normally well
        # above this threshold, while handwriting remains protected.
        strong_ink_threshold = int(os.getenv("OCR_STRONG_INK_THRESHOLD", "115"))
        strong_ink = cv2.threshold(
            gray, strong_ink_threshold, 255, cv2.THRESH_BINARY_INV
        )[1]
        preserved_ink = cv2.bitwise_and(binary_clean, strong_ink)
        # A dark photographed page edge is also "strong ink" but must not be
        # restored after Hough removal. Protect handwriting only in the page
        # interior so borders cannot reconnect otherwise separate text rows.
        interior_mask = np.zeros_like(binary_clean)
        horizontal_margin = max(12, int(cols * 0.04))
        vertical_margin = max(10, int(rows * 0.02))
        interior_mask[
            vertical_margin:rows - vertical_margin,
            horizontal_margin:cols - horizontal_margin,
        ] = 255
        preserved_ink = cv2.bitwise_and(preserved_ink, interior_mask)
        binary_clean = cv2.bitwise_or(
            cv2.bitwise_and(binary_clean, cv2.bitwise_not(rule_mask)),
            preserved_ink,
        )

    return binary_clean


def _without_page_rule_residue(binary_image: np.ndarray) -> np.ndarray:
    """Discard the occasional page-spanning rule left below handwriting."""
    rows, cols = binary_image.shape
    cleaned = binary_image.copy()
    # These are page rules/margins, not a normal text or diagram stroke.  This
    # is intentionally conservative so a broad diagram edge is retained.
    row_counts = np.count_nonzero(cleaned, axis=1)
    col_counts = np.count_nonzero(cleaned, axis=0)
    cleaned[row_counts > cols * 0.65, :] = 0
    cleaned[:, col_counts > rows * 0.65] = 0
    return cleaned


def _count_nested_characters(binary_image: np.ndarray, box: Tuple[int, int, int, int]) -> int:
    """Count character-like contours inside a box area to detect text containers."""
    x, y, w, h = box
    crop = binary_image[y:y+h, x:x+w]
    contours, _ = cv2.findContours(crop, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    char_count = 0
    for contour in contours:
        cx, cy, cw, ch = cv2.boundingRect(contour)
        # Exclude the outer border outline itself
        if cw > 0.8 * w or ch > 0.8 * h:
            continue
        if 4 <= cw <= 50 and 6 <= ch <= 50:
            char_count += 1
    return char_count


def _diagram_boxes(binary_image: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """Return boxes containing structural strokes, not handwriting contours."""
    working = _without_page_rule_residue(binary_image)
    rows, cols = working.shape
    edge_margin = max(10, int(min(rows, cols) * 0.025))

    def touches_page_edge(x: int, y: int, width: int, height: int) -> bool:
        """Notebook borders/margins are stationery, never document diagrams."""
        return (
            x <= edge_margin
            or y <= edge_margin
            or x + width >= cols - edge_margin
            or y + height >= rows - edge_margin
        )
    # Morphological line extraction is intentionally used instead of a
    # permissive Hough transform. Hough classified ruled-paper residue and
    # individual entity-box edges as separate diagrams. Long horizontal and
    # vertical strokes provide a stable structural seed while ordinary words
    # remain outside the diagram mask.
    line_length = max(30, int(min(rows, cols) * 0.07))
    horizontal = cv2.morphologyEx(
        working,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (line_length, 1)),
    )
    vertical = cv2.morphologyEx(
        working,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, line_length)),
    )
    structure = cv2.bitwise_or(horizontal, vertical)

    # Remove only long, shallow fragments beside a photographed page edge.
    # Interior connector/arrow lines must remain so related entity boxes join
    # into one coherent ER/domain-model region.
    contours, _ = cv2.findContours(
        structure, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        edge_fragment = touches_page_edge(x, y, w, h) and (
            h <= 3 or w <= 3
        )
        if edge_fragment:
            cv2.drawContours(structure, [contour], -1, 0, thickness=-1)

    boxes: List[Tuple[int, int, int, int]] = []
    if np.any(structure):
        # Join nearby boxes and their connectors. The grouping kernel is large
        # enough to make one domain model one region, but validation below
        # still requires evidence in both orientations, rejecting underlines.
        grouped = cv2.dilate(
            structure,
            cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (max(35, int(cols * 0.20)), max(25, int(rows * 0.09))),
            ),
            iterations=1,
        )
        contours, _ = cv2.findContours(grouped, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        padding_x = max(10, int(min(rows, cols) * 0.18))
        padding_y = max(8, int(min(rows, cols) * 0.035))
        for contour in contours:
            group_mask = np.zeros_like(structure)
            cv2.drawContours(group_mask, [contour], -1, 255, thickness=-1)
            group_structure = cv2.bitwise_and(structure, group_mask)
            coordinates = cv2.findNonZero(group_structure)
            if coordinates is None:
                continue
            sx, sy, sw, sh = cv2.boundingRect(coordinates)
            horizontal_evidence = int(np.count_nonzero(horizontal[sy:sy + sh, sx:sx + sw]))
            vertical_evidence = int(np.count_nonzero(vertical[sy:sy + sh, sx:sx + sw]))
            if horizontal_evidence < line_length * 2 or vertical_evidence < line_length * 2:
                continue
            x = max(0, sx - padding_x)
            y = max(0, sy - padding_y)
            x1 = min(cols, sx + sw + padding_x)
            y1 = min(rows, sy + sh + padding_y)
            w, h = x1 - x, y1 - y
            if w > cols * 0.94 and h > rows * 0.94:
                continue
            if touches_page_edge(sx, sy, sw, sh):
                continue
            boxes.append((x, y, w, h))

    # Long straight strokes do not cover circles and triangles.  Detect only
    # large, closed geometric contours here so an ordinary handwritten O or A
    # is still treated as text.
    geometric_minimum = max(45, int(min(rows, cols) * 0.11))
    # Rule removal may leave one-pixel gaps where a notebook line crossed a
    # circle or triangle.  Reconnect only vertically for geometric-contour
    # detection; this does not join separate words on a text line.
    geometric_input = cv2.morphologyEx(
        working,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(7, int(min(rows, cols) * 0.025)))),
    )
    contours, _ = cv2.findContours(geometric_input, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if min(w, h) < geometric_minimum:
            continue
        if touches_page_edge(x, y, w, h):
            continue
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        area = cv2.contourArea(contour)
        circularity = 4 * np.pi * area / (perimeter * perimeter)
        vertices = len(cv2.approxPolyDP(contour, 0.04 * perimeter, True))
        polygon = 3 <= vertices <= 5 and area >= (w * h * 0.25)
        rounded_polygon = (
            5 <= vertices <= 10
            and 0.65 <= (w / h) <= 1.35
            and area >= (w * h * 0.45)
        )
        if circularity >= 0.45 or polygon or rounded_polygon:
            boxes.append((x, y, w, h))

    # A rectangle can be found both by its straight strokes and by its closed
    # contour.  Keep only one region for the same physical diagram.
    unique_boxes: List[Tuple[int, int, int, int]] = []
    for candidate in sorted(boxes, key=lambda box: box[2] * box[3], reverse=True):
        x, y, w, h = candidate
        duplicate = False
        for kept_x, kept_y, kept_w, kept_h in unique_boxes:
            overlap_w = max(0, min(x + w, kept_x + kept_w) - max(x, kept_x))
            overlap_h = max(0, min(y + h, kept_y + kept_h) - max(y, kept_y))
            overlap = overlap_w * overlap_h
            if overlap / min(w * h, kept_w * kept_h) >= 0.70:
                duplicate = True
                break
        if not duplicate:
            unique_boxes.append(candidate)
    return unique_boxes


def _text_line_boxes(binary_image: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """Extract text-line boxes using the horizontal ink projection."""
    working = _without_page_rule_residue(binary_image)
    rows, cols = working.shape
    row_ink = np.count_nonzero(working, axis=1)
    # Ignore isolated dots/noise, but keep short handwritten lines.
    minimum_ink = max(3, int(cols * 0.0025))
    active_rows = row_ink >= minimum_ink
    # TrOCR expects one text line per image. A larger gap here merges several
    # notebook lines into a paragraph and causes the decoder to hallucinate.
    max_gap = max(5, int(rows * 0.002))
    bands: List[Tuple[int, int]] = []
    start = None
    last = None
    for y, is_active in enumerate(active_rows):
        if not is_active:
            continue
        if start is None:
            start = last = y
        elif y - last <= max_gap:
            last = y
        else:
            bands.append((start, last))
            start = last = y
    if start is not None:
        bands.append((start, last))

    # Long margins/noise can keep several handwritten rows weakly connected.
    # Split unusually tall bands at local projection valleys so the sequence
    # recognizer always receives one physical line at a time.
    expected_line_height = max(24, min(55, int(rows * 0.035)))
    refined_bands: List[Tuple[int, int]] = []
    for start_y, end_y in bands:
        band_height = end_y - start_y + 1
        if band_height < expected_line_height * 1.25:
            refined_bands.append((start_y, end_y))
            continue
        line_count = max(2, int(round(band_height / expected_line_height)))

        cuts = []
        for line_index in range(1, line_count):
            target = start_y + int(band_height * line_index / line_count)
            radius = max(3, int(expected_line_height * 0.30))
            search_start = max(start_y + 3, target - radius)
            search_end = min(end_y - 3, target + radius)
            if search_end > search_start:
                cut = search_start + int(np.argmin(row_ink[search_start:search_end + 1]))
                cuts.append(cut)

        segment_start = start_y
        for cut in cuts:
            if cut - segment_start >= 5:
                refined_bands.append((segment_start, cut - 1))
                segment_start = cut + 1
        if end_y - segment_start >= 4:
            refined_bands.append((segment_start, end_y))
    bands = refined_bands

    boxes: List[Tuple[int, int, int, int]] = []
    # Crops shorter than roughly one percent of the page are residual rule
    # edges/dots, not a complete handwriting line. Keeping them gives a
    # sequence model permission to invent words from no visual evidence.
    minimum_height = max(7, int(rows * 0.007))
    minimum_width = max(14, int(cols * 0.02))
    padding = max(3, int(min(rows, cols) * 0.004))
    ignored_header_fraction = float(os.getenv("OCR_IGNORE_HEADER_FRACTION", "0.07"))
    for start_y, end_y in bands:
        if end_y - start_y + 1 < minimum_height:
            continue
        crop = working[start_y:end_y + 1, :]
        active_columns = np.flatnonzero(np.count_nonzero(crop, axis=0))
        if active_columns.size == 0:
            continue
        # A sequence recognizer needs the complete physical line. Splitting at
        # large spaces feeds partial words/glyph clusters to TrOCR and destroys
        # their reading order.
        x0 = max(0, int(active_columns[0]) - padding)
        x1 = min(cols, int(active_columns[-1]) + padding + 1)
        y0 = max(0, start_y - padding)
        y1 = min(rows, end_y + padding + 1)
        if y0 < rows * ignored_header_fraction:
            continue
        box_width = x1 - x0
        box_height = y1 - y0
        if box_width < minimum_width:
            continue
        is_residual_rule = (
            box_width >= cols * 0.60
            and box_height <= max(12, int(rows * 0.025))
            and box_width / max(1, box_height) >= 20
        )
        if not is_residual_rule:
            boxes.append((x0, y0, box_width, box_height))
    return boxes


def segment_document(original_image: np.ndarray, binary_image: np.ndarray) -> Tuple[List[Dict], np.ndarray]:
    """Split a page into text lines and structural diagram areas.

    Text is deliberately segmented into shallow line regions.  Passing a whole
    paragraph or a diagram through a single-character CNN creates merged
    contours and meaningless characters, which was the source of the random
    output shown in the application.
    """
    overlay = original_image.copy()
    rows, cols = binary_image.shape
    diagram_boxes = _diagram_boxes(binary_image)

    # Do not allow text inside/next to a diagram outline to be interpreted as
    # page prose.  A modest padding keeps box borders from becoming characters.
    diagram_mask = np.zeros_like(binary_image)
    exclusion_padding = max(5, int(min(rows, cols) * 0.012))
    for x, y, w, h in diagram_boxes:
        cv2.rectangle(
            diagram_mask,
            (max(0, x - exclusion_padding), max(0, y - exclusion_padding)),
            (min(cols - 1, x + w + exclusion_padding), min(rows - 1, y + h + exclusion_padding)),
            255,
            thickness=-1,
        )

    text_only = cv2.bitwise_and(binary_image, cv2.bitwise_not(diagram_mask))
    text_boxes = _text_line_boxes(text_only)

    regions: List[Dict] = []
    for x, y, w, h in text_boxes:
        regions.append({
            "type": "text",
            "box": (x, y, w, h),
            "cropped_image": original_image[y:y + h, x:x + w],
        })
    for x, y, w, h in diagram_boxes:
        regions.append({
            "type": "diagram",
            "box": (x, y, w, h),
            "cropped_image": original_image[y:y + h, x:x + w],
        })

    regions.sort(key=lambda region: (region["box"][1], region["box"][0]))
    for index, region in enumerate(regions, start=1):
        x, y, w, h = region["box"]
        color = (0, 255, 0) if region["type"] == "text" else (255, 0, 0)
        cv2.rectangle(overlay, (x, y), (x + w, y + h), color, 2)
        cv2.putText(
            overlay,
            f"{region['type'].capitalize()} #{index}",
            (x, max(y - 6, 18)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )
    return regions, overlay

def remove_background(image: np.ndarray, binary_image: np.ndarray) -> np.ndarray:
    """
    Remove background from the color BGR image:
    1. Create a solid white background of the same shape.
    2. Copy foreground color pixels from the original image where the binary mask is 255.
    """
    clean_image = np.ones_like(image) * 255
    mask = (binary_image == 255)
    clean_image[mask] = image[mask]
    return clean_image


def digitize_diagram(binary_crop: np.ndarray) -> np.ndarray:
    """Render one coherent cleaned diagram without discarding its labels.

    Reconstructing every contour as a rectangle/polygon removed all character
    contours and converted an ER model into a meaningless bundle of lines. The
    preprocessed mask already contains the useful box, arrow, and label ink, so
    preserve it faithfully on a clean white background.
    """
    if binary_crop is None or binary_crop.size == 0:
        return np.empty((0, 0, 3), dtype=np.uint8)
    ink = binary_crop.copy()
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
        (ink > 0).astype(np.uint8), connectivity=8
    )
    cleaned = np.zeros_like(ink)
    for component in range(1, component_count):
        if int(stats[component, cv2.CC_STAT_AREA]) >= 3:
            cleaned[labels == component] = 255
    return cv2.cvtColor(cv2.bitwise_not(cleaned), cv2.COLOR_GRAY2BGR)
