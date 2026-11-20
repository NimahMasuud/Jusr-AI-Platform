FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir "fastapi>=0.110" "pydantic>=2" "uvicorn>=0.29" "python-dotenv>=1.0"
COPY app ./app
COPY config ./config
ENV PORT=8100
EXPOSE 8100
CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
