#!/usr/bin/env python3
"""Qwap testnet auto-swap bot.

Automates round-trip swaps on Qwap (UniswapV2-style AMM) on QMS Testnet
(chain ID 19480). TESTNET ONLY — the bot refuses to run on any other chain.

Strategy (default): each round does QMS -> USDT -> QMS
  1. swap native QMS -> USDT via swapExactETHForTokens
  2. approve USDT -> router (only when allowance is insufficient)
  3. swap USDT -> QMS via swapExactTokensForETH
  4. random sleep, repeat

Usage:
  ./venv/bin/python bot.py                  # run with config.json strategy
  ./venv/bin/python bot.py --dry-run        # simulate, broadcast nothing
  ./venv/bin/python bot.py --rounds 5       # stop after 5 round trips
  ./venv/bin/python bot.py --once           # single round trip then exit

On first run a fresh wallet is generated at ~/.config/qwap-bot/wallet.json
(mode 0600). Fund it from the faucet: https://faucet.testnet.qms.finance/
(10 QMS per request, max 4 requests / 24h), then run again.
"""

import argparse
import json
import os
import random
import sys
import time

from eth_account import Account
from web3 import Web3

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "config.json")
WALLET_PATH = os.path.expanduser("~/.config/qwap-bot/wallet.json")
EXPLORER = "https://testnet.qmsscan.io/tx/"

ROUTER_ABI = [
    {"name": "WQMS", "type": "function", "stateMutability": "view", "inputs": [],
     "outputs": [{"name": "", "type": "address"}]},
    {"name": "getAmountsOut", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "amountIn", "type": "uint256"}, {"name": "path", "type": "address[]"}],
     "outputs": [{"name": "amounts", "type": "uint256[]"}]},
    {"name": "swapExactETHForTokens", "type": "function", "stateMutability": "payable",
     "inputs": [{"name": "amountOutMin", "type": "uint256"}, {"name": "path", "type": "address[]"},
                {"name": "to", "type": "address"}, {"name": "deadline", "type": "uint256"}],
     "outputs": [{"name": "amounts", "type": "uint256[]"}]},
    {"name": "swapExactTokensForETH", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "amountIn", "type": "uint256"}, {"name": "amountOutMin", "type": "uint256"},
                {"name": "path", "type": "address[]"}, {"name": "to", "type": "address"},
                {"name": "deadline", "type": "uint256"}],
     "outputs": [{"name": "amounts", "type": "uint256[]"}]},
]

ERC20_ABI = [
    {"name": "decimals", "type": "function", "stateMutability": "view", "inputs": [],
     "outputs": [{"name": "", "type": "uint8"}]},
    {"name": "balanceOf", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "account", "type": "address"}], "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "allowance", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "approve", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
     "outputs": [{"name": "", "type": "bool"}]},
]


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_wallet():
    """Load or (first run) generate the bot wallet. Key file is 0600."""
    os.makedirs(os.path.dirname(WALLET_PATH), mode=0o700, exist_ok=True)
    if os.path.exists(WALLET_PATH):
        with open(WALLET_PATH) as f:
            key = json.load(f)["private_key"]
        return Account.from_key(key)
    acct = Account.create()
    with open(WALLET_PATH, "w") as f:
        json.dump({"address": acct.address, "private_key": acct.key.hex()}, f)
    os.chmod(WALLET_PATH, 0o600)
    print(f"Wallet baru dibuat: {acct.address}")
    print("Private key tersimpan di ~/.config/qwap-bot/wallet.json (mode 600, tidak ditampilkan).")
    print("Isi saldo dari faucet https://faucet.testnet.qms.finance/ lalu jalankan lagi.")
    sys.exit(0)


def send_tx(w3, acct, tx, dry_run, label):
    tx.setdefault("chainId", w3.eth.chain_id)
    tx.setdefault("nonce", w3.eth.get_transaction_count(acct.address))
    if "gas" not in tx:
        tx["gas"] = int(w3.eth.estimate_gas({k: v for k, v in tx.items() if k != "gas"}) * 1.2)
    if "gasPrice" not in tx and "maxFeePerGas" not in tx:
        tx["gasPrice"] = w3.eth.gas_price
    if dry_run:
        print(f"  [DRY-RUN] {label}: {tx}")
        return None
    signed = acct.sign_transaction(tx)
    h = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"  {label}: {h.hex()}  ({EXPLORER}{h.hex()})")
    receipt = w3.eth.wait_for_transaction_receipt(h, timeout=120)
    status = "OK" if receipt.status == 1 else "GAGAL"
    print(f"    -> {status} (block {receipt.blockNumber}, gas {receipt.gasUsed})")
    if receipt.status != 1:
        raise RuntimeError(f"tx gagal: {h.hex()}")
    return h.hex()


def ensure_approval(w3, acct, token, spender, amount, dry_run):
    t = w3.eth.contract(address=token, abi=ERC20_ABI)
    if t.functions.allowance(acct.address, spender).call() >= amount:
        return
    print("  approve USDT -> router (max)")
    tx = t.functions.approve(spender, 2**256 - 1).build_transaction({"from": acct.address})
    send_tx(w3, acct, tx, dry_run, "approve")


def round_trip(w3, acct, cfg, dry_run):
    s = cfg["strategy"]
    router = w3.eth.contract(address=cfg["router"], abi=ROUTER_ABI)
    wqms = router.functions.WQMS().call()
    usdt = cfg["tokens"]["USDT"]
    to = acct.address
    deadline = int(time.time()) + 1200
    slip = 1 - s["slippage_pct"] / 100

    # --- leg 1: QMS -> USDT ---
    amount_in = w3.to_wei(random.uniform(s["min_amount_qms"], s["max_amount_qms"]), "ether")
    quoted = router.functions.getAmountsOut(amount_in, [wqms, usdt]).call()[1]
    min_out = int(quoted * slip)
    print(f"Leg 1: {w3.from_wei(amount_in, 'ether'):.4f} QMS -> ~{quoted/1e6:.4f} USDT (min {min_out/1e6:.4f})")
    if dry_run:
        print(f"  [DRY-RUN] swapExactETHForTokens(amountOutMin={min_out}, path=[WQMS, USDT], to={to}) value={w3.from_wei(amount_in, 'ether'):.4f} QMS")
    else:
        tx = router.functions.swapExactETHForTokens(
            min_out, [wqms, usdt], to, deadline
        ).build_transaction({"from": to, "value": amount_in})
        send_tx(w3, acct, tx, dry_run, "swap QMS->USDT")

    # --- leg 2: USDT -> QMS ---
    erc = w3.eth.contract(address=usdt, abi=ERC20_ABI)
    if dry_run:
        bal = quoted  # dummy: pakai hasil quote leg 1 agar tidak revert saat simulasi
        print(f"Leg 2 (simulasi): {bal/1e6:.4f} USDT -> QMS")
        quoted_back = router.functions.getAmountsOut(bal, [usdt, wqms]).call()[1]
        print(f"  -> ~{w3.from_wei(quoted_back, 'ether'):.4f} QMS")
        return
    bal = erc.functions.balanceOf(to).call()
    if bal == 0:
        raise RuntimeError("saldo USDT 0 setelah leg 1 — berhenti")
    ensure_approval(w3, acct, usdt, cfg["router"], bal, dry_run)
    quoted_back = router.functions.getAmountsOut(bal, [usdt, wqms]).call()[1]
    min_back = int(quoted_back * slip)
    print(f"Leg 2: {bal/1e6:.4f} USDT -> ~{w3.from_wei(quoted_back, 'ether'):.4f} QMS (min {w3.from_wei(min_back, 'ether'):.4f})")
    tx = router.functions.swapExactTokensForETH(
        min_back, [usdt, wqms], to, deadline
    ).build_transaction({"from": to, "value": 0})
    send_tx(w3, acct, tx, dry_run, "swap USDT->QMS")


def main():
    ap = argparse.ArgumentParser(description="Qwap testnet auto-swap bot")
    ap.add_argument("--dry-run", action="store_true", help="simulasi tanpa broadcast")
    ap.add_argument("--rounds", type=int, default=0, help="jumlah round trip (0 = tanpa batas)")
    ap.add_argument("--once", action="store_true", help="satu round trip lalu berhenti")
    args = ap.parse_args()

    cfg = load_config()
    w3 = Web3(Web3.HTTPProvider(cfg["rpc"], request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        sys.exit("RPC tidak terhubung: " + cfg["rpc"])
    if w3.eth.chain_id != cfg["chain_id"]:
        sys.exit(f"CHAIN ID SALAH ({w3.eth.chain_id}) — bot hanya jalan di QMS Testnet 19480. Berhenti.")
    print(f"Tersambung: chain {w3.eth.chain_id} (QMS Testnet), block {w3.eth.block_number}")

    acct = get_wallet()
    print(f"Wallet: {acct.address}")
    bal = w3.eth.get_balance(acct.address)
    print(f"Saldo: {w3.from_wei(bal, 'ether'):.4f} QMS")
    need = w3.to_wei(cfg["strategy"]["min_amount_qms"] * 2, "ether")
    if bal < need:
        print(f"Saldo kurang (butuh ~{w3.from_wei(need, 'ether'):.2f} QMS). Isi dari https://faucet.testnet.qms.finance/")
        if not args.dry_run:
            sys.exit(1)

    if args.dry_run:
        print("== DRY-RUN ==")
    rounds = 1 if args.once else (args.rounds or float("inf"))
    i = 0
    try:
        while i < rounds:
            i += 1
            print(f"\n--- Round {i} ---")
            round_trip(w3, acct, cfg, args.dry_run)
            if i >= rounds or args.dry_run:
                break
            s = cfg["strategy"]
            delay = random.uniform(s["min_delay_s"], s["max_delay_s"])
            print(f"Jeda {delay:.0f} dtk...")
            time.sleep(delay)
    except KeyboardInterrupt:
        print("\nBerhenti oleh pengguna.")
    print(f"\nSelesai: {i} round.")


if __name__ == "__main__":
    main()
