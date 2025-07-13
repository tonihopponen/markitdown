"""
Comprehensive test suite for the Lambda function.
Tests all improvements including security, validation, error handling, and functionality.
"""

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys
import os

# Add the current directory to Python path to import lambda_function
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lambda_function

class TestLambdaFunction(unittest.TestCase):
    """Test suite for the Lambda function improvements."""

    def setUp(self):
        """Set up test fixtures."""
        self.sample_text = "This is a sample document. It contains multiple sentences. Each sentence has different content."
        self.sample_markdown = "# Sample Document\n\nThis is a sample document. It contains multiple sentences. Each sentence has different content."

    def test_is_safe_path(self):
        """Test path safety validation."""
        # Valid paths
        self.assertTrue(lambda_function.is_safe_path(Path("/tmp/test.pdf")))
        self.assertTrue(lambda_function.is_safe_path(Path("/tmp/abc123.docx")))
        
        # Invalid paths
        self.assertFalse(lambda_function.is_safe_path(Path("/etc/passwd")))
        self.assertFalse(lambda_function.is_safe_path(Path("/tmp/../etc/passwd")))
        self.assertFalse(lambda_function.is_safe_path(Path("/tmp/../../etc/passwd")))
        self.assertFalse(lambda_function.is_safe_path(Path("/tmp/test/../file.pdf")))

    def test_validate_file_extension(self):
        """Test file extension validation."""
        # Valid extensions
        self.assertEqual(lambda_function.validate_file_extension("test.pdf"), (True, ""))
        self.assertEqual(lambda_function.validate_file_extension("document.docx"), (True, ""))
        self.assertEqual(lambda_function.validate_file_extension("data.xlsx"), (True, ""))
        
        # Invalid extensions
        is_valid, error = lambda_function.validate_file_extension("test.txt")
        self.assertFalse(is_valid)
        self.assertIn("Unsupported file type", error)
        
        is_valid, error = lambda_function.validate_file_extension("test")
        self.assertFalse(is_valid)
        self.assertIn("No file extension provided", error)

    def test_validate_file_size(self):
        """Test file size validation."""
        # Small file (valid)
        small_b64 = base64.b64encode(b"small content").decode()
        self.assertEqual(lambda_function.validate_file_size(small_b64), (True, ""))
        
        # Large file (invalid) - create a large base64 string
        large_content = b"x" * (lambda_function.MAX_FILE_SIZE + 1000)
        large_b64 = base64.b64encode(large_content).decode()
        is_valid, error = lambda_function.validate_file_size(large_b64)
        self.assertFalse(is_valid)
        self.assertIn("File too large", error)

    def test_validate_base64(self):
        """Test base64 validation."""
        # Valid base64
        valid_b64 = base64.b64encode(b"test content").decode()
        self.assertEqual(lambda_function.validate_base64(valid_b64), (True, ""))
        
        # Invalid base64
        is_valid, error = lambda_function.validate_base64("invalid base64!")
        self.assertFalse(is_valid)
        self.assertIn("Invalid base64 encoding", error)

    def test_validate_input(self):
        """Test comprehensive input validation."""
        valid_b64 = base64.b64encode(b"test content").decode()
        
        # Valid input
        self.assertEqual(lambda_function.validate_input(valid_b64, "test.pdf"), (True, ""))
        
        # Invalid file extension
        is_valid, error = lambda_function.validate_input(valid_b64, "test.txt")
        self.assertFalse(is_valid)
        self.assertIn("Unsupported file type", error)
        
        # Invalid base64
        is_valid, error = lambda_function.validate_input("invalid!", "test.pdf")
        self.assertFalse(is_valid)
        self.assertIn("Invalid base64 encoding", error)

    def test_summarise(self):
        """Test summarization functionality."""
        # Test with text that needs summarization
        long_text = "First sentence. " * 1000  # ~2000 words
        result = lambda_function.summarise(long_text, 100)
        
        # Should be shorter than original
        self.assertLess(len(result.split()), len(long_text.split()))
        
        # Should maintain sentence structure
        self.assertIn(".", result)
        
        # Test with short text (should return unchanged)
        short_text = "Short text."
        result = lambda_function.summarise(short_text, 100)
        self.assertEqual(result, short_text)

    @patch('lambda_function.subprocess.run')
    def test_markitdown_convert_success(self, mock_run):
        """Test successful markitdown conversion."""
        mock_run.return_value = MagicMock(returncode=0)
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)
            tmp_path.write_text("test content")
            
            # Mock the output file creation
            with patch('pathlib.Path.exists', return_value=True):
                with patch('pathlib.Path.read_text', return_value="# Test\n\nContent"):
                    result = lambda_function.markitdown_convert(tmp_path)
                    self.assertEqual(result, "# Test\n\nContent")
            
            tmp_path.unlink()

    @patch('lambda_function.subprocess.run')
    def test_markitdown_convert_timeout(self, mock_run):
        """Test markitdown conversion timeout."""
        mock_run.side_effect = lambda_function.subprocess.TimeoutExpired("cmd", 30)
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)
            tmp_path.write_text("test content")
            
            with self.assertRaises(lambda_function.subprocess.TimeoutExpired):
                lambda_function.markitdown_convert(tmp_path)
            
            tmp_path.unlink()

    def test_save_tmp_file(self):
        """Test temporary file saving with validation."""
        test_content = b"test file content"
        b64_content = base64.b64encode(test_content).decode()
        
        result_path = lambda_function.save_tmp_file(b64_content, "test.pdf")
        
        # Check file exists and has correct content
        self.assertTrue(result_path.exists())
        self.assertEqual(result_path.read_bytes(), test_content)
        
        # Check path is safe
        self.assertTrue(lambda_function.is_safe_path(result_path))
        
        # Cleanup
        result_path.unlink()

    def test_handler_success(self):
        """Test successful Lambda handler execution."""
        test_content = b"test content"
        b64_content = base64.b64encode(test_content).decode()
        
        event = {
            "body": b64_content,
            "isBase64Encoded": True,
            "headers": {"filename": "test.pdf"}
        }
        
        with patch('lambda_function.markitdown_convert', return_value="# Test\n\nContent"):
            with patch('lambda_function.save_tmp_file') as mock_save:
                mock_save.return_value = Path("/tmp/test.pdf")
                
                result = lambda_function.handler(event, {})
                
                self.assertEqual(result["statusCode"], 200)
                body = json.loads(result["body"])
                self.assertIn("markdown", body)
                self.assertEqual(body["markdown"], "# Test\n\nContent")

    def test_handler_missing_body(self):
        """Test handler with missing body."""
        event = {"headers": {"filename": "test.pdf"}}
        
        result = lambda_function.handler(event, {})
        
        self.assertEqual(result["statusCode"], 400)
        body = json.loads(result["body"])
        self.assertIn("No body provided", body["error"])

    def test_handler_invalid_extension(self):
        """Test handler with invalid file extension."""
        test_content = b"test content"
        b64_content = base64.b64encode(test_content).decode()
        
        event = {
            "body": b64_content,
            "isBase64Encoded": True,
            "headers": {"filename": "test.txt"}
        }
        
        result = lambda_function.handler(event, {})
        
        self.assertEqual(result["statusCode"], 400)
        body = json.loads(result["body"])
        self.assertIn("Unsupported file type", body["error"])

    def test_handler_invalid_base64(self):
        """Test handler with invalid base64."""
        event = {
            "body": "invalid base64!",
            "isBase64Encoded": True,
            "headers": {"filename": "test.pdf"}
        }
        
        result = lambda_function.handler(event, {})
        
        self.assertEqual(result["statusCode"], 400)
        body = json.loads(result["body"])
        self.assertIn("Invalid base64 encoding", body["error"])

    def test_cleanup_temp_files(self):
        """Test temporary file cleanup."""
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)
            tmp_path.write_text("test content")
            
            # Test cleanup
            lambda_function.cleanup_temp_files(tmp_path)
            
            # File should be deleted
            self.assertFalse(tmp_path.exists())

    def test_error_response_format(self):
        """Test error response format."""
        result = lambda_function._err(400, "Test error")
        
        self.assertEqual(result["statusCode"], 400)
        self.assertIn("content-type", result["headers"])
        self.assertIn("cache-control", result["headers"])
        
        body = json.loads(result["body"])
        self.assertIn("error", body)
        self.assertEqual(body["error"], "Test error")

if __name__ == '__main__':
    unittest.main() 