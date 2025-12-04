import re
import pandas as pd
import json

# ---------------------------------------------------
# Paste the SAME parsing logic used in your endpoint
# ---------------------------------------------------

def parse_cdr_status(sample_text):
    # Normalize section similar to your real handler
    section = sample_text.replace("\t", " ")
    section = re.sub(r"\r\n", "\n", section)
    section = re.sub(r"\n{2,}", "\n\n", section).strip()

    lines = [ln.rstrip() for ln in section.splitlines()]

    expected = [
        "Link State",
        "Date & Time",
        "Forward Seq. No",
        "Backward Seq. No",
        "CDR Buffer % Full",
        "Reason Code"
    ]

    def find_label_line_idx(label):
        pattern = re.compile(re.escape(label) + r"\s*:", re.IGNORECASE)
        for idx, ln in enumerate(lines):
            if pattern.search(ln):
                return idx
        return None

    rows = []
    for label in expected:
        idx = find_label_line_idx(label)
        primary = ""
        secondary = ""

        if idx is not None:
            line = lines[idx]
            after = re.sub(r"(?i)^.*?\:\s*", "", line).strip()

            if after:
                parts = re.split(r"\s{2,}", after)
                if len(parts) >= 2:
                    primary, secondary = parts[0].strip(), parts[1].strip()
                else:
                    primary = after
            else:
                j = idx + 1
                while j < len(lines) and lines[j].strip() == "":
                    j += 1
                if j < len(lines):
                    nextline = lines[j].strip()
                    parts = re.split(r"\s{2,}", nextline)
                    if len(parts) >= 2:
                        primary, secondary = parts[0].strip(), parts[1].strip()
                    else:
                        primary = nextline

        primary = re.sub(r"\b\d+\b\s*$", "", primary).strip()
        secondary = re.sub(r"\b\d+\b\s*$", "", secondary).strip()

        rows.append({
            "Parameter": label,
            "Primary": primary,
            "Secondary": secondary
        })

    df = pd.DataFrame(rows, columns=["Parameter", "Primary", "Secondary"])
    return df


# ---------------------------------------------------
# TEST INPUT (your sample EXACTLY)
# ---------------------------------------------------

sample_output = """
CDR LINK STATUS

               Primary                           Secondary
               -------                           ---------

Link State:    up                                up

Date & Time:   2025/11/16 05:59:26               2025/11/16 05:49:31

Forward Seq. No:     66                           66
Backward Seq. No:    0                            0

CDR Buffer % Full:   0.00                         0.00

Reason Code:   OK                                OK
"""

# ---------------------------------------------------
# RUN PARSER + SHOW RESULT
# ---------------------------------------------------

df = parse_cdr_status(sample_output)

print("\n=== PARSED TABLE ===")
print(df)

print("\n=== JSON FORMAT ===")
print(json.dumps(df.to_dict(orient="records"), indent=4))
