FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install browsers
RUN playwright install chromium

COPY . .

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV HEADLESS=True

CMD ["python", "bot_browser.py"]
