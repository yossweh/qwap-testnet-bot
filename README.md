# Qwap Testnet Auto Bot — Paket VPS

Bot otomatis untuk Qwap DEX di QMS Testnet (chain ID 19480). **Hanya testnet.**
Terinspirasi UX Oroswap-Auto-Bot: multi-wallet, cycle swap + liquidity,
logging berwarna, mode loop 24 jam.

## Fitur

- **Swap otomatis**: 10 swap per cycle, alternating QMS→USDT / USDT→QMS
- **Liquidity**: add + remove liquidity tiap cycle (UniswapV2)
- **Multi-wallet**: semua wallet di `wallets.json` diproses berurutan
- **Mode 24 jam**: countdown lalu ulangi cycle otomatis
- **Retry otomatis** tiap tx yang gagal (3x), lanjut walau ada yang gagal
- **Chain guard**: menolak jalan di chain selain 19480

## Isi paket

| File | Fungsi |
|---|---|
| `bot.py` | Bot utama |
| `config.json` | RPC, chain, kontrak, parameter cycle |
| `setup.sh` | Installer (venv + web3 + buat wallet) |
| `run.sh` | Jalankan di background |
| `qwap-bot.service` | Unit systemd untuk 24/7 |
| `requirements.txt` | Dependensi Python |

## Install di VPS (Ubuntu/Debian)

```bash
sudo mkdir -p /opt/qwap-bot
sudo tar xzf qwap-bot-vps.tar.gz -C /opt/qwap-bot
cd /opt/qwap-bot
# Ubuntu: sudo apt install -y python3 python3-venv
sudo bash setup.sh        # -> wallet baru dibuat, catat address-nya
```

Isi saldo dari faucet: https://faucet.testnet.qms.finance/ (10 QMS/req, 4 req/24 jam)

## Menjalankan

```bash
./venv/bin/python bot.py              # prompt interaktif: jumlah cycle
./venv/bin/python bot.py --rounds 3   # 3 cycle per wallet lalu berhenti
./venv/bin/python bot.py --once       # 1 cycle
./venv/bin/python bot.py --loop-24h   # cycle, countdown 24 jam, ulangi
./venv/bin/python bot.py --dry-run    # simulasi tanpa broadcast

bash run.sh --loop-24h                # background
sudo cp qwap-bot.service /etc/systemd/system/
sudo systemctl enable --now qwap-bot  # 24/7
```

## Multi-wallet

Tambah wallet ke `~/.config/qwap-bot/wallets.json` (mode 600):

```json
[
  {"address": "0x...", "private_key": "..."},
  {"address": "0x...", "private_key": "..."}
]
```

Jangan commit file ini. Tiap wallet butuh saldo QMS sendiri untuk gas.

## Konfigurasi (config.json → cycle)

| Key | Arti |
|---|---|
| `swaps_per_cycle` | jumlah swap per cycle (default 10) |
| `min_swap_qms` / `max_swap_qms` | rentang jumlah swap acak |
| `add_liquidity` | true/false |
| `liquidity_qms` | QMS untuk add liquidity per cycle |
| `slippage_pct` | slippage |
| `min_delay_s` / `max_delay_s` | jeda acak antar cycle |
| `max_retries` | retry per tx |

`points_url` opsional — isi URL API points dengan placeholder `{address}`
bila Qwap/QMS punya endpoint points.

## Keamanan

- Wallet di `~/.config/qwap-bot/wallets.json` (mode 600). Jangan bagikan.
- Testnet — tidak ada dana asli yang berisiko.
