#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════════
#  DigitalOcean Droplet — dağıtım / güncelleme scripti
#  Repoyu günceller, production container'larını yeniden derleyip başlatır.
#
#  Kullanım (sunucuda, repo kökünde):
#    ./scripts/deploy-digitalocean.sh
#
#  Ön koşul: .env dosyası hazır olmalı  ->  cp .env.digitalocean.example .env
# ════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# Nereden çağrılırsa çağrılsın repo köküne geç (script konumuna göre)
cd "$(dirname "$0")/.."

COMPOSE_FILE="docker-compose.prod.yml"

# .env yoksa erken ve net uyar
if [ ! -f .env ]; then
    echo "✗ .env bulunamadı. Önce: cp .env.digitalocean.example .env (ve doldur)" >&2
    exit 1
fi

echo "▶ [1/4] Son değişiklikler çekiliyor (git pull)..."
git pull --ff-only

echo "▶ [2/4] Mevcut container'lar durduruluyor..."
docker compose -f "$COMPOSE_FILE" down

echo "▶ [3/4] Yeniden derlenip arka planda başlatılıyor..."
docker compose -f "$COMPOSE_FILE" up --build -d

echo "▶ [4/4] Çalışan container'lar:"
docker compose -f "$COMPOSE_FILE" ps

echo
echo "✅ Dağıtım tamamlandı."
echo "   Sağlık kontrolü:  curl -fsS http://localhost:8000/health"
