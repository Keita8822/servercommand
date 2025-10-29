# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# 依存を先に入れるとビルドキャッシュが効きやすい
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリ本体
COPY . .

# FastAPI 起動
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

