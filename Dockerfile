FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 BS_DATABASE=/data/business.sqlite3
WORKDIR /app
COPY server/requirements.txt /app/server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt && useradd --uid 10001 --create-home appuser && mkdir /data && chown appuser:appuser /data
COPY server /app/server
USER appuser
VOLUME ["/data"]
EXPOSE 9000
CMD ["uvicorn","server.app:app","--host","0.0.0.0","--port","9000","--workers","1","--limit-concurrency","100","--backlog","128","--timeout-keep-alive","5"]
