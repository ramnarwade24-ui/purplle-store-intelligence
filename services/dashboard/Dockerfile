FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN pip install --no-cache-dir -U pip

COPY requirements/dashboard.txt /app/requirements/dashboard.txt
RUN pip install --no-cache-dir -r /app/requirements/dashboard.txt

COPY apps /app/apps

EXPOSE 8501
CMD ["streamlit", "run", "apps/dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
