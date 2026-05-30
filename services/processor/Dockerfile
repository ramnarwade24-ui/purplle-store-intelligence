FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -U pip

COPY requirements/processor.txt /app/requirements/processor.txt
RUN pip install --no-cache-dir -r /app/requirements/processor.txt

COPY src /app/src

ENV PYTHONPATH=/app/src

CMD ["python", "-m", "storeintel.processor", "--help"]
