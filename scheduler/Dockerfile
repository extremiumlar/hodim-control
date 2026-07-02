FROM python:3.11-slim

WORKDIR /app

COPY scheduler/requirements.txt /app/scheduler/requirements.txt
RUN pip install --no-cache-dir -r /app/scheduler/requirements.txt

COPY scheduler /app/scheduler

CMD ["python", "-m", "scheduler.main"]
