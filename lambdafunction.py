"""
Lambda entry-point that:
  • accepts a single uploaded file (pdf, ppt/pptx, doc/docx, xls/xlsx, csv, json, xml)
  • converts it to Markdown with Microsoft markitdown
  • trims / summarises to ≤ 3 000 words
Return payload: JSON { "markdown": "<md string>" }
"""

import base64, json, os, re, subprocess, tempfile, uuid
from pathlib import Path
from typing import Tuple

# --- configuration ---------------------------------------------------------

MAX_WORDS = 3_000                 # hard cap for output
MARKITDOWN_BIN = "/opt/markitdown"  # shipped in the Lambda layer / image

# --- tiny TextRank-ish summariser ------------------------------------------

def summarise(text: str, target_words: int = MAX_WORDS) -> str:
    """
    Quick n-gram / frequency based extractive summariser.
    Keeps sentences with the highest keyword weight until ≤ target_words.
    No heavy ML – keeps Lambda cold-start tiny.
    """
    # tokenise sentences naïvely
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    if len(sentences) < 2:
        return text

    # keyword frequency
    words = re.findall(r'\b\w+\b', text.lower())
    stop = set(("the", "and", "of", "to", "in", "a", "is", "for", "on", "that", "with"))
    freq = {}
    for w in words:
        if w in stop or len(w) < 3:
            continue
        freq[w] = freq.get(w, 0) + 1

    # score each sentence
    sent_scores = []
    for s in sentences:
        score = sum(freq.get(w.lower(), 0) for w in re.findall(r'\b\w+\b', s))
        sent_scores.append((score, s))

    # pick sentences by descending score until ≤ N words
    summary, running = [], 0
    for _, s in sorted(sent_scores, reverse=True):
        wcount = len(s.split())
        if running + wcount > target_words:
            continue
        summary.append(s)
        running += wcount
        if running >= target_words:
            break

    # maintain original ordering
    ordered = sorted(summary, key=lambda s: sentences.index(s))
    return " ".join(ordered)


# --- helpers ----------------------------------------------------------------

def save_tmp_file(b64_body: str, filename_hint: str) -> Path:
    raw = base64.b64decode(b64_body)
    ext  = os.path.splitext(filename_hint)[1] or ".bin"
    tmpf = Path(f"/tmp/{uuid.uuid4().hex}{ext}")
    tmpf.write_bytes(raw)
    return tmpf

def markitdown_convert(inpath: Path) -> str:
    outpath = inpath.with_suffix(".md")
    cmd = [MARKITDOWN_BIN, str(inpath), "-o", str(outpath)]
    subprocess.run(cmd, check=True)
    return outpath.read_text(encoding="utf-8", errors="ignore")


# --- Lambda handler ---------------------------------------------------------

def handler(event, _context):
    """
    event expected from an HTTP API Gateway v2:
    {
        "isBase64Encoded": true,
        "body": "<base64 file>",
        "headers": { "content-type": "...", "filename": "report.pdf" }
    }
    """
    try:
        body   = event["body"]
        b64    = body if event.get("isBase64Encoded") else base64.b64encode(body.encode()).decode()
        fname  = event.get("headers", {}).get("filename", "uploaded.bin")
        fpath  = save_tmp_file(b64, fname)

        # 1. Convert → Markdown
        md = markitdown_convert(fpath)
        words = len(md.split())

        # 2. Summarise if required
        if words > MAX_WORDS:
            md = summarise(md, MAX_WORDS)

        return {
            "statusCode": 200,
            "headers": { "content-type": "application/json" },
            "body": json.dumps({"markdown": md})
        }

    except subprocess.CalledProcessError as e:
        return _err(500, f"markitdown failed: {e}")
    except Exception as e:
        return _err(500, f"Internal error: {e}")

def _err(code: int, msg: str):
    return {
        "statusCode": code,
        "headers": { "content-type": "application/json" },
        "body": json.dumps({"error": msg})
    }
