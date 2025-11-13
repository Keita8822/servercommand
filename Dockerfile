# syntax=docker/dockerfile:1
FROM python:3.11-slim
 
ENV HTTP_PROXY=http://172.16.30.11:3128 \
    HTTPS_PROXY=http://172.16.30.11:3128 \
    NO_PROXY=localhost,127.0.0.1,::1
 
WORKDIR /app
 
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
 
COPY . .
 
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
