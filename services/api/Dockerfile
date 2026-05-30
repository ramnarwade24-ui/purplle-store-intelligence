FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN pip install --no-cache-dir -U pip
RUN mkdir -p /data

COPY requirements/api.txt /app/requirements/api.txt
RUN pip install --no-cache-dir -r /app/requirements/api.txt

COPY src /app/src

ENV PYTHONPATH=/app/src
EXPOSE 8000

CMD ["python", "-m", "storeintel.api"]
