# Multi-stage build for optimized Lambda container
FROM public.ecr.aws/lambda/python:3.11 as base

# Install system dependencies
RUN yum update -y && \
    yum install -y \
        dotnet-sdk-8.0 \
        && yum clean all

# Install markitdown globally
RUN dotnet tool install -g markitdown

# Create non-root user for security
RUN groupadd -r lambda && useradd -r -g lambda lambda

# Set up environment
ENV PATH="$PATH:/root/.dotnet/tools"
RUN ln -s /root/.dotnet/tools/markitdown /opt/markitdown

# Create necessary directories and set permissions
RUN mkdir -p /tmp && \
    chown -R lambda:lambda /tmp && \
    chmod 755 /tmp

# Copy application code
COPY lambda_function.py ${LAMBDA_TASK_ROOT}

# Set proper ownership
RUN chown -R lambda:lambda ${LAMBDA_TASK_ROOT}

# Switch to non-root user
USER lambda

# Set working directory
WORKDIR ${LAMBDA_TASK_ROOT}

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import lambda_function; print('OK')" || exit 1

# Lambda handler
CMD ["lambda_function.handler"]
