#!/usr/bin/env python3
"""Extract text from resume PDFs for conversion to LaTeX."""
import pymupdf
import os

pdf_dir = os.path.join(os.path.dirname(__file__), "Resumes")

for fname in sorted(os.listdir(pdf_dir)):
    if not fname.endswith(".pdf"):
        continue
    path = os.path.join(pdf_dir, fname)
    print(f"\n{'='*80}")
    print(f"FILE: {fname}")
    print(f"{'='*80}")
    doc = pymupdf.open(path)
    for page in doc:
        # Get detailed text blocks for structure
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    text = ""
                    for span in line["spans"]:
                        font = span["font"]
                        size = span["size"]
                        flags = span["flags"]
                        t = span["text"].strip()
                        if t:
                            text += f"[font={font}, size={size:.1f}, flags={flags}] {t} "
                    if text.strip():
                        print(text.strip())
            print()  # blank between blocks
    doc.close()
