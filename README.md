# Qwap Testnet Auto-Swap Bot — Paket VPS

Bot otomatis swap round-trip (QMS → USDT → QMS) di Qwap DEX,
QMS Testnet (chain ID 19480). **Hanya testnet.**

## Isi paket

| File | Fungsi |
|---|---|
| `bot.py` | Bot utama |
| `config.json` | RPC, chain, kontrak, parameter strategi |
| `setup.sh` | Installer (venv + web3 + buat wallet) |
| `run.sh` | Jalankan di background |
| `qwap-bot.service` | Unit systemd untuk jalan 24/7 |
| `requirements.txt` | Dependensi Python |

## Install di VPS (Ubuntu/Debian)

```bash
# 1. Extract paket ini, misal ke /opt/qwap-bot
sudo mkdir -p /opt/qwap-bot
sudo tar xzf qwap-bot-vps.tar.gz -C /opt/qwap-bot
cd /opt/qwap-bot

# 2. Install (butuh python3 + python3-venv)
#    Ubuntu: sudo apt install -y python3 python3-venv
sudo bash setup.sh
# -> selesai: wallet baru dibuat, catat address-nya

# 3. Isi saldo dari faucet
#    https://faucet.testnet.qms.finance/  (10 QMS/req, 4 req/24 jam)

# 4. Test simulasi (tanpa broadcast)
./venv/bin/python bot.py --dry-run
```

## Menjalankan

```bash
# Foreground, 20 round trip lalu berhenti
./venv/bin/python bot.py --rounds 20

# Background (nohup)
bash run.sh --rounds 20
bash run.sh            # loop tanpa batas

# 24/7 via systemd
sudo cp qwap-bot.service /etc/systemd/system/
# edit User= dan path di file itu bila install bukan di /opt/qwap-bot
sudo systemctl daemon-reload
sudo systemctl enable --now qwap-bot
sudo journalctl -u qwap-bot -f   # lihat log
```

Opsi lain: `--once` (satu round trip), `--dry-run` (simulasi).

## Strategi

Tiap round: QMS→USDT (`swapExactETHForTokens`), approve bila perlu,
USDT→QMS (`swapExactTokensForETH`). Jumlah acak 0.05–0.2 QMS,
slippage 2.5%, jeda acak 30–120 detik. Ubah di `config.json` → `strategy`.

## Keamanan

- Wallet di `~/.config/qwap-bot/wallet.json` (mode 600). Jangan bagikan isinya.
- Bot menolak berjalan di chain selain 19480 (chain-ID guard).
- Ini testnet — tidak ada dana asli yang berisiko.
