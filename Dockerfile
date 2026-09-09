FROM python:3.12-slim

WORKDIR /app

COPY scheduler.py .
COPY backup.py .
RUN pip install --no-cache-dir requests httpx

ENV PYTHONUNBUFFERED=1
ENV PORT=10000

EXPOSE 10000

CMD ["python", "scheduler.py"]
