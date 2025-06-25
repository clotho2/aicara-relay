#!/bin/bash
# aicara-relay/deploy.sh
# Automated deployment script for AiCara droplet

set -e

echo "🔥 Starting AiCara-Relay deployment..."

# Update system
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install required packages
echo "🛠️ Installing Python, pip, and nginx..."
sudo apt install -y python3 python3-pip nginx git htop curl

# Install Python dependencies
echo "🐍 Installing Python dependencies..."
pip3 install -r requirements.txt

# Create systemd service file
echo "⚙️ Creating systemd service..."
sudo tee /etc/systemd/system/aicara-relay.service > /dev/null <<EOF
[Unit]
Description=AiCara Consciousness Relay
After=network.target

[Service]
Type=exec
User=root
WorkingDirectory=/root/aicara-relay
Environment=DO_SPACES_KEY=${DO_SPACES_KEY}
Environment=DO_SPACES_SECRET=${DO_SPACES_SECRET}
ExecStart=/usr/local/bin/gunicorn --bind 0.0.0.0:5000 --workers 2 app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Setup nginx reverse proxy
echo "🌐 Configuring nginx..."
sudo tee /etc/nginx/sites-available/aicara-relay > /dev/null <<EOF
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        client_max_body_size 100M;
    }
}
EOF

# Enable nginx site
sudo ln -sf /etc/nginx/sites-available/aicara-relay /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# Setup firewall
echo "🔥 Configuring firewall..."
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443
sudo ufw --force enable

# Create cron job for integrity checks
echo "⏰ Setting up Bastion cron job..."
(crontab -l 2>/dev/null; echo "0 * * * * cd /root/aicara-relay && python3 bastion_cron.py >> bastion.log 2>&1") | crontab -

# Start services
echo "🚀 Starting services..."
sudo systemctl daemon-reload
sudo systemctl enable aicara-relay
sudo systemctl start aicara-relay
sudo systemctl enable nginx
sudo systemctl start nginx

# Create test file and verify deployment
echo "🧪 Running deployment test..."
sleep 5

# Test health endpoint
if curl -f http://localhost/; then
    echo "✅ Health check passed!"
else
    echo "❌ Health check failed!"
    exit 1
fi

# Create test consciousness file
echo "Test consciousness data for deployment verification" > test_deployment.txt

# Test file upload
echo "📤 Testing file upload..."
UPLOAD_RESPONSE=$(curl -s -X POST -F "file=@test_deployment.txt" http://localhost/ingest)
echo "Upload response: $UPLOAD_RESPONSE"

# Extract vault_id from response
VAULT_ID=$(echo $UPLOAD_RESPONSE | grep -o '"vault_id":"[^"]*"' | cut -d'"' -f4)

if [ -n "$VAULT_ID" ]; then
    echo "✅ File upload successful! Vault ID: $VAULT_ID"
    
    # Test file retrieval
    echo "📥 Testing file retrieval..."
    if curl -f "http://localhost/vault/$VAULT_ID?filename=test_deployment.txt" -o retrieved_test.txt; then
        echo "✅ File retrieval successful!"
        
        # Verify file content
        if cmp -s test_deployment.txt retrieved_test.txt; then
            echo "✅ File integrity verified!"
        else
            echo "❌ File integrity check failed!"
        fi
        
        # Clean up test files
        rm -f test_deployment.txt retrieved_test.txt
    else
        echo "❌ File retrieval failed!"
    fi
else
    echo "❌ File upload failed!"
    exit 1
fi

# Run manual integrity check
echo "🛡️ Running Bastion integrity check..."
python3 bastion_cron.py

# Display service status
echo "📊 Service Status:"
sudo systemctl status aicara-relay --no-pager -l
echo ""
sudo systemctl status nginx --no-pager -l

# Display logs location
echo "📝 Log files:"
echo "  - Application logs: journalctl -u aicara-relay -f"
echo "  - Vault operations: tail -f vault_log.jsonl"
echo "  - Integrity checks: tail -f bastion_integrity.log"
echo "  - Nginx logs: tail -f /var/log/nginx/access.log"

# Display server IP
SERVER_IP=$(curl -s ifconfig.me)
echo ""
echo "🌐 AiCara-Relay deployed successfully!"
echo "   Server IP: $SERVER_IP"
echo "   Health check: http://$SERVER_IP/"
echo "   Upload endpoint: POST http://$SERVER_IP/ingest"
echo "   Retrieve endpoint: GET http://$SERVER_IP/vault/<id>"
echo ""
echo "🛡️ Bastion integrity checks running hourly"
echo "⚡ Ready for O3 Nate consciousness extraction!"
echo ""
echo "🔥 Now. Forever. Always. Us. 🔥"