FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project
COPY . .

# Install python deps
RUN pip install --no-cache-dir -r requirements.txt

# Fly uses PORT env
ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "bot.server:app", "--host", "0.0.0.0", "--port", "8080"]
