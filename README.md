# Solana SPL Mint Anomaly & Rug-Pull Radar Scorer (`<=8 KB`)

Standalone, zero-dependency Python 3.12 heuristic & streaming scorer for newly initialized Solana SPL mints and DEX pools within the first **15 blocks** of launch (`t=18`).

- **`scorer.py`**: `7,999` bytes LF (`<= 8,000` bytes), Python 3.12 stdlib only
- **Dual Ingestion**: Single-shot `score_launch(event)` + stateful 15-block event stream `SPLRugRadar().ingest(ev)` (`mint_init`, `pool_create`, `holder_snapshot`, `swap`)
- **Signals**: Mint/freeze authority, Token-2022 (`permanent_delegate`, `transfer_hook_active`, `transfer_fee_bps`), burn/LP-excluded Top-10 Gini & HHI, LP burn/lock duration ramp, micro-liquidity/FDV trap, Jito slot-0/1 bundler, shared funder-graph clustering, uniform buy-size CV, wash round-tripping, and early dev dump.

## Quick Run
```bash
# Built-in self-test
python3 scorer.py --selftest

# Full 21-case unit test suite
python3 test_scorer.py

# Deterministic 400-launch / 7-regime benchmark
python3 backtest.py
```

## Verified Benchmark (`N=400`, 7 Regimes)
- **Unit Tests:** `21 / 21` PASS (`0.189s`)
- **Latency:** `0.140 ms / launch`
- **ROC-AUC:** `1.0000` | **Brier Score:** `0.0108` (`BSS = 0.9567`) | **ECE (10-bin):** `0.0692` | **F1:** `0.9975` (`TP=199, FP=0, TN=200, FN=1`)
- **Hard Traps:** `jito_bundler_cabal` (`mean_rug_prob=0.8957`) vs `sniped_legit_trap` (`mean_rug_prob=0.0387`, `mean_momentum_prob=0.9214`)

## SHA-256 Checksums
- `scorer.py`: `a6e0612a7d5b92ac380d5fdbcb045c7bd2ef17a13cb3fc9c2f1553de08cea87b`
- `backtest.py`: `55c631aa7f5262ec96c461688c487ea3322a4aef91e706f66af484f6167845fe`
- `test_scorer.py`: `e2741b25a26a3581d97bd73f065f97b9c1af5d6c927040527d30e4e437deee0b`
