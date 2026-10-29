# syntax=docker/dockerfile:1
FROM python:3.11-alpine

LABEL maintainer="Plotline Community"
LABEL description="Plotline - Self-hosted, offline-first TV and movie tracker"

WORKDIR /app

# Install standard dependencies
RUN apk add --no-cache tzdata

# Create data directories for persistence
RUN mkdir -p /app/data/media/posters /app/data/media/backdrops /app/web

# Copy application files
COPY *.py /app/
COPY web/ /app/web/

# Environment variables
ENV PORT=8765
ENV PYTHONUNBUFFERED=1

# Expose server port
EXPOSE 8765

# Volume for persistent storage (database + cached media)
VOLUME ["/app/data"]

# Run Plotline
CMD ["python", "server.py"]
