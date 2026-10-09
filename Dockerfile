FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app
RUN addgroup --system meatshop && adduser --system --ingroup meatshop meatshop
COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt
COPY app ./app
USER meatshop
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
