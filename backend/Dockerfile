FROM python:3.11-slim

# Backend setup
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Install Nginx and Supervisord
RUN apt-get update && apt-get install -y nginx supervisor && rm -rf /var/lib/apt/lists/*

# Copy Nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Copy supervisor config
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Copy static frontend to expected location (if needed)
RUN mkdir -p /srv/app && cp /app/index.html /srv/app/ && cp /app/style.css /srv/app/ && cp /app/script.js /srv/app/ && cp /app/leads.html /srv/app/ && cp /app/confirmation.html /srv/app/ && cp /app/leads_script.js /srv/app/

EXPOSE 8080

CMD ["/usr/bin/supervisord"]
