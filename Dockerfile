FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Create non-root user
RUN useradd -m archonos && \
    mkdir -p /home/archonos/.archonos && \
    chown -R archonos:archonos /home/archonos

# Switch to user
USER archonos
ENV HOME=/home/archonos

# Expose web UI port (future)
EXPOSE 8090

# Default: show version
CMD ["archonos", "--version"]