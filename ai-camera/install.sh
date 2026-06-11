#!/bin/bash
# One-shot installer for the AI camera on Raspberry Pi OS (Bookworm).
# Run on the Pi:  sudo bash install.sh
set -e

if [ "$EUID" -ne 0 ]; then
  echo "Please run with sudo: sudo bash install.sh"
  exit 1
fi

REAL_USER="${SUDO_USER:-pi}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR=/opt/ai-camera
CONFIG_TXT=/boot/firmware/config.txt

echo "==> Installing apt dependencies"
apt-get update
apt-get install -y python3-pil python3-numpy python3-requests \
  python3-spidev python3-libgpiod fonts-noto-cjk rpicam-apps git

echo "==> Installing Whisplay HAT driver"
if [ ! -d "$REAL_HOME/Whisplay" ]; then
  sudo -u "$REAL_USER" git clone https://github.com/PiSugar/Whisplay.git --depth 1 "$REAL_HOME/Whisplay"
  bash "$REAL_HOME/Whisplay/install_driver.sh"
else
  echo "    $REAL_HOME/Whisplay already exists, skipping clone"
fi

echo "==> Enabling the IMX708 (CAM109) camera in $CONFIG_TXT"
if ! grep -q "^dtoverlay=imx708" "$CONFIG_TXT"; then
  sed -i 's/^camera_auto_detect=1/camera_auto_detect=0/' "$CONFIG_TXT"
  grep -q "^camera_auto_detect=0" "$CONFIG_TXT" || echo "camera_auto_detect=0" >> "$CONFIG_TXT"
  echo "dtoverlay=imx708,cam0" >> "$CONFIG_TXT"
else
  echo "    imx708 overlay already present, skipping"
fi

echo "==> Installing app to $APP_DIR"
mkdir -p "$APP_DIR"
cp "$SRC_DIR/camera_app.py" "$SRC_DIR/prompts.json" "$APP_DIR/"
sed "s|~/Whisplay|$REAL_HOME/Whisplay|" "$SRC_DIR/config.example.env" > /tmp/ai-camera.env.example
if [ ! -f /etc/ai-camera.env ]; then
  cp /tmp/ai-camera.env.example /etc/ai-camera.env
  chmod 600 /etc/ai-camera.env
  echo "    created /etc/ai-camera.env  <-- PUT YOUR OPENAI_API_KEY HERE"
fi
# the service runs as root, but gallery/driver paths resolve to the real user's home
sed -i "s|GALLERY_DIR=~/|GALLERY_DIR=$REAL_HOME/|; s|WHISPLAY_DIR=~/|WHISPLAY_DIR=$REAL_HOME/|" /etc/ai-camera.env || true

echo "==> Installing systemd service"
cp "$SRC_DIR/ai-camera.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable ai-camera.service

echo
echo "Done. Next steps:"
echo "  1. sudo nano /etc/ai-camera.env     # set OPENAI_API_KEY"
echo "  2. sudo reboot                      # applies camera + HAT overlays"
echo "  3. after reboot the app starts automatically; check with:"
echo "     systemctl status ai-camera ; journalctl -u ai-camera -f"
