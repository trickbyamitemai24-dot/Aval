FROM python:3.11-slim

RUN useradd -m -u 1000 appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data logs && chown -R appuser:appuser /app

USER appuser

CMD python3 -u bot.py