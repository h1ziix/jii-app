# -*- coding: utf-8 -*-
"""Decode mojibake from TRANSLATION_BLOCKS in app.py and print clean text."""
import re
import unicodedata

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

ru_match = re.search(r'"ru":\s*"""(.*?)"""', content, re.DOTALL)
kk_match = re.search(r'"kk":\s*"""(.*?)"""', content, re.DOTALL)

MOJIBAKE_MARKERS = ("Ð", "Ñ", "Ã", "Â", "\u0402", "\u0403", "\u2019", "\u2018", "\u201c", "\u201d", "\u2022", "\u2013", "\u2014", "\u2122")

def score_text(text):
    marker_score = sum(text.count(m) for m in MOJIBAKE_MARKERS)
    latin1_noise = sum(1 for ch in text if 0x00C0 <= ord(ch) <= 0x00FF)
    control_noise = sum(1 for ch in text if unicodedata.category(ch).startswith("C") and ch not in "\n\r\t")
    return marker_score * 4 + latin1_noise * 2 + control_noise * 8

def repair_mojibake(value):
    best = value
    best_score = score_text(value)
    for enc in ("cp1251", "latin1", "cp1252"):
        try:
            candidate = value.encode(enc).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        s = score_text(candidate)
        if candidate and s < best_score:
            best = candidate
            best_score = s
    return best

def process_block(block_text):
    lines = []
    for raw_line in block_text.strip().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            lines.append(line)
            continue
        if "=" not in line:
            lines.append(line)
            continue
        key, value = line.split("=", 1)
        fixed = repair_mojibake(value.strip())
        lines.append(f"{key.strip()}={fixed}")
    return "\n".join(lines)

import sys
sys.stdout.reconfigure(encoding='utf-8')

if ru_match:
    print("=== RU BLOCK ===")
    print(process_block(ru_match.group(1)))
    print()

if kk_match:
    print("=== KK BLOCK ===")
    print(process_block(kk_match.group(1)))
