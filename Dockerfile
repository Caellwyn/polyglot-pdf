# Use official Python runtime
FROM python:3.12-slim

# Set working directory in container
WORKDIR /app

# Copy requirements first (for Docker caching)
COPY backend/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire backend folder
COPY backend/ ./backend/

# Set Python path so imports work
ENV PYTHONPATH=/app

# Cloud Run sets PORT env var, default to 8080
ENV PORT=8080

# Expose port for documentation (Cloud Run ignores this)
EXPOSE 8080

# Start the FastAPI server
# Cloud Run will inject PORT env var
CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}