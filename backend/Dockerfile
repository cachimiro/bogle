FROM python:3.11-slim AS backend
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONUNBUFFERED=1
CMD ["gunicorn", "-b", "unix:/gunicorn.sock", "app:app"]

FROM nginx:1.25-alpine
COPY --from=backend /app /srv/app
COPY nginx.conf /etc/nginx/nginx.conf
