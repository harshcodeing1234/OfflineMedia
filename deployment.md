# OfflineMedia - VM Production Deployment Guide

This guide details the steps to deploy **OfflineMedia** on a Cloud Virtual Machine (AWS EC2 or Azure VM) running **Ubuntu 22.04 LTS**. This deployment model includes a multithreaded **Gunicorn** app runner and an optimized **Nginx** reverse proxy to handle video file streaming efficiently for multiple concurrent users.

---

## 1. Prerequisites & Resource Requirements

* **OS**: Ubuntu 22.04 LTS (recommended).
* **Hardware**: At least a **t3.medium** (AWS) or **Standard_B2s** (Azure) instance (2 vCPUs, 4GB RAM) to support parallel Chrome browser instances for scraping.
* **Storage**: At least **10GB–20GB** of SSD storage is recommended for downloaded video caches.
* **Network Ports**: Open inbound ports `80` (HTTP), `443` (HTTPS), and `22` (SSH) in your cloud security groups.
* **Database**: A PostgreSQL connection string configured in `.env`.

---

## 2. Option A: Automated Deployment (1-Click Install)

We have created an automation script to handle updates, dependencies, Python environments, Gunicorn background services, and Nginx caching logic automatically.

1. Copy the [`setup_production.sh`](file:///C:/Users/shali/OneDrive/Desktop/OfflineMedia/landing%20page/setup_production.sh) file to your VM server.
2. Grant execution permissions and run the script:
   ```bash
   chmod +x setup_production.sh
   ./setup_production.sh
   ```
3. Enter your PostgreSQL connection string when prompted.
4. Access the web application using your virtual machine's public IP address.

---

## 3. Manual Installation Steps (Alternative to Script)

If you prefer to configure the server manually, execute the following commands in sequence on your Ubuntu virtual machine terminal:

### Step 1: Install System Dependencies & Headless Chrome
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git curl wget unzip nginx chromium-browser chromium-chromedriver
```

### Step 2: Set Up Web Directories & Permissions
```bash
# Clone repository
cd /var/www
sudo git clone <YOUR_REPO_URL> offline_media
sudo chown -R ubuntu:ubuntu offline_media
cd offline_media

# Configure Python Virtualenv & install requirements
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn

# Setup local cache folder
mkdir -p cache
chmod -R 775 cache
```

### Step 3: Configure Environment Variables
Create a `.env` configuration file in `/var/www/offline_media/`:
```ini
DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<dbname>?sslmode=require
SECRET_KEY=generate-a-strong-random-key-here
```

### Step 4: Configure Gunicorn Background Service (Systemd)
Create a system daemon configuration file:
```bash
sudo nano /etc/systemd/system/offlinemedia.service
```

Add the following config:
```ini
[Unit]
Description=Gunicorn instance to serve OfflineMedia app
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/var/www/offline_media
Environment="PATH=/var/www/offline_media/venv/bin"
ExecStart=/var/www/offline_media/venv/bin/gunicorn --workers 4 --bind 127.0.0.1:5001 app:app

[Install]
WantedBy=multi-user.target
```

Enable and start Gunicorn:
```bash
sudo systemctl daemon-reload
sudo systemctl start offlinemedia
sudo systemctl enable offlinemedia
```

### Step 5: Configure Nginx Reverse Proxy with Video Caching
Nginx streams video files directly from disk without hitting the Flask backend threadpool, which prevents buffering for active users.
```bash
sudo nano /etc/nginx/sites-available/offlinemedia
```

Add the configuration:
```nginx
server {
    listen 80;
    server_name _; # Replace with your domain name or public IP if available

    # High performance static video streaming direct from disk
    location /cache/ {
        alias /var/www/offline_media/cache/;
        try_files $uri =404;
        sendfile on;
        tcp_nopush on;
        keepalive_timeout 65;
    }

    # Proxy web pages and API requests to Flask application
    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable configuration and restart Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/offlinemedia /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```
