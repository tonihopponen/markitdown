# MarkItDown Lambda Function

A secure, robust AWS Lambda function that converts various document formats to Markdown using Microsoft's markitdown tool.

## Features

- **Multi-format Support**: PDF, PPT/PPTX, DOC/DOCX, XLS/XLSX, CSV, JSON, XML
- **Security First**: Comprehensive input validation, path safety checks, non-root execution
- **Resource Management**: Automatic cleanup of temporary files, memory optimization
- **Error Handling**: Detailed error messages with proper HTTP status codes
- **Performance**: Configurable timeouts, efficient summarization algorithm
- **Monitoring**: Comprehensive logging for debugging and monitoring

## Security Improvements

### Input Validation
- File extension validation against whitelist
- Base64 encoding validation
- File size limits (50MB max)
- Path traversal attack prevention

### Runtime Security
- Non-root user execution
- Safe file path validation
- Process timeout protection
- Resource cleanup guarantees

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   API Gateway   │───▶│  Lambda Function │───▶│   markitdown    │
│                 │    │                  │    │   (converter)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────────┐
                       │   Summarizer     │
                       │   (if needed)    │
                       └──────────────────┘
```

## API Usage

### Request Format
```json
{
  "isBase64Encoded": true,
  "body": "<base64-encoded-file-content>",
  "headers": {
    "content-type": "application/pdf",
    "filename": "document.pdf"
  }
}
```

### Response Format
```json
{
  "statusCode": 200,
  "headers": {
    "content-type": "application/json",
    "cache-control": "no-cache"
  },
  "body": {
    "markdown": "# Document Title\n\nContent...",
    "word_count": 1500,
    "was_summarized": false
  }
}
```

### Error Response
```json
{
  "statusCode": 400,
  "headers": {
    "content-type": "application/json",
    "cache-control": "no-cache"
  },
  "body": {
    "error": "Unsupported file type: .txt. Supported: .pdf, .ppt, .pptx, .doc, .docx, .xls, .xlsx, .csv, .json, .xml"
  }
}
```

## Configuration

### Environment Variables
- `MAX_WORDS`: Maximum word count for output (default: 3000)
- `MAX_FILE_SIZE`: Maximum file size in bytes (default: 50MB)
- `PROCESS_TIMEOUT`: Timeout for markitdown process in seconds (default: 300)

### Supported File Types
- `.pdf` - PDF documents
- `.ppt`, `.pptx` - PowerPoint presentations
- `.doc`, `.docx` - Word documents
- `.xls`, `.xlsx` - Excel spreadsheets
- `.csv` - CSV files
- `.json` - JSON files
- `.xml` - XML files

## Deployment

### Docker Build
```bash
docker build -t markitdown-lambda .
```

### AWS Lambda Deployment
```bash
# Package the function
aws lambda create-function \
  --function-name markitdown-converter \
  --package-type Image \
  --code ImageUri=<your-ecr-repo>:latest \
  --role arn:aws:iam::<account>:role/lambda-execution-role
```

### API Gateway Integration
```bash
# Create HTTP API
aws apigatewayv2 create-api \
  --name markitdown-api \
  --protocol-type HTTP \
  --target arn:aws:lambda:<region>:<account>:function:markitdown-converter
```

## Testing

### Run Unit Tests
```bash
python -m pytest test_lambda.py -v
```

### Run with Coverage
```bash
python -m pytest test_lambda.py --cov=lambda_function --cov-report=html
```

### Manual Testing
```bash
# Test with a sample PDF
curl -X POST https://your-api-gateway-url/convert \
  -H "Content-Type: application/json" \
  -H "filename: test.pdf" \
  -d '{
    "isBase64Encoded": true,
    "body": "'$(base64 -w 0 test.pdf)'"
  }'
```

## Monitoring and Logging

### CloudWatch Logs
The function logs important events:
- Request processing start/end
- File validation results
- Conversion progress
- Error details
- Resource cleanup

### Metrics to Monitor
- Invocation count and duration
- Error rates by type
- File size distribution
- Summarization frequency
- Timeout occurrences

## Performance Considerations

### Cold Start Optimization
- Minimal dependencies
- Efficient summarization algorithm
- Optimized Docker image size

### Memory Usage
- Automatic cleanup of temporary files
- Streaming processing for large files
- Configurable word limits

### Timeout Handling
- Process-level timeouts
- Graceful error responses
- Retry logic recommendations

## Security Best Practices

### Input Sanitization
- All file paths validated for safety
- Base64 encoding verification
- File type whitelist enforcement
- Size limit enforcement

### Runtime Security
- Non-root user execution
- Minimal file system access
- Process isolation
- Resource limits

### Error Handling
- No sensitive information in error messages
- Proper HTTP status codes
- Structured error responses

## Troubleshooting

### Common Issues

1. **Timeout Errors**
   - Check file size and complexity
   - Verify markitdown installation
   - Review CloudWatch logs

2. **Memory Errors**
   - Reduce file size limits
   - Optimize summarization algorithm
   - Increase Lambda memory allocation

3. **Permission Errors**
   - Verify Lambda execution role
   - Check file system permissions
   - Ensure proper IAM policies

### Debug Mode
Enable detailed logging by setting the log level:
```python
logger.setLevel(logging.DEBUG)
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details. # Trigger deployment
