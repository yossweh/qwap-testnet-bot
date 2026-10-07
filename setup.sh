#!/bin/bash
# Setup Qwap testnet bot di VPS (Ubuntu/Debian).
#   1. Upload/extract paket ini ke VPS, misal /opt/qwap-bot
#   2. sudo bash setup.sh   (atau bash setup.sh untuk install lokal user)
# Script ini: cek python3, buat venv, install web3, buat wallet baru (0600).
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "== Cek python3 =="
command -v python3 >/dev/null || { echo "python3 tidak ditemukan. Install dulu: sudo apt install python3 python3-venv"; exit 1; }
python3 --version

echo "== Buat virtualenv =="
[ -d venv ] || python3 -m venv venv

echo "== Install dependencies =="
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q -r requirements.txt
./venv/bin/python -c "import web3; print('web3.py', web3.__version__)"

echo "== Wallet =="
WALLET_DIR="$HOME/.config/qwap-bot"
WALLET_FILE="$WALLET_DIR/wallet.json"
mkdir -p "$WALLET_DIR"
chmod 700 "$WALLET_DIR"
if [ -f "$WALLET_FILE" ]; then
  ADDR=$(./venv/bin/python -c "import json; print(json.load(open('$WALLET_FILE'))['address'])")
  echo "Wallet sudah ada: $ADDR"
else
  ADDR=$(./venv/bin/python -c "
from eth_account import Account
import json, os
acct = Account.create()
p = os.path.expanduser('~/.config/qwap-bot/wallet.json')
open(p, 'w').write(json.dumps({'address': acct.address, 'private_key': acct.key.hex()}))
os.chmod(p, 0o600)
print(acct.address)
")
  echo "Wallet BARU dibuat: $ADDR"
  echo "Private key tersimpan di $WALLET_FILE (mode 600). JANGAN dibagikan."
fi

echo ""
echo "== SELESAI =="
echo "1. Isi saldo wallet dari faucet: https://faucet.testnet.qms.finance/"
echo "   (10 QMS per request, maks 4 request / 24 jam)"
echo "2. Test dulu: ./venv/bin/python bot.py --dry-run"
echo "3. Jalan di foreground: ./venv/bin/python bot.py --rounds 20"
echo "   Jalan di background : bash run.sh --rounds 20"
echo "   24/7 via systemd    : sudo cp qwap-bot.service /etc/systemd/system/ && sudo systemctl enable --now qwap-bot"
