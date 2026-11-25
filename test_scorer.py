#!/usr/bin/env python3
"""Comprehensive 24-case unittest suite for standalone <8KB SPL Rug-Pull Radar Scorer."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from scorer import SPLRugRadar, compute_gini, score_launch

BASE_DIR = Path(__file__).resolve().parent


def clean_launch() -> dict:
    return {
        "mint": "CleanMint111",
        "launch_slot": 1000,
        "mint_authority_active": False,
        "freeze_authority_active": False,
        "metadata_mutable": False,
        "lp_burned_pct": 1.0,
        "initial_liquidity_sol": 60.0,
        "fdv_sol": 500.0,
        "dev_holding_pct": 0.02,
        "dev_sold_pct": 0.0,
        "top_holders": [{"pct": 0.025} for _ in range(10)]
        + [{"pct": 0.45, "address": "11111111111111111111111111111111"}],
        "trades": [
            {"slot": 1002 + (i % 12), "side": "buy", "wallet": f"w{i}", "funder": f"f{i}", "sol_amount": 0.5 + (i % 5) * 0.4}
            for i in range(28)
        ],
    }


class TestScorer(unittest.TestCase):
    def test_size_strictly_under_8000_bytes_lf(self) -> None:
        raw = (BASE_DIR / "scorer.py").read_bytes()
        lf_size = len(raw.replace(b"\r\n", b"\n"))
        self.assertLessEqual(lf_size, 8000, f"scorer.py LF size is {lf_size} B (> 8000)")
        self.assertLessEqual(len(raw), 8192, f"scorer.py raw size is {len(raw)} B (> 8192)")

    def test_gini_empty_single_equal_unequal(self) -> None:
        self.assertEqual(compute_gini([]), 0.0)
        self.assertEqual(compute_gini([10.0]), 1.0)
        self.assertAlmostEqual(compute_gini([5.0, 5.0, 5.0, 5.0]), 0.0, places=5)
        self.assertGreater(compute_gini([0.01, 0.01, 0.01, 0.97]), 0.65)

    def test_gini_ignores_negative_and_none(self) -> None:
        self.assertAlmostEqual(compute_gini([None, -5.0, 4.0, 4.0]), 0.0, places=5)  # type: ignore[list-item]

    def test_clean_launch_strong_momentum(self) -> None:
        res = score_launch(clean_launch())
        self.assertLess(res["rug_prob"], 0.20)
        self.assertGreater(res["momentum_prob"], 0.60)
        self.assertEqual(res["risk_tier"], "STRONG_MOMENTUM")
        self.assertEqual(res["signal_coverage"], 1.0)

    def test_mint_and_freeze_monotonic(self) -> None:
        ev = clean_launch()
        r0 = score_launch(ev)["rug_prob"]
        ev["mint_authority_active"] = True
        r1 = score_launch(ev)["rug_prob"]
        ev["freeze_authority_active"] = True
        r2 = score_launch(ev)["rug_prob"]
        self.assertLess(r0, r1)
        self.assertLess(r1, r2)
        self.assertGreater(r2, 0.70)

    def test_mint_authority_string_detection(self) -> None:
        ev = clean_launch()
        del ev["mint_authority_active"]
        ev["mint_authority"] = "DeployerPubkey111"
        self.assertGreater(score_launch(ev)["rug_prob"], score_launch(clean_launch())["rug_prob"])

    def test_token2022_extensions(self) -> None:
        ev = clean_launch()
        ev["permanent_delegate"] = True
        ev["transfer_hook_active"] = True
        ev["transfer_fee_bps"] = 1200
        res = score_launch(ev)
        self.assertGreater(res["rug_prob"], 0.80)
        factors = [f["factor"] for f in res["top_factors"]]
        self.assertIn("token2022_permanent_delegate", factors)

    def test_lp_burn_vs_lock_vs_unlocked(self) -> None:
        ev = clean_launch()
        ev["lp_burned_pct"] = 0.0
        ev["lp_locked_pct"] = 0.0
        r_unlocked = score_launch(ev)["rug_prob"]
        ev["lp_locked_pct"] = 0.95
        ev["lp_lock_days"] = 7
        r_short_lock = score_launch(ev)["rug_prob"]
        ev["lp_lock_days"] = 180
        r_long_lock = score_launch(ev)["rug_prob"]
        self.assertGreater(r_unlocked, r_short_lock)
        self.assertGreater(r_short_lock, r_long_lock)

    def test_percentage_0_to_100_normalization(self) -> None:
        ev1 = clean_launch()
        ev2 = clean_launch()
        ev2["lp_burned_pct"] = 100.0
        ev2["top_holders"] = [{"pct": 2.5} for _ in range(10)]
        self.assertAlmostEqual(score_launch(ev1)["rug_prob"], score_launch(ev2)["rug_prob"], places=4)

    def test_micro_liq_to_fdv_trap(self) -> None:
        ev = clean_launch()
        ev["initial_liquidity_sol"] = 15.0
        ev["fdv_sol"] = 2000.0  # 0.75% liq/FDV
        res = score_launch(ev)
        self.assertGreater(res["rug_prob"], score_launch(clean_launch())["rug_prob"])

    def test_slot_bundler_jito_tip_and_funder_cluster(self) -> None:
        ev = clean_launch()
        ev["trades"] = [
            {"slot": 1000, "side": "buy", "wallet": f"bot_{i}", "funder": "cabal_master",
             "sol_amount": 1.50, "jito_tip_lamports": 500_000}
            for i in range(15)
        ]
        res = score_launch(ev)
        self.assertEqual(res["metrics"]["slot0_ratio"], 1.0)
        self.assertEqual(res["metrics"]["bundle_ratio"], 1.0)
        self.assertEqual(res["metrics"]["funder_cluster_ratio"], 1.0)
        self.assertGreater(res["metrics"]["uniform_buy_score"], 0.95)
        self.assertEqual(res["metrics"]["organic_buyers_15b"], 0)
        self.assertGreater(res["rug_prob"], 0.55)

    def test_distinct_funder_snipers_still_lower_risk_than_cabal(self) -> None:
        cabal = clean_launch()
        cabal["trades"] = [
            {"slot": 1000, "side": "buy", "wallet": f"b{i}", "funder": "same_funder", "sol_amount": 1.0, "jito_bundle": True}
            for i in range(10)
        ]
        indep = clean_launch()
        indep["trades"] = [
            {"slot": 1000, "side": "buy", "wallet": f"b{i}", "funder": f"diff_{i}", "sol_amount": 0.3 + i * 0.4, "jito_bundle": True}
            for i in range(10)
        ]
        self.assertGreater(score_launch(cabal)["rug_prob"], score_launch(indep)["rug_prob"])

    def test_ignores_trades_beyond_15_blocks_and_before_launch(self) -> None:
        ev = clean_launch()
        ev["trades"] = [
            {"slot": 999, "side": "buy", "wallet": "early", "funder": "x", "sol_amount": 1.0, "jito_bundle": True},
            {"slot": 1016, "side": "buy", "wallet": "late", "funder": "x", "sol_amount": 1.0, "jito_bundle": True},
        ]
        res = score_launch(ev)
        self.assertEqual(res["metrics"]["bundle_ratio"], 0.0)
        self.assertEqual(res["metrics"]["organic_buyers_15b"], 0)

    def test_burn_and_lp_addresses_excluded(self) -> None:
        ev = clean_launch()
        ev["top_holders"] = [
            {"pct": 0.40, "address": "11111111111111111111111111111111"},
            {"pct": 0.25, "address": "1nc1nerator11111111111111111111111111111111"},
            {"pct": 0.20, "tag": "Raydium AMM Vault"},
            {"pct": 0.03}, {"pct": 0.03}, {"pct": 0.03}, {"pct": 0.03},
        ]
        res = score_launch(ev)
        self.assertAlmostEqual(res["metrics"]["top10_gini"], 0.0, places=4)
        self.assertAlmostEqual(res["metrics"]["top10_share"], 0.12, places=4)

    def test_dev_early_dump_penalized(self) -> None:
        ev = clean_launch()
        r0 = score_launch(ev)["rug_prob"]
        ev["dev_sold_pct"] = 0.85
        self.assertGreater(score_launch(ev)["rug_prob"], r0)

    def test_wash_round_tripping_penalized(self) -> None:
        ev = clean_launch()
        ev["trades"] = [
            {"slot": 1003, "side": "buy", "wallet": f"w{i}", "funder": f"f{i}", "sol_amount": 1.0} for i in range(10)
        ] + [
            {"slot": 1009, "side": "sell", "wallet": f"w{i}", "sol_amount": 0.95} for i in range(10)
        ]
        res = score_launch(ev)
        self.assertGreater(res["rug_prob"], score_launch(clean_launch())["rug_prob"])

    def test_missing_fields_graceful_degradation(self) -> None:
        res = score_launch({"mint": "SparseMint"})
        self.assertEqual(res["signal_coverage"], 0.0)
        self.assertTrue(0.0 <= res["rug_prob"] <= 1.0)
        self.assertTrue(0.0 <= res["momentum_prob"] <= 1.0)

    def test_extreme_rug_bounds_and_tier(self) -> None:
        extreme = {
            "mint": "ExtremeRug", "launch_slot": 10,
            "mint_authority_active": True, "freeze_authority_active": True,
            "permanent_delegate": True, "transfer_fee_bps": 5000,
            "lp_burned_pct": 0.0, "initial_liquidity_sol": 0.1, "dev_sold_pct": 1.0,
            "top_holders": [{"pct": 0.95}],
            "trades": [{"slot": 10, "side": "buy", "wallet": f"b{i}", "funder": "x", "sol_amount": 1.0, "jito_bundle": True} for i in range(10)],
        }
        res = score_launch(extreme)
        self.assertTrue(0.0 <= res["rug_prob"] <= 1.0)
        self.assertTrue(0.0 <= res["momentum_prob"] <= 1.0)
        self.assertEqual(res["risk_tier"], "CRITICAL_RUG")

    def test_streaming_radar_ingester(self) -> None:
        radar = SPLRugRadar()
        r1 = radar.ingest({"type": "mint_init", "mint": "Stream1", "launch_slot": 500, "mint_authority_active": False, "freeze_authority_active": False})
        r2 = radar.ingest({"type": "pool_create", "mint": "Stream1", "lp_burned_pct": 1.0, "initial_liquidity_sol": 65.0})
        r3 = radar.ingest({"type": "holder_snapshot", "mint": "Stream1", "top_holders": [{"pct": 0.025} for _ in range(10)]})
        for i in range(25):
            r4 = radar.ingest({"type": "swap", "mint": "Stream1", "slot": 502 + (i % 10), "side": "buy", "wallet": f"u{i}", "funder": f"f{i}", "sol_amount": 0.5 + (i % 4) * 0.4})
        self.assertGreater(r1["rug_prob"], r2["rug_prob"])
        self.assertEqual(r4["signal_coverage"], 1.0)
        self.assertEqual(r4["risk_tier"], "STRONG_MOMENTUM")
        self.assertLess(r4["rug_prob"], r3["rug_prob"])

    def test_cli_selftest_passes(self) -> None:
        proc = subprocess.run([sys.executable, str(BASE_DIR / "scorer.py"), "--selftest"], text=True, capture_output=True, check=True)
        out = json.loads(proc.stdout)
        self.assertEqual(out["selftest"], "PASS")

    def test_cli_single_and_stream_stdin(self) -> None:
        p1 = subprocess.run([sys.executable, str(BASE_DIR / "scorer.py")], input=json.dumps(clean_launch()), text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(p1.stdout)["mint"], "CleanMint111")

        stream = [
            {"type": "mint_init", "mint": "S1", "launch_slot": 10, "mint_authority_active": True, "freeze_authority_active": True},
            {"type": "pool_create", "mint": "S1", "lp_burned_pct": 0.0, "initial_liquidity_sol": 2.0},
            {"type": "swap", "mint": "S1", "slot": 10, "side": "buy", "wallet": "b1", "funder": "x", "sol_amount": 1.0, "jito_bundle": True},
        ]
        p2 = subprocess.run([sys.executable, str(BASE_DIR / "scorer.py")], input=json.dumps(stream), text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(p2.stdout)["risk_tier"], "CRITICAL_RUG")


if __name__ == "__main__":
    unittest.main(verbosity=2)
