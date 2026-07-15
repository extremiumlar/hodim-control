FROM python:3.11-slim

WORKDIR /app

COPY api/requirements.txt /app/api/requirements.txt
RUN pip install --no-cache-dir -r /app/api/requirements.txt

COPY api /app/api
COPY db /app/db
# crm/ — CRM adapterlari (users/stats/daily_results va h.k. import qiladi)
COPY crm /app/crm
# scripts/ — bir martalik yordamchilar (masalan create_boss.py — birinchi rahbar)
COPY scripts /app/scripts

COPY api/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
