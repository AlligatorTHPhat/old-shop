#!/usr/bin/env bash
# One-time preparation of a fresh Ubuntu 22.04/24.04 VPS. Run as root:
#   curl -fsSL https://raw.githubusercontent.com/<you>/<repo>/main/deploy/scripts/bootstrap-vps.sh | sudo bash -s -- <repo-url>
# or, after cloning: sudo deploy/scripts/bootstrap-vps.sh <repo-url>
set -euo pipefail

REPO_URL="${1:-}"
APP_DIR=/opt/oldshop
DEPLOY_USER=deploy

[[ $EUID -eq 0 ]] || { echo "Run as root" >&2; exit 1; }
log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

log "System packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get upgrade -yq
apt-get install -yq ca-certificates curl git ufw fail2ban unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades

if ! command -v docker >/dev/null; then
  log "Docker Engine + compose plugin"
  curl --proto '=https' --tlsv1.2 -fsSL https://get.docker.com | sh
fi

log "Docker log rotation (Promtail/Filebeat read these files)"
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "5" },
  "live-restore": true
}
JSON
systemctl restart docker

log "Deploy user '$DEPLOY_USER'"
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$DEPLOY_USER"
  mkdir -p /home/$DEPLOY_USER/.ssh
  # Reuse root's authorized key so CI can SSH in as the deploy user.
  [[ -f /root/.ssh/authorized_keys ]] && cp /root/.ssh/authorized_keys /home/$DEPLOY_USER/.ssh/
  chown -R $DEPLOY_USER:$DEPLOY_USER /home/$DEPLOY_USER/.ssh
  chmod 700 /home/$DEPLOY_USER/.ssh
fi
usermod -aG docker "$DEPLOY_USER"

log "Firewall: SSH, HTTP, HTTPS only"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable
systemctl enable --now fail2ban

log "Kernel settings (Elasticsearch needs vm.max_map_count)"
cat > /etc/sysctl.d/99-oldshop.conf <<'SYSCTL'
vm.max_map_count=262144
vm.swappiness=10
SYSCTL
sysctl --system >/dev/null

if ! swapon --show | grep -q .; then
  log "2 GB swap file"
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

if [[ -n "$REPO_URL" && ! -d "$APP_DIR/.git" ]]; then
  log "Cloning $REPO_URL into $APP_DIR"
  git clone "$REPO_URL" "$APP_DIR"
fi
mkdir -p "$APP_DIR"
chown -R $DEPLOY_USER:$DEPLOY_USER "$APP_DIR"

log "Done. Next steps (as $DEPLOY_USER):"
cat <<EOF
  cd $APP_DIR
  cp deploy/.env.example deploy/.env && nano deploy/.env
  echo <GHCR_TOKEN> | docker login ghcr.io -u <github-user> --password-stdin   # if images are private
  deploy/scripts/deploy.sh
EOF
