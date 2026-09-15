"""OpenCV character contour grouping and left-to-right line ordering."""

from __future__ import annotations

from typing import List, Tuple

import cv2
import numpy as np

Box = Tuple[int, int, int, int]


def merge_overlapping_boxes(boxes, overlap_threshold=0.45, max_gap=10):
    """Merge disconnected pieces of one glyph without joining neighbours."""
    if not boxes:
        return []

    boxes = sorted(boxes, key=lambda box: box[0])
    merged = []
    while boxes:
        x1, y1, width1, height1 = boxes.pop(0)
        has_merged = False
        for index, (x2, y2, width2, height2) in enumerate(boxes):
            overlap_x = min(x1 + width1, x2 + width2) - max(x1, x2)
            overlap_y = max(
                0,
                min(y1 + height1, y2 + height2) - max(y1, y2),
            )
            vertical_gap = max(
                0,
                max(y1, y2) - min(y1 + height1, y2 + height2),
            )
            minimum_width = min(width1, width2)
            vertically_related = (
                overlap_y > 0
                or vertical_gap <= max(3, int(max(height1, height2) * 0.20))
            )
            should_merge = (
                overlap_x > 0
                and minimum_width > 0
                and vertically_related
                and overlap_x / minimum_width >= overlap_threshold
            )
            if should_merge:
                new_x = min(x1, x2)
                new_y = min(y1, y2)
                new_width = max(x1 + width1, x2 + width2) - new_x
                new_height = max(y1 + height1, y2 + height2) - new_y
                boxes[index] = (new_x, new_y, new_width, new_height)
                has_merged = True
                break

        if not has_merged:
            merged.append((x1, y1, width1, height1))
        else:
            boxes = sorted(boxes, key=lambda box: box[0])
    return merged


def split_wide_box(
    binary_crop,
    x_offset,
    y_offset,
    width,
    height,
    max_char_aspect=1.75,
):
    """Recursively split a connected wide contour at projection valleys."""
    if width <= 0 or height <= 0:
        return []
    if width < height * max_char_aspect:
        return [(x_offset, y_offset, width, height)]

    projection = np.sum(binary_crop > 0, axis=0)
    if len(projection) >= 3:
        smoothed = np.convolve(projection, np.ones(3) / 3, mode="same")
    else:
        smoothed = projection
    maximum = np.max(smoothed)
    if maximum == 0:
        return [(x_offset, y_offset, width, height)]

    threshold = max(2, min(5, maximum * 0.2))
    candidates = np.where(smoothed <= threshold)[0]
    if len(candidates) == 0:
        candidates = np.where(smoothed <= maximum * 0.3)[0]
    if len(candidates) == 0:
        return [(x_offset, y_offset, width, height)]

    groups = []
    current = []
    for column in candidates:
        if not current or column == current[-1] + 1:
            current.append(column)
        else:
            groups.append(current)
            current = [column]
    if current:
        groups.append(current)
    split_points = [
        int(np.mean(group))
        for group in groups
        if 6 < int(np.mean(group)) < width - 6
    ]
    if not split_points:
        return [(x_offset, y_offset, width, height)]

    split_boxes = []
    previous = 0
    for point in split_points:
        split_boxes.append((x_offset + previous, y_offset, point - previous, height))
        previous = point
    split_boxes.append((x_offset + previous, y_offset, width - previous, height))

    final_boxes = []
    for x, y, split_width, split_height in split_boxes:
        crop = binary_crop[:, x - x_offset:x - x_offset + split_width]
        final_boxes.extend(
            split_wide_box(
                crop,
                x,
                y,
                split_width,
                split_height,
                max_char_aspect,
            )
        )
    return final_boxes


def remove_box_borders(binary_region: np.ndarray) -> Tuple[np.ndarray, bool]:
    """Remove an outer rectangular frame when a legacy caller supplies one."""
    height, width = binary_region.shape[:2]
    cleaned = binary_region.copy()
    has_border = False
    contours, _ = cv2.findContours(
        cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    for contour in contours:
        x, y, contour_width, contour_height = cv2.boundingRect(contour)
        if contour_width > 0.82 * width and contour_height > 0.82 * height:
            has_border = True
            thickness = max(8, min(20, int(max(contour_width, contour_height) * 0.05)))
            cv2.rectangle(
                cleaned,
                (x, y),
                (x + contour_width, y + contour_height),
                0,
                thickness,
            )
            margin = thickness // 2
            cleaned[:margin, :] = 0
            cleaned[-margin:, :] = 0
            cleaned[:, :margin] = 0
            cleaned[:, -margin:] = 0
    return cleaned, has_border


def segment_characters(binary_region: np.ndarray) -> List[List[Box]]:
    """Return character boxes grouped into ordered physical text lines."""
    contours, _ = cv2.findContours(
        binary_region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    raw_boxes = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if width < 2 or height < 2 or cv2.contourArea(contour) < 2:
            continue
        raw_boxes.append((x, y, width, height))
    if not raw_boxes:
        return []

    raw_heights = [height for _, _, _, height in raw_boxes]
    body_height_floor = max(5.0, float(np.percentile(raw_heights, 60)))
    substantial = [height for height in raw_heights if height >= body_height_floor]
    reference_height = np.median(substantial) if substantial else 6.0
    body_minimum = max(5, int(reference_height * 0.35))
    body_boxes = [box for box in raw_boxes if box[3] >= body_minimum] or raw_boxes

    body_lines: List[List[Box]] = []
    line_centers: List[float] = []
    for box in sorted(body_boxes, key=lambda item: item[1] + item[3] / 2):
        center_y = box[1] + box[3] / 2
        tolerance = max(5.0, reference_height * 0.85)
        candidates = [
            index
            for index, line_center in enumerate(line_centers)
            if abs(center_y - line_center) <= tolerance
        ]
        if candidates:
            line_index = min(
                candidates, key=lambda index: abs(center_y - line_centers[index])
            )
            body_lines[line_index].append(box)
            line_centers[line_index] = np.median(
                [item[1] + item[3] / 2 for item in body_lines[line_index]]
            )
        else:
            body_lines.append([box])
            line_centers.append(center_y)

    small_boxes = [box for box in raw_boxes if box not in body_boxes]
    for small_x, small_y, small_width, small_height in small_boxes:
        small_center_x = small_x + small_width / 2
        candidates = []
        for line_index, line in enumerate(body_lines):
            for body_x, body_y, body_width, body_height in line:
                overlaps = body_x - 2 <= small_center_x <= body_x + body_width + 2
                vertical_gap = max(
                    0,
                    max(small_y, body_y)
                    - min(small_y + small_height, body_y + body_height),
                )
                if overlaps and vertical_gap <= reference_height * 0.8:
                    candidates.append((vertical_gap, line_index))
        if candidates:
            _, line_index = min(candidates, key=lambda item: item[0])
            body_lines[line_index].append(
                (small_x, small_y, small_width, small_height)
            )

    lines: List[List[Box]] = []
    for line in body_lines:
        merged = merge_overlapping_boxes(line, overlap_threshold=0.45, max_gap=10)
        final_boxes = []
        for x, y, width, height in merged:
            crop = binary_region[y:y + height, x:x + width]
            final_boxes.extend(
                split_wide_box(
                    crop,
                    x,
                    y,
                    width,
                    height,
                    max_char_aspect=2.20,
                )
            )
        if final_boxes:
            lines.append(sorted(final_boxes, key=lambda box: box[0]))
    return sorted(
        lines,
        key=lambda line: np.median([box[1] + box[3] / 2 for box in line]),
    )


def segment_words(binary_line: np.ndarray) -> List[Box]:
    """Group handwriting components into left-to-right word boxes.

    TrOCR's IAM handwriting checkpoints work best on word-sized crops. A full
    notebook line can be ten or more times wider than it is tall and becomes
    unreadably compressed when the vision processor resizes it to a square.
    """
    if binary_line is None or binary_line.size == 0:
        return []
    if binary_line.ndim == 3:
        binary_line = cv2.cvtColor(binary_line, cv2.COLOR_BGR2GRAY)

    height, width = binary_line.shape[:2]
    contours, _ = cv2.findContours(
        binary_line, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    components: List[Box] = []
    for contour in contours:
        x, y, component_width, component_height = cv2.boundingRect(contour)
        if cv2.contourArea(contour) < 2 or component_width < 2:
            continue
        if component_height < max(2, int(height * 0.08)):
            continue
        is_rule_residue = (
            component_width > width * 0.40
            and component_height <= max(3, int(height * 0.12))
        )
        if not is_rule_residue:
            components.append((x, y, component_width, component_height))
    if not components:
        return []

    components = merge_overlapping_boxes(components, overlap_threshold=0.30)
    components.sort(key=lambda box: box[0])
    body_heights = [box[3] for box in components]
    reference_height = float(np.median(body_heights)) if body_heights else height
    # Inter-character gaps in connected or semi-connected handwriting are
    # normally below half a character body. Notebook word spaces are wider.
    word_gap = max(7, int(reference_height * 0.55), int(height * 0.38))

    # A ruled-paper line can touch several letters and turn an entire sentence
    # into one external contour. Use columns with real character-body density
    # instead: a residual rule contributes only one or two pixels per column.
    column_counts = np.count_nonzero(binary_line, axis=0)
    dense_columns = np.flatnonzero(
        column_counts >= max(3, int(height * 0.10))
    )
    column_runs: List[Tuple[int, int]] = []
    for column in dense_columns:
        column = int(column)
        if not column_runs or column > column_runs[-1][1] + 1:
            column_runs.append((column, column))
        else:
            column_runs[-1] = (column_runs[-1][0], column)

    grouped_runs: List[List[Tuple[int, int]]] = []
    for run in column_runs:
        if not grouped_runs or run[0] - grouped_runs[-1][-1][1] - 1 > word_gap:
            grouped_runs.append([run])
        else:
            grouped_runs[-1].append(run)

    # Fall back to contour grouping only for exceptionally faint words whose
    # vertical/curved strokes never meet the body-density threshold.
    if grouped_runs:
        horizontal_groups = [
            (group[0][0], group[-1][1] + 1)
            for group in grouped_runs
        ]
    else:
        horizontal_groups = []
        current_start = components[0][0]
        current_end = components[0][0] + components[0][2]
        for x, _, component_width, _ in components[1:]:
            if x - current_end > word_gap:
                horizontal_groups.append((current_start, current_end))
                current_start = x
            current_end = max(current_end, x + component_width)
        horizontal_groups.append((current_start, current_end))

    padding_x = max(3, int(height * 0.12))
    padding_y = max(2, int(height * 0.10))
    words: List[Box] = []
    for group_start, group_end in horizontal_groups:
        minimum_core_width = max(4, int(height * 0.22))
        if group_end - group_start < minimum_core_width:
            # Spiral binding, isolated page dirt, and detached rule fragments
            # commonly appear as tiny far-right "words".
            continue
        search_x0 = max(0, group_start - padding_x)
        search_x1 = min(width, group_end + padding_x)
        word_mask = binary_line[:, search_x0:search_x1]
        coordinates = cv2.findNonZero(word_mask)
        if coordinates is None:
            continue
        local_x, local_y, word_width, word_height = cv2.boundingRect(coordinates)
        x0 = max(0, search_x0 + local_x - padding_x)
        y0 = max(0, local_y - padding_y)
        x1 = min(width, search_x0 + local_x + word_width + padding_x)
        y1 = min(height, local_y + word_height + padding_y)
        minimum_word_width = max(5, int(height * 0.25))
        if x1 - x0 >= minimum_word_width and y1 - y0 >= 5:
            words.append((x0, y0, x1 - x0, y1 - y0))
    return words
