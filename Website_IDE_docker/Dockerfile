# Start with the official Python 3.9 slim image
FROM python:3.9-slim

# Set environment variables to avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install any system dependencies required
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libssl-dev \
    libffi-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip install --no-cache-dir \
    requests \
    numpy \
    pandas  # Add any other packages you need

# Create a non-root user
RUN useradd -m nonrootuser

# Set the user to non-root user
USER nonrootuser

# Set the working directory
WORKDIR /home/nonrootuser

# Command to keep the container running
CMD ["python"]
