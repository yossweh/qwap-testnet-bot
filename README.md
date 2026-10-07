# Qwap Testnet Auto Bot 🚀

Automated swap + liquidity bot for [Qwap DEX](https://testnet.qwap.xyz/) on QMS Testnet.
Performs alternating swaps and liquidity cycles to generate on-chain activity.

> ⚠️ **Testnet only.** This bot refuses to run on any chain other than QMS Testnet (chain ID `19480`).
> No real funds are ever at risk.

## 🌟 Features

- **Automated Swapping** — 10 swaps per cycle, alternating QMS→USDT / USDT→QMS with random amounts
- **Liquidity Management** — automatically adds then removes liquidity every cycle (UniswapV2-style)
- **Multi-Wallet Support** — processes all wallets in `wallets.json` sequentially
- **24-Hour Loop Mode** — countdown timer, then repeats cycles automatically
- **Colored CLI Logging** — every tx printed with explorer link
- **Auto-Retry** — failed transactions retried 3× before moving on
- **Chain Guard** — hard refusal on wrong chain ID
- **Dry-Run Mode** — simulate a full cycle without broadcasting anything

## 📋 Prerequisites

- Python 3.8+ (`python3-venv` on Debian/Ubuntu)
- QMS testnet tokens from the faucet for gas + swaps

## 🚀 Installation

```bash
git clone https://github.com/yossweh/qwap-testnet-bot.git
cd qwap-testnet-bot
bash setup.sh
```

`setup.sh` creates a virtualenv, installs `web3.py`, and generates a fresh wallet at
`~/.config/qwap-bot/wallets.json` (mode `600`). **Fund it first:**

- Faucet: https://faucet.testnet.qms.finance/ (10 QMS per request, max 4 requests / 24h)

Verify with a dry run (broadcasts nothing):

```bash
./venv/bin/python bot.py --dry-run
```

## 🏃 Usage

```bash
./venv/bin/python bot.py              # interactive prompt: number of cycles
./venv/bin/python bot.py --rounds 3   # 3 cycles per wallet, then exit
./venv/bin/python bot.py --once       # single cycle
./venv/bin/python bot.py --loop-24h   # run cycles, 24h countdown, repeat
./venv/bin/python bot.py --dry-run    # simulate only

# background
bash run.sh --loop-24h

# 24/7 via systemd
sudo cp qwap-bot.service /etc/systemd/system/
sudo systemctl enable --now qwap-bot
```

## 📊 Transaction Flow

Each cycle, per wallet:

1. **10 swaps** (alternating)
   - Swap 1,3,5,7,9: QMS → USDT (`swapExactETHForTokens`)
   - Swap 2,4,6,8,10: USDT → QMS (`swapExactTokensForETH`, auto-approve)
2. **Add liquidity** — QMS + USDT via `addLiquidityETH`
3. **Remove liquidity** — withdraw all LP tokens via `removeLiquidityETH`
4. **Delay** — random 30–120s before next cycle (configurable)

## ⚙️ Configuration

`config.json` → `cycle`:

| Key | Default | Description |
|---|---|---|
| `swaps_per_cycle` | 10 | swaps per cycle |
| `min_swap_qms` / `max_swap_qms` | 0.05 / 0.2 | random swap size (QMS) |
| `add_liquidity` | true | add+remove liquidity each cycle |
| `liquidity_qms` | 0.1 | QMS committed to liquidity per cycle |
| `slippage_pct` | 2.5 | slippage tolerance |
| `min_delay_s` / `max_delay_s` | 30 / 120 | random delay between cycles |
| `max_retries` | 3 | retries per failed tx |

`points_url` (optional): set an API URL with an `{address}` placeholder if a points
endpoint exists — the bot will query and display it after each cycle.

### Multi-wallet

`~/.config/qwap-bot/wallets.json` (mode `600`, never commit):

```json
[
  {"address": "0x...", "private_key": "..."},
  {"address": "0x...", "private_key": "..."}
]
```

Each wallet needs its own QMS for gas.

## 🔧 Technical Details

| Item | Value |
|---|---|
| Network | QMS Testnet (EVM) |
| Chain ID | 19480 (`0x4c18`) |
| RPC | https://rpc.testnet.qms.finance |
| Explorer | https://testnet.qmsscan.io |
| QwapRouter | `0x93AFF45f28e5DF1b55f5AEFEfB807De843b12619` (UniswapV2-style) |
| QwapFactory | `0x93AFD9aC50822F82c7C4f2Ec8Ec2463b086Fb878` |
| WQMS | `0x9AA510295aC664A3d5A3182a3eFe959DE2B12c34` |
| USDT | `0x72577544f4134a25E7f09d0B5FF0ca05A1249EbF` |
| USDC | `0xDfF68E53a0A8275212927c12017f5aB5f1842a04` |

## 🛡️ Safety

- Private keys stay in `~/.config/qwap-bot/wallets.json` (`600`), never in the repo (`.gitignore` enforced)
- Chain-ID guard aborts on any network other than 19480
- Slippage protection (`amountOutMin`) on every swap and liquidity op
- Testnet: no real funds at risk

## 🐛 Troubleshooting

- **"Saldo kurang"** — fund the wallet from the faucet and re-run
- **"CHAIN ID SALAH"** — RPC is pointing at the wrong network; check `config.json`
- **Swap skipped: USDT kurang** — normal on low balances; the bot continues with the next leg
- **RPC timeouts** — the public RPC can be slow; the bot retries txs automatically

## ⚠️ Disclaimer

For educational and research purposes. Use at your own risk. Test with small amounts first.
Not financial advice — DYOR.

## 📄 License

MIT
