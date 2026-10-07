#!/usr/bin/env python3
"""Qwap Testnet Auto Bot.

Automated swap + liquidity cycles on Qwap DEX (UniswapV2-style AMM),
QMS Testnet (chain ID 19480). TESTNET ONLY — refuses any other chain.

Each cycle per wallet:
  1. N alternating swaps (QMS->USDT, USDT->QMS, ...)
  2. Add liquidity (QMS + USDT)
  3. Remove liquidity (withdraw all LP)
  4. Optional points check (if points_url is set in config)

Wallets live in ~/.config/qwap-bot/wallets.json (mode 0600):
  [{"address": "0x...", "private_key": "..."}]
On first run a fresh wallet is generated; fund it from
https://faucet.testnet.qms.finance/ then re-run. Append more entries
manually to run multiple wallets (never commit this file).

Usage:
  ./venv/bin/python bot.py                 # interactive prompt (cycles)
  ./venv/bin/python bot.py --rounds 3      # 3 cycles per wallet, then exit
  ./venv/bin/python bot.py --once          # single cycle then exit
  ./venv/bin/python bot.py --loop-24h      # cycles, then 24h countdown, repeat
  ./venv/bin/python bot.py --dry-run       # simulate, broadcast nothing
"""

import argparse
import json
import os
import random
import sys
import time

import requests
from eth_account import Account
from web3 import Web3

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "config.json")
WALLETS_PATH = os.path.expanduser("~/.config/qwap-bot/wallets.json")
LEGACY_WALLET_PATH = os.path.expanduser("~/.config/qwap-bot/wallet.json")
EXPLORER = "https://testnet.qmsscan.io/tx/"

# ---------------------------------------------------------------- colors/log
C = {
    "reset": "\x1b[0m", "cyan": "\x1b[36m", "green": "\x1b[32m",
    "yellow": "\x1b[33m", "red": "\x1b[31m", "white": "\x1b[37m",
    "bold": "\x1b[1m", "magenta": "\x1b[35m",
}


def log_info(m):    print(f"{C['green']}[✓] {m}{C['reset']}")
def log_warn(m):    print(f"{C['yellow']}[⚠] {m}{C['reset']}")
def log_error(m):   print(f"{C['red']}[✗] {m}{C['reset']}")
def log_ok(m):      print(f"{C['green']}[✅] {m}{C['reset']}")
def log_load(m):    print(f"{C['cyan']}[⟳] {m}{C['reset']}")
def log_step(m):    print(f"{C['white']}[➤] {m}{C['reset']}")
def banner():
    print(f"{C['cyan']}{C['bold']}")
    print("-----------------------------------------------")
    print("  Qwap Testnet Auto Bot")
    print("-----------------------------------------------")
    print(f"{C['reset']}")


# ------------------------------------------------------------------ ABIs
ROUTER_ABI = [
    {"name": "WQMS", "type": "function", "stateMutability": "view", "inputs": [],
     "outputs": [{"name": "", "type": "address"}]},
    {"name": "factory", "type": "function", "stateMutability": "view", "inputs": [],
     "outputs": [{"name": "", "type": "address"}]},
    {"name": "getAmountsOut", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "amountIn", "type": "uint256"}, {"name": "path", "type": "address[]"}],
     "outputs": [{"name": "amounts", "type": "uint256[]"}]},
    {"name": "quote", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "amountA", "type": "uint256"}, {"name": "reserveA", "type": "uint256"},
                {"name": "reserveB", "type": "uint256"}],
     "outputs": [{"name": "amountB", "type": "uint256"}]},
    {"name": "swapExactETHForTokens", "type": "function", "stateMutability": "payable",
     "inputs": [{"name": "amountOutMin", "type": "uint256"}, {"name": "path", "type": "address[]"},
                {"name": "to", "type": "address"}, {"name": "deadline", "type": "uint256"}],
     "outputs": [{"name": "amounts", "type": "uint256[]"}]},
    {"name": "swapExactTokensForETH", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "amountIn", "type": "uint256"}, {"name": "amountOutMin", "type": "uint256"},
                {"name": "path", "type": "address[]"}, {"name": "to", "type": "address"},
                {"name": "deadline", "type": "uint256"}],
     "outputs": [{"name": "amounts", "type": "uint256[]"}]},
    {"name": "addLiquidityETH", "type": "function", "stateMutability": "payable",
     "inputs": [{"name": "token", "type": "address"}, {"name": "amountTokenDesired", "type": "uint256"},
                {"name": "amountTokenMin", "type": "uint256"}, {"name": "amountETHMin", "type": "uint256"},
                {"name": "to", "type": "address"}, {"name": "deadline", "type": "uint256"}],
     "outputs": [{"name": "amountToken", "type": "uint256"}, {"name": "amountETH", "type": "uint256"},
                 {"name": "liquidity", "type": "uint256"}]},
    {"name": "removeLiquidityETH", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "token", "type": "address"}, {"name": "liquidity", "type": "uint256"},
                {"name": "amountTokenMin", "type": "uint256"}, {"name": "amountETHMin", "type": "uint256"},
                {"name": "to", "type": "address"}, {"name": "deadline", "type": "uint256"}],
     "outputs": [{"name": "amountToken", "type": "uint256"}, {"name": "amountETH", "type": "uint256"}]},
]

FACTORY_ABI = [
    {"name": "getPair", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "tokenA", "type": "address"}, {"name": "tokenB", "type": "address"}],
     "outputs": [{"name": "pair", "type": "address"}]},
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


# ------------------------------------------------------------------ config
def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_wallets():
    """Return list of Account. Migrates legacy single wallet.json, else generates one."""
    os.makedirs(os.path.dirname(WALLETS_PATH), mode=0o700, exist_ok=True)
    if os.path.exists(WALLETS_PATH):
        with open(WALLETS_PATH) as f:
            data = json.load(f)
        return [Account.from_key(e["private_key"]) for e in data]
    entries = []
    if os.path.exists(LEGACY_WALLET_PATH):
        with open(LEGACY_WALLET_PATH) as f:
            old = json.load(f)
        entries.append({"address": old["address"], "private_key": old["private_key"]})
        log_info(f"Wallet lama dimigrasi: {old['address']}")
    else:
        acct = Account.create()
        entries.append({"address": acct.address, "private_key": acct.key.hex()})
        print(f"Wallet baru dibuat: {acct.address}")
        print("Private key tersimpan di ~/.config/qwap-bot/wallets.json (mode 600).")
        print("Isi saldo dari https://faucet.testnet.qms.finance/ lalu jalankan lagi.")
    with open(WALLETS_PATH, "w") as f:
        json.dump(entries, f)
    os.chmod(WALLETS_PATH, 0o600)
    if len(entries) == 1 and not os.path.exists(LEGACY_WALLET_PATH):
        sys.exit(0)  # wallet baru -> minta funding dulu
    return [Account.from_key(e["private_key"]) for e in entries]


# ------------------------------------------------------------------ chain ops
class Bot:
    def __init__(self, w3, acct, cfg):
        self.w3 = w3
        self.acct = acct
        self.cfg = cfg
        self.cycle_cfg = cfg["cycle"]
        self.router = w3.eth.contract(address=cfg["router"], abi=ROUTER_ABI)
        self.wqms = self.router.functions.WQMS().call()
        self.usdt = cfg["tokens"]["USDT"]
        self.usdt_c = w3.eth.contract(address=self.usdt, abi=ERC20_ABI)
        self.slip = 1 - self.cycle_cfg["slippage_pct"] / 100
        self.retries = self.cycle_cfg.get("max_retries", 3)

    def deadline(self):
        return int(time.time()) + 1200

    def send_tx(self, tx, label):
        w3, acct = self.w3, self.acct
        tx.setdefault("chainId", w3.eth.chain_id)
        tx.setdefault("nonce", w3.eth.get_transaction_count(acct.address))
        if "gas" not in tx:
            tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.2)
        if "gasPrice" not in tx and "maxFeePerGas" not in tx:
            tx["gasPrice"] = w3.eth.gas_price
        last_err = None
        for attempt in range(1, self.retries + 1):
            try:
                signed = acct.sign_transaction(tx)
                h = w3.eth.send_raw_transaction(signed.raw_transaction)
                log_ok(f"{label}: {EXPLORER}{h.hex()}")
                rcpt = w3.eth.wait_for_transaction_receipt(h, timeout=120)
                if rcpt.status == 1:
                    return h.hex()
                last_err = f"tx revert {h.hex()}"
            except Exception as e:
                last_err = str(e)
            log_warn(f"{label} gagal (percobaan {attempt}/{self.retries}): {last_err}")
            tx["nonce"] = w3.eth.get_transaction_count(acct.address)
            time.sleep(2)
        log_error(f"{label} gagal setelah {self.retries} percobaan, lanjut.")
        return None

    def ensure_approval(self, token_c, spender, amount, dry_run):
        if token_c.functions.allowance(self.acct.address, spender).call() >= amount:
            return
        log_load("Approve token -> router (max)")
        if dry_run:
            print("  [DRY-RUN] approve(max)")
            return
        tx = token_c.functions.approve(spender, 2**256 - 1).build_transaction(
            {"from": self.acct.address})
        self.send_tx(tx, "approve")

    def qms_balance(self):
        return self.w3.eth.get_balance(self.acct.address)

    def usdt_balance(self):
        return self.usdt_c.functions.balanceOf(self.acct.address).call()

    # ------------------------------------------------------------ swaps
    def swap_qms_to_usdt(self, amount_in, n, dry_run):
        quoted = self.router.functions.getAmountsOut(amount_in, [self.wqms, self.usdt]).call()[1]
        min_out = int(quoted * self.slip)
        log_load(f"Swap {n}: {self.w3.from_wei(amount_in, 'ether'):.5f} QMS -> USDT "
                 f"(~{quoted/1e6:.4f}, min {min_out/1e6:.4f})")
        if dry_run:
            print(f"  [DRY-RUN] swapExactETHForTokens value={self.w3.from_wei(amount_in, 'ether'):.5f} QMS")
            return True
        tx = self.router.functions.swapExactETHForTokens(
            min_out, [self.wqms, self.usdt], self.acct.address, self.deadline()
        ).build_transaction({"from": self.acct.address, "value": amount_in})
        return self.send_tx(tx, f"Swap {n} QMS->USDT") is not None

    def swap_usdt_to_qms(self, amount_in, n, dry_run):
        quoted = self.router.functions.getAmountsOut(amount_in, [self.usdt, self.wqms]).call()[1]
        min_out = int(quoted * self.slip)
        log_load(f"Swap {n}: {amount_in/1e6:.4f} USDT -> QMS "
                 f"(~{self.w3.from_wei(quoted, 'ether'):.5f}, min {self.w3.from_wei(min_out, 'ether'):.5f})")
        if dry_run:
            print("  [DRY-RUN] swapExactTokensForETH")
            return True
        self.ensure_approval(self.usdt_c, self.cfg["router"], amount_in, dry_run)
        tx = self.router.functions.swapExactTokensForETH(
            min_out, [self.usdt, self.wqms], self.acct.address, self.deadline()
        ).build_transaction({"from": self.acct.address})
        return self.send_tx(tx, f"Swap {n} USDT->QMS") is not None

    # ------------------------------------------------------------ liquidity
    def add_liquidity(self, dry_run):
        cc = self.cycle_cfg
        qms_amt = self.w3.to_wei(cc["liquidity_qms"], "ether")
        if self.qms_balance() < qms_amt + self.w3.to_wei(0.05, "ether"):
            log_error(f"QMS kurang untuk add liquidity ({cc['liquidity_qms']} dibutuhkan)")
            return False
        usdt_amt = self.router.functions.getAmountsOut(qms_amt, [self.wqms, self.usdt]).call()[1]
        if self.usdt_balance() < usdt_amt:
            log_warn(f"USDT kurang ({usdt_amt/1e6:.4f} dibutuhkan) — swap dulu atau kecilkan liquidity_qms")
            return False
        log_load(f"Add liquidity: {cc['liquidity_qms']} QMS + {usdt_amt/1e6:.4f} USDT")
        if dry_run:
            print("  [DRY-RUN] addLiquidityETH")
            return True
        self.ensure_approval(self.usdt_c, self.cfg["router"], usdt_amt, dry_run)
        tx = self.router.functions.addLiquidityETH(
            self.usdt, usdt_amt, int(usdt_amt * self.slip), int(qms_amt * self.slip),
            self.acct.address, self.deadline()
        ).build_transaction({"from": self.acct.address, "value": qms_amt})
        return self.send_tx(tx, "Add liquidity") is not None

    def remove_liquidity(self, dry_run):
        factory = self.w3.eth.contract(
            address=self.router.functions.factory().call(), abi=FACTORY_ABI)
        pair_addr = factory.functions.getPair(self.wqms, self.usdt).call()
        if int(pair_addr, 16) == 0:
            log_warn("Pair WQMS/USDT belum ada")
            return False
        pair = self.w3.eth.contract(address=pair_addr, abi=ERC20_ABI)
        lp = pair.functions.balanceOf(self.acct.address).call()
        if lp == 0:
            log_warn("Tidak ada LP token untuk withdraw")
            return False
        log_load(f"Remove liquidity: {lp} LP")
        if dry_run:
            print("  [DRY-RUN] removeLiquidityETH")
            return True
        self.ensure_approval(pair, self.cfg["router"], lp, dry_run)
        tx = self.router.functions.removeLiquidityETH(
            self.usdt, lp, 0, 0, self.acct.address, self.deadline()
        ).build_transaction({"from": self.acct.address})
        return self.send_tx(tx, "Remove liquidity") is not None

    # ------------------------------------------------------------ points
    def check_points(self):
        url = self.cfg.get("points_url", "")
        if not url:
            return
        try:
            r = requests.get(url.format(address=self.acct.address), timeout=15)
            log_info(f"Points: {r.text[:200]}")
        except Exception as e:
            log_warn(f"Gagal ambil points: {e}")

    # ------------------------------------------------------------ cycle
    def run_cycle(self, num, dry_run):
        cc = self.cycle_cfg
        log_step(f"--- Cycle {num} | {self.acct.address} ---")
        q0 = self.w3.from_wei(self.qms_balance(), "ether")
        u0 = self.usdt_balance() / 1e6
        log_info(f"Saldo awal: {q0:.4f} QMS, {u0:.4f} USDT")

        ok_swaps = 0
        n = cc["swaps_per_cycle"]
        for i in range(1, n + 1):
            if i % 2 == 1:  # ganjil: QMS -> USDT
                amt = self.w3.to_wei(random.uniform(cc["min_swap_qms"], cc["max_swap_qms"]), "ether")
                reserve = self.w3.to_wei(0.05, "ether")
                if not dry_run and self.qms_balance() < amt + reserve:
                    log_warn(f"Swap {i}/{n} dilewati: QMS kurang")
                    continue
                if self.swap_qms_to_usdt(amt, f"{i}/{n}", dry_run):
                    ok_swaps += 1
            else:  # genap: USDT -> QMS
                bal = self.usdt_balance()
                if dry_run:
                    bal = 10**6  # dummy 1 USDT
                amt = min(bal, int(bal * random.uniform(0.25, 0.5)))
                if amt < 10**4:  # < 0.01 USDT
                    log_warn(f"Swap {i}/{n} dilewati: USDT kurang")
                    continue
                if self.swap_usdt_to_qms(amt, f"{i}/{n}", dry_run):
                    ok_swaps += 1
            time.sleep(random.uniform(1, 3))

        if cc.get("add_liquidity", True):
            time.sleep(2)
            if self.add_liquidity(dry_run):
                time.sleep(2)
                self.remove_liquidity(dry_run)

        self.check_points()
        q1 = self.w3.from_wei(self.qms_balance(), "ether")
        u1 = self.usdt_balance() / 1e6
        log_info(f"Cycle {num} selesai: {ok_swaps}/{n} swap OK | Saldo: {q1:.4f} QMS, {u1:.4f} USDT")
        print()


# ------------------------------------------------------------------ main
def countdown_24h():
    total = 24 * 60 * 60
    end = time.time() + total
    while time.time() < end:
        rem = int(end - time.time())
        h, rem = divmod(rem, 3600)
        m, s = divmod(rem, 60)
        print(f"\r{C['cyan']}[⏰] Eksekusi berikutnya dalam: {h:02d}:{m:02d}:{s:02d}{C['reset']}", end="", flush=True)
        time.sleep(1)
    print()


def prompt_cycles():
    while True:
        try:
            v = input("Masukkan jumlah cycle yang dijalankan: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if v.isdigit() and int(v) > 0:
            return int(v)
        log_error("Masukkan angka positif.")


def main():
    ap = argparse.ArgumentParser(description="Qwap Testnet Auto Bot")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rounds", type=int, default=0, help="jumlah cycle per wallet (0 = prompt interaktif)")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop-24h", action="store_true", help="ulangi cycle tiap 24 jam")
    args = ap.parse_args()

    banner()
    cfg = load_config()
    w3 = Web3(Web3.HTTPProvider(cfg["rpc"], request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        sys.exit("RPC tidak terhubung: " + cfg["rpc"])
    if w3.eth.chain_id != cfg["chain_id"]:
        sys.exit(f"CHAIN ID SALAH ({w3.eth.chain_id}) — hanya QMS Testnet 19480.")
    log_info(f"Tersambung: chain {w3.eth.chain_id} (QMS Testnet), block {w3.eth.block_number}")

    wallets = load_wallets()
    log_info(f"{len(wallets)} wallet dimuat")

    if args.once:
        rounds = 1
    elif args.rounds:
        rounds = args.rounds
    elif sys.stdin.isatty() and not args.dry_run:
        rounds = prompt_cycles()
    else:
        rounds = 1 if args.dry_run else prompt_cycles()

    bots = [Bot(w3, a, cfg) for a in wallets]
    cycle = 0
    try:
        while True:
            cycle += 1
            for bi, bot in enumerate(bots):
                log_step(f"Wallet {bi+1}/{len(bots)}: {bot.acct.address}")
                try:
                    bot.run_cycle(cycle, args.dry_run)
                except Exception as e:
                    log_error(f"Cycle {cycle} wallet {bi+1} error: {e}")
                if bi < len(bots) - 1:
                    time.sleep(3)
            if args.dry_run or (not args.loop_24h and cycle >= rounds):
                break
            if args.loop_24h:
                log_ok("Siklus selesai. Menunggu 24 jam...")
                countdown_24h()
            else:
                cc = cfg["cycle"]
                d = random.uniform(cc["min_delay_s"], cc["max_delay_s"])
                log_info(f"Jeda {d:.0f} dtk sebelum cycle berikutnya...")
                time.sleep(d)
    except KeyboardInterrupt:
        print("\nBerhenti oleh pengguna.")
    log_ok(f"Selesai: {cycle} cycle.")


if __name__ == "__main__":
    main()
