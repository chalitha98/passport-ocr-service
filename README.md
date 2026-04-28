# Passport OCR Microservice

This Flask-based OCR microservice processes passport images using PassportEye and Tesseract OCR. It extracts MRZ data and returns the result as JSON.

## Run with Docker

```bash
docker build -t passport-ocr-service .
docker run -p 5000:5000 passport-ocr-service
