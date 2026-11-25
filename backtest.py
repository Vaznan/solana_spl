#!/usr/bin/env python3
"""Deterministic 400-launch noisy benchmark & calibration report for scorer.py."""
from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any

from scorer import score_launch


def _make_launch(rng: random.Random, regime: str, idx: int) -> tuple[dict[str, Any], int]:
    """Generate realistic synthetic SPL launches across 7 regimes (including hard overlapping cases)."""
    s0 = 310_000_000 + idx * 100
    trades: list[dict[str, Any]] = []

    if regime == "organic_breakout":
        label = 0
        for i in range(rng.randint(24, 50)):
            trades.append({
                "slot": s0 + (rng.randint(0, 1) if i < 2 else rng.randint(2, 15)),
                "side": "buy", "wallet": f"org_{idx}_{i}", "funder": f"cex_{idx}_{i}",
                "sol_amount": round(rng.uniform(0.15, 6.5), 3), "jito_bundle": False,
            })
        for i in range(rng.randint(2, 6)):
            trades.append({"slot": s0 + rng.randint(6, 15), "side": "sell",
                           "wallet": f"tp_{idx}_{i}", "sol_amount": round(rng.uniform(0.1, 1.4), 3)})
        holders = [{"pct": round(rng.uniform(0.012, 0.042), 4)} for _ in range(10)]
        holders.append({"pct": 0.42, "address": "11111111111111111111111111111111"})
        return {
            "mint": f"Org{idx:04d}", "launch_slot": s0,
            "mint_authority_active": False, "freeze_authority_active": False,
            "metadata_mutable": rng.random() < 0.15,
            "lp_burned_pct": round(rng.uniform(0.85, 1.0), 3),
            "initial_liquidity_sol": round(rng.uniform(35.0, 150.0), 2),
            "fdv_sol": round(rng.uniform(300.0, 1200.0), 1),
            "dev_sold_pct": 0.0, "top_holders": holders, "trades": trades,
        }, label

    if regime == "modest_organic":
        label = 0
        for i in range(rng.randint(12, 24)):
            trades.append({
                "slot": s0 + rng.randint(1, 15), "side": "buy",
                "wallet": f"mod_{idx}_{i}", "funder": f"mf_{idx}_{i}",
                "sol_amount": round(rng.uniform(0.1, 3.0), 3), "jito_bundle": i < 2,
            })
        holders = [{"pct": round(rng.uniform(0.02, 0.055), 4)} for _ in range(10)]
        return {
            "mint": f"Mod{idx:04d}", "launch_slot": s0,
            "mint_authority_active": False, "freeze_authority_active": False,
            "lp_burned_pct": 0.0, "lp_locked_pct": round(rng.uniform(0.80, 1.0), 3),
            "lp_lock_days": rng.randint(60, 180),
            "initial_liquidity_sol": round(rng.uniform(18.0, 45.0), 2),
            "dev_sold_pct": round(rng.uniform(0.0, 0.08), 3),
            "top_holders": holders, "trades": trades,
        }, label

    if regime == "sniped_legit_trap":
        # Hard negative: legit dev burned LP + revoked auth, but 3rd-party MEV bots sniped slot 0-1
        label = 0
        for i in range(6):
            trades.append({
                "slot": s0 + (0 if i < 3 else 1), "side": "buy",
                "wallet": f"mev_{idx}_{i}", "funder": f"mev_f_{idx}_{i}",  # distinct funders
                "sol_amount": round(rng.uniform(0.2, 4.0), 3), "jito_bundle": True,
            })
        for i in range(rng.randint(18, 30)):
            trades.append({
                "slot": s0 + rng.randint(2, 15), "side": "buy",
                "wallet": f"real_{idx}_{i}", "funder": f"real_f_{idx}_{i}",
                "sol_amount": round(rng.uniform(0.15, 2.8), 3), "jito_bundle": False,
            })
        holders = [{"pct": round(rng.uniform(0.015, 0.045), 4)} for _ in range(10)]
        return {
            "mint": f"SnipedLegit{idx:04d}", "launch_slot": s0,
            "mint_authority_active": False, "freeze_authority_active": False,
            "lp_burned_pct": 1.0, "initial_liquidity_sol": round(rng.uniform(35.0, 80.0), 2),
            "dev_sold_pct": 0.0, "top_holders": holders, "trades": trades,
        }, label

    if regime == "authority_rug":
        label = 1
        for i in range(rng.randint(6, 18)):
            trades.append({
                "slot": s0 + rng.randint(0, 12), "side": "buy",
                "wallet": f"vic_{idx}_{i}", "funder": f"vf_{idx}_{i}",
                "sol_amount": round(rng.uniform(0.2, 2.0), 3), "jito_bundle": i < 3,
            })
        holders = [{"pct": round(rng.uniform(0.15, 0.35), 4)}] + [{"pct": round(rng.uniform(0.02, 0.07), 4)} for _ in range(9)]
        return {
            "mint": f"AuthRug{idx:04d}", "launch_slot": s0,
            "mint_authority_active": True, "freeze_authority_active": rng.random() < 0.75,
            "metadata_mutable": True, "lp_burned_pct": round(rng.uniform(0.0, 0.2), 3),
            "initial_liquidity_sol": round(rng.uniform(3.0, 18.0), 2),
            "dev_sold_pct": round(rng.uniform(0.0, 0.35), 3),
            "top_holders": holders, "trades": trades,
        }, label

    if regime == "jito_bundler_cabal":
        # Hard positive: authorities revoked + LP burned, but coordinated Jito cabal funded by 1-2 masters
        label = 1
        n_cabal = rng.randint(12, 22)
        for i in range(n_cabal):
            trades.append({
                "slot": s0 + (0 if i < int(n_cabal * 0.75) else 1), "side": "buy",
                "wallet": f"cab_{idx}_{i}", "funder": f"master_{idx}_{i % 2}",
                "sol_amount": round(rng.uniform(1.45, 1.55), 3),
                "jito_bundle": True, "jito_tip_lamports": 1_000_000,
            })
        for i in range(rng.randint(2, 6)):
            trades.append({
                "slot": s0 + rng.randint(4, 14), "side": "buy",
                "wallet": f"ret_{idx}_{i}", "funder": f"rf_{idx}_{i}",
                "sol_amount": round(rng.uniform(0.1, 1.0), 3), "jito_bundle": False,
            })
        for i in range(rng.randint(4, 10)):
            trades.append({
                "slot": s0 + rng.randint(8, 15), "side": "sell",
                "wallet": f"cab_{idx}_{i}", "sol_amount": round(rng.uniform(1.2, 2.5), 3),
            })
        holders = [{"pct": round(rng.uniform(0.055, 0.095), 4)} for _ in range(10)]
        return {
            "mint": f"CabRug{idx:04d}", "launch_slot": s0,
            "mint_authority_active": False, "freeze_authority_active": False,
            "lp_burned_pct": round(rng.uniform(0.75, 1.0), 3),
            "initial_liquidity_sol": round(rng.uniform(12.0, 30.0), 2),
            "dev_sold_pct": round(rng.uniform(0.35, 0.9), 3),
            "top_holders": holders, "trades": trades,
        }, label

    if regime == "token2022_stealth_rug":
        label = 1
        for i in range(rng.randint(10, 20)):
            trades.append({
                "slot": s0 + rng.randint(1, 14), "side": "buy",
                "wallet": f"t22_{idx}_{i}", "funder": f"tf_{idx}_{i}",
                "sol_amount": round(rng.uniform(0.2, 2.5), 3),
            })
        holders = [{"pct": round(rng.uniform(0.03, 0.06), 4)} for _ in range(10)]
        return {
            "mint": f"T22Rug{idx:04d}", "launch_slot": s0,
            "mint_authority_active": False, "freeze_authority_active": False,
            "permanent_delegate": rng.random() < 0.7,
            "transfer_fee_bps": rng.choice([800, 1200, 2500]),
            "transfer_hook_active": True,
            "lp_burned_pct": 0.9, "initial_liquidity_sol": round(rng.uniform(15.0, 35.0), 2),
            "top_holders": holders, "trades": trades,
        }, label

    # unlocked_lp_drain
    label = 1
    for i in range(rng.randint(8, 16)):
        trades.append({
            "slot": s0 + rng.randint(1, 12), "side": "buy",
            "wallet": f"u_{idx}_{i}", "funder": f"uf_{idx}_{i}",
            "sol_amount": round(rng.uniform(0.2, 1.8), 3),
        })
    holders = [{"pct": round(rng.uniform(0.10, 0.22), 4)}] + [{"pct": round(rng.uniform(0.03, 0.06), 4)} for _ in range(9)]
    return {
        "mint": f"LPRug{idx:04d}", "launch_slot": s0,
        "mint_authority_active": False, "freeze_authority_active": False,
        "lp_burned_pct": 0.0, "lp_locked_pct": round(rng.uniform(0.0, 0.15), 3),
        "lp_lock_days": 3, "initial_liquidity_sol": round(rng.uniform(2.0, 9.0), 2),
        "fdv_sol": round(rng.uniform(500.0, 2000.0), 1),
        "dev_sold_pct": round(rng.uniform(0.3, 0.8), 3),
        "top_holders": holders, "trades": trades,
    }, label


def roc_auc(labels: list[int], scores: list[float]) -> float:
    pairs = sorted(zip(scores, labels), key=lambda x: x[0])
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.0
    rank_sum = sum(i for i, (_, y) in enumerate(pairs, start=1) if y == 1)
    return (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def ece_10(labels: list[int], probs: list[float]) -> float:
    n = len(labels)
    ece = 0.0
    for b in range(10):
        lo, hi = b / 10.0, (b + 1) / 10.0
        idxs = [i for i, p in enumerate(probs) if (lo <= p < hi) or (b == 9 and p == 1.0)]
        if not idxs:
            continue
        acc = sum(labels[i] for i in idxs) / len(idxs)
        conf = sum(probs[i] for i in idxs) / len(idxs)
        ece += (len(idxs) / n) * abs(acc - conf)
    return ece


def main() -> int:
    rng = random.Random(20261125)
    regimes = (
        ["organic_breakout"] * 80
        + ["modest_organic"] * 65
        + ["sniped_legit_trap"] * 55
        + ["authority_rug"] * 55
        + ["jito_bundler_cabal"] * 55
        + ["token2022_stealth_rug"] * 45
        + ["unlocked_lp_drain"] * 45
    )
    rng.shuffle(regimes)

    labels, rug_probs, mom_probs = [], [], []
    by_reg: dict[str, list[tuple[float, float]]] = {}

    t0 = time.perf_counter()
    for i, reg in enumerate(regimes):
        ev, y = _make_launch(rng, reg, i)
        res = score_launch(ev)
        labels.append(y)
        rug_probs.append(res["rug_prob"])
        mom_probs.append(res["momentum_prob"])
        by_reg.setdefault(reg, []).append((res["rug_prob"], res["momentum_prob"]))
    ms = (time.perf_counter() - t0) * 1000.0

    brier = sum((p - y) ** 2 for p, y in zip(rug_probs, labels)) / len(labels)
    base_rate = sum(labels) / len(labels)
    brier_ref = base_rate * (1.0 - base_rate)
    bss = 1.0 - brier / max(brier_ref, 1e-9)
    auc = roc_auc(labels, rug_probs)
    ece = ece_10(labels, rug_probs)
    tp = sum(1 for p, y in zip(rug_probs, labels) if p >= 0.5 and y == 1)
    fp = sum(1 for p, y in zip(rug_probs, labels) if p >= 0.5 and y == 0)
    fn = sum(1 for p, y in zip(rug_probs, labels) if p < 0.5 and y == 1)
    tn = sum(1 for p, y in zip(rug_probs, labels) if p < 0.5 and y == 0)
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)

    raw_bytes = Path(__file__).with_name("scorer.py").read_bytes()
    lf_bytes = len(raw_bytes.replace(b"\r\n", b"\n"))

    print(f"=== SPL Mint Anomaly & Rug-Pull Radar Backtest (N={len(labels)}, 7 Regimes) ===")
    print(f"scorer.py size : {lf_bytes} B (LF) / {len(raw_bytes)} B (raw) | limit <= 8000 B -> {'PASS' if lf_bytes <= 8000 else 'FAIL'}")
    print(f"Runtime        : {ms:.2f} ms total ({ms / len(labels):.3f} ms/launch)")
    print(f"ROC-AUC        : {auc:.4f}")
    print(f"Brier Score    : {brier:.4f} (Brier Skill Score: {bss:.4f})")
    print(f"ECE (10-bin)   : {ece:.4f}")
    print(f"Precision/Rec  : P={prec:.4f} | R={rec:.4f} | F1={f1:.4f} (TP={tp}, FP={fp}, TN={tn}, FN={fn})")
    print("\nPer-Regime Mean Probabilities:")
    for reg, vals in sorted(by_reg.items()):
        mr = sum(v[0] for v in vals) / len(vals)
        mm = sum(v[1] for v in vals) / len(vals)
        print(f"  - {reg:<22} (n={len(vals):2d}) | mean_rug_prob={mr:.4f} | mean_momentum_prob={mm:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
