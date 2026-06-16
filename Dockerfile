FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY bot.py .

# Persistent data directory (mount as a volume in production)
RUN mkdir -p /app/logs

CMD ["python", "bot.py"]
