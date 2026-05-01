# Passport OCR Microservice

This Flask-based OCR microservice processes passport images using PassportEye and Tesseract OCR. It extracts MRZ data and returns the result as JSON.

## Run with Docker

```bash
docker build -t passport-ocr-service .
docker run -p 5000:5000 passport-ocr-service
```

## Environment Variables

1. Copy `.env.example` to `.env` and add your real API key:

   cp .env.example .env
   # Edit .env and set your OCR_API_KEY

2. When running the Docker container, use the .env file:

   docker run --env-file .env passport-ocr-service

This keeps your API keys and secrets out of the Dockerfile and image history.
