#!/usr/bin/env python3
"""
test_status_cdr_link_fixed.py

Improved standalone tester for the status cdr-link parser.
Embeds a sample CDR LINK STATUS block and runs a corrected parser that
keeps Primary and Secondary columns aligned correctly.
"""

import re
import pandas as pd
import os
import json
import time
from datetime import datetime

# ---------- SAMPLE TEXT (embedded) ----------
SAMPLE_TEXT = r"""
CDR LINK STATUS

               Primary                           Secondary
               -------                           ---------
Link State:    up                                up

Date & Time:   2025/11/16 05:59:26               2025/11/16 05:49:31

Forward Seq. No:     66                           66
Backward Seq. No:    0                            0

CDR Buffer % Full:   0.00                         0.00

Reason Code:   OK                                OK

Command successfully completed
"""

def parse_cdr_link_section(output):
    start = time.time()

    # Normalize spacing but keep long gaps that indicate column gap
    section = output or ""
    section = section.replace("\t", " ")
    section = re.sub(r"\r\n", "\n", section)
    # collapse repeated blank lines to single newline
    section = re.sub(r"\n{2,}", "\n\n", section).strip()

    # Remove footer/noise tokens (keep content safe)
    section = re.sub(r"(?i)press\s+CANCEL.*", "", section)
    section = re.sub(r"(?i)command\s+successfully.*", "", section)
    section = section.strip()

    expected = [
        "Link State",
        "Date & Time",
        "Forward Seq. No",
        "Backward Seq. No",
        "CDR Buffer % Full",
        "Reason Code"
    ]

    # Find positions of each label so we can extract the chunk reliably
    positions = {}
    for label in expected:
        m = re.search(re.escape(label) + r"\s*:", section, re.IGNORECASE)
        positions[label] = m.start() if m else -1

    present = [(lbl, pos) for lbl, pos in positions.items() if pos >= 0]
    if not present:
        raise ValueError("Could not detect expected labels in CDR LINK STATUS output")

    present.sort(key=lambda x: x[1])

    # Extract chunk for each label (text from label to next label)
    label_chunks = {}
    for i, (label, pos) in enumerate(present):
        start_pos = pos
        end_pos = present[i+1][1] if i+1 < len(present) else len(section)
        chunk = section[start_pos:end_pos].strip()
        # remove the label and colon
        chunk = re.sub(re.escape(label) + r"\s*:\s*", "", chunk, flags=re.IGNORECASE).strip()
        label_chunks[label] = chunk

    # Now for each chunk normalize internal whitespace and split by multiple spaces as column separator
    def split_primary_secondary(chunk_text):
        """
        Return (primary, secondary) from a chunk.
        Approach:
          - Replace newlines with single space
          - Replace runs of 2+ spaces with a separator token '|||'
          - Split on token: left -> primary, right -> secondary (strip)
        """
        if not chunk_text or chunk_text.strip() == "":
            return "", ""
        # collapse internal multiple newlines/spaces, but preserve "2+ spaces" boundary
        one_line = re.sub(r"\s*\n\s*", " ", chunk_text).strip()
        # replace repeated spaces (2 or more) with a token
        tokened = re.sub(r" {2,}", " ||| ", one_line)
        parts = [p.strip() for p in tokened.split("|||")]
        # parts may have surrounding separators; clean them
        parts = [p for p in parts if p is not None]
        # After split, primary should be first non-empty, secondary the next non-empty
        primary = parts[0].strip() if len(parts) >= 1 else ""
        secondary = parts[1].strip() if len(parts) >= 2 else ""
        return primary, secondary

    rows = []
    for label in expected:
        chunk = label_chunks.get(label, "")
        primary, secondary = split_primary_secondary(chunk)
        # Final cleanups
        primary = primary.strip()
        secondary = secondary.strip()
        rows.append({"Parameter": label, "Primary": primary, "Secondary": secondary})

    df = pd.DataFrame(rows, columns=["Parameter", "Primary", "Secondary"])
    duration = round(time.time() - start, 2)
    return df, duration

def main():
    try:
        df, dur = parse_cdr_link_section(SAMPLE_TEXT)
    except Exception as e:
        print("Parser error:", e)
        return

    # Print JSON to stdout for easy verification
    records = df.to_dict(orient="records")
    print(json.dumps({"data": records, "columns": df.columns.tolist()}, indent=2))

    # Save Excel
    os.makedirs("outputs", exist_ok=True)
    today_folder = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(os.path.join("outputs", today_folder), exist_ok=True)
    timestamp = datetime.now().strftime("%H-%M-%S")
    excel_path = os.path.join("outputs", today_folder, f"status_cdr_link_{timestamp}.xlsx")
    df.to_excel(excel_path, index=False)
    print(f"\nExcel written: {excel_path}\nParsed in {dur} seconds")

if __name__ == "__main__":
    main()
