# Use official Python image
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create writable directories for reports/logs
RUN mkdir -p reports/output data/logs && chmod -R 777 reports/output data/logs

# Expose Hugging Face Spaces default port
EXPOSE 7860

# Command to run the application
CMD ["streamlit", "run", "app.py", "--server.port=7860", "--server.address=0.0.0.0", "--server.enableCORS=false", "--server.enableXsrfProtection=false"]
