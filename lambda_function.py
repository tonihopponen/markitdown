"""
Lambda entry-point that:
  • accepts a single uploaded file (pdf, ppt/pptx, doc/docx, xls/xlsx, csv, json, xml)
  • converts it to Markdown with Microsoft markitdown
  • trims / summarises to ≤ 3 000 words
Return payload: JSON { "markdown": "<md string>" }
"""

import base64, json, os, re, subprocess, tempfile, uuid, logging
from pathlib import Path
from typing import Tuple, Optional

# --- configuration ---------------------------------------------------------

MAX_WORDS = 3_000                 # hard cap for output
MARKITDOWN_BIN = "/opt/markitdown"  # shipped in the Lambda layer / image
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB limit
SUPPORTED_EXTENSIONS = {'.pdf', '.ppt', '.pptx', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.json', '.xml'}
PROCESS_TIMEOUT = 300  # 5 minutes timeout for markitdown

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- input validation ------------------------------------------------------

def is_safe_path(path: Path) -> bool:
    """Validate that file path is safe and within /tmp directory."""
    path_str = str(path)
    return (path_str.startswith('/tmp/') and 
            '..' not in path_str and 
            not path_str.startswith('/tmp/../') and
            path.is_file())

def validate_file_extension(filename: str) -> Tuple[bool, str]:
    """Validate file extension is supported."""
    ext = os.path.splitext(filename.lower())[1]
    if not ext:
        return False, "No file extension provided"
    if ext not in SUPPORTED_EXTENSIONS:
        return False, f"Unsupported file type: {ext}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
    return True, ""

def validate_file_size(b64_body: str) -> Tuple[bool, str]:
    """Validate file size is within limits."""
    try:
        # Estimate size from base64 (roughly 4/3 ratio)
        estimated_size = len(b64_body) * 3 // 4
        if estimated_size > MAX_FILE_SIZE:
            return False, f"File too large. Max size: {MAX_FILE_SIZE // (1024*1024)}MB"
        return True, ""
    except Exception as e:
        return False, f"Error validating file size: {e}"

def validate_base64(b64_body: str) -> Tuple[bool, str]:
    """Validate base64 encoding."""
    try:
        # Test decode
        base64.b64decode(b64_body)
        return True, ""
    except Exception as e:
        return False, f"Invalid base64 encoding: {e}"

def validate_input(b64_body: str, filename: str) -> Tuple[bool, str]:
    """Comprehensive input validation."""
    # Check base64 encoding
    is_valid, error = validate_base64(b64_body)
    if not is_valid:
        return False, error
    
    # Check file extension
    is_valid, error = validate_file_extension(filename)
    if not is_valid:
        return False, error
    
    # Check file size
    is_valid, error = validate_file_size(b64_body)
    if not is_valid:
        return False, error
    
    return True, ""

# --- resource management --------------------------------------------------

def cleanup_temp_files(*files: Path):
    """Safely cleanup temporary files."""
    for file_path in files:
        try:
            if file_path.exists() and is_safe_path(file_path):
                file_path.unlink()
                logger.info(f"Cleaned up temporary file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup {file_path}: {e}")

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
    """Save base64 content to temporary file with proper validation."""
    try:
        raw = base64.b64decode(b64_body)
        ext = os.path.splitext(filename_hint)[1] or ".bin"
        tmpf = Path(f"/tmp/{uuid.uuid4().hex}{ext}")
        tmpf.write_bytes(raw)
        
        # Validate the created file
        if not is_safe_path(tmpf):
            raise ValueError("Generated file path is not safe")
            
        logger.info(f"Saved temporary file: {tmpf} ({len(raw)} bytes)")
        return tmpf
    except Exception as e:
        logger.error(f"Failed to save temporary file: {e}")
        raise

def markitdown_convert(inpath: Path) -> str:
    """Convert file to markdown using markitdown with timeout and validation."""
    if not is_safe_path(inpath):
        raise ValueError(f"Input file path is not safe: {inpath}")
    
    outpath = inpath.with_suffix(".md")
    cmd = [MARKITDOWN_BIN, str(inpath), "-o", str(outpath)]
    
    logger.info(f"Running markitdown: {' '.join(cmd)}")
    
    try:
        # Run with timeout
        result = subprocess.run(
            cmd, 
            check=True, 
            timeout=PROCESS_TIMEOUT,
            capture_output=True,
            text=True
        )
        
        if not outpath.exists():
            raise FileNotFoundError(f"markitdown did not create output file: {outpath}")
        
        content = outpath.read_text(encoding="utf-8", errors="ignore")
        logger.info(f"Successfully converted {inpath} to markdown ({len(content)} chars)")
        return content
        
    except subprocess.TimeoutExpired:
        logger.error(f"markitdown process timed out after {PROCESS_TIMEOUT} seconds")
        raise
    except subprocess.CalledProcessError as e:
        logger.error(f"markitdown failed with exit code {e.returncode}: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during markitdown conversion: {e}")
        raise

# --- Lambda handler ---------------------------------------------------------

def handler(event, context):
    """
    event expected from an HTTP API Gateway v2:
    {
        "isBase64Encoded": true,
        "body": "<base64 file>",
        "headers": { "content-type": "...", "filename": "report.pdf" }
    }
    """
    temp_files = []
    
    try:
        logger.info(f"Processing request with event keys: {list(event.keys())}")
        
        # Extract and validate input
        body = event.get("body", "")
        if not body:
            return _err(400, "No body provided")
        
        b64 = body if event.get("isBase64Encoded") else base64.b64encode(body.encode()).decode()
        fname = event.get("headers", {}).get("filename", "uploaded.bin")
        
        # Validate input
        is_valid, error = validate_input(b64, fname)
        if not is_valid:
            return _err(400, error)
        
        # Save file
        fpath = save_tmp_file(b64, fname)
        temp_files.append(fpath)
        
        # Convert to markdown
        md = markitdown_convert(fpath)
        words = len(md.split())
        
        logger.info(f"Converted document: {words} words")
        
        # Summarise if required
        if words > MAX_WORDS:
            original_words = words
            md = summarise(md, MAX_WORDS)
            words = len(md.split())
            logger.info(f"Summarized from {original_words} to {words} words")
        
        return {
            "statusCode": 200,
            "headers": { 
                "content-type": "application/json",
                "cache-control": "no-cache"
            },
            "body": json.dumps({
                "markdown": md,
                "word_count": words,
                "was_summarized": words < len(md.split())
            })
        }

    except subprocess.TimeoutExpired:
        return _err(408, f"Conversion timed out after {PROCESS_TIMEOUT} seconds")
    except subprocess.CalledProcessError as e:
        return _err(500, f"markitdown failed: {e}")
    except json.JSONDecodeError as e:
        return _err(400, f"Invalid JSON: {e}")
    except UnicodeDecodeError as e:
        return _err(400, f"Encoding error: {e}")
    except ValueError as e:
        return _err(400, f"Validation error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return _err(500, f"Internal error: {e}")
    finally:
        # Always cleanup temporary files
        cleanup_temp_files(*temp_files)

def _err(code: int, msg: str):
    """Return standardized error response."""
    logger.error(f"Error {code}: {msg}")
    return {
        "statusCode": code,
        "headers": { 
            "content-type": "application/json",
            "cache-control": "no-cache"
        },
        "body": json.dumps({"error": msg})
    }
