#!/usr/bin/env python3
"""<8KB Solana SPL Mint & DEX Rug-Pull Radar Scorer (<=15 blocks, Python 3.12 stdlib)."""
import json, math, sys
from collections import Counter

MAX_BLOCKS = 15
BURNS = frozenset({"1" * 32, "1nc1nerator" + "1" * 32, "dead" * 11})
SKIP = "lp pool amm burn dead vault raydium meteora orca pump".split()
AUTH_K = "mint_authority_active mint_authority freeze_authority_active freeze_authority".split()
LP_K = "lp_burned_pct lp_locked_pct initial_liquidity_sol liquidity_sol".split()

def _c(v, lo=0., hi=1.): return lo if v < lo else (hi if v > hi else v)
def _f(v): return float(v or 0.)
def _sig(z): return 1 / (1 + math.exp(-min(z, 60))) if z >= 0 else (e := math.exp(max(z, -60))) / (1 + e)
def _pct(v): x = _f(v); return _c(x / 100 if x > 1 else x)
def _amt(t): return _f(t.get("sol_amount", t.get("amount_sol", 0)))
def _wal(t, i): return str(t.get("wallet") or t.get("trader") or i)

def compute_gini(values):
  xs = sorted(max(0., float(v)) for v in values if v is not None and float(v) >= 0)
  n, tot = len(xs), sum(xs)
  return (1. if n == 1 and tot > 0 else 0.) if n < 2 or tot <= 0 else _c(sum((2 * i - n + 1) * x for i, x in enumerate(xs)) / (n * tot))

def _holders(ev):
  out = []
  for h in ev.get("top_holders") or ev.get("holders") or []:
    if isinstance(h, dict):
      a = str(h.get("address") or h.get("owner") or "").strip().lower()
      tg = str(h.get("tag") or h.get("label") or "").lower()
      if h.get("is_lp") or h.get("is_burn") or a in BURNS or any(k in tg for k in SKIP): continue
      p = _pct(h.get("pct", h.get("share", 0)))
    else: p = _pct(h)
    if p > 0: out.append(p)
  if not out: return .5, 0., 0., 0., False
  out.sort(reverse=True); t = out[:10]
  return compute_gini(t), _c(t[0]), _c(sum(t)), _c(sum(p * p for p in t)), True

def _bundles(ev):
  s0 = int(ev.get("launch_slot", ev.get("pool_slot", 0)) or 0)
  ts = ev.get("trades") or ev.get("swaps") or []
  w = [(d, t) for t in ts if 0 <= (d := int(t.get("slot", s0) or s0) - s0) <= MAX_BLOCKS]
  bs = [(d, t) for d, t in w if str(t.get("side", "buy")).lower() == "buy"]
  ss = [(d, t) for d, t in w if str(t.get("side", "")).lower() == "sell"]
  if not bs: return (0., 0., 0., 0., 1. if ss else 0., 0., 0.), bool(ts)
  nb = len(bs)
  s0_r = _c(sum(d == 0 for d, _ in bs) / nb)
  bun_r = _c(sum(bool(d <= 1 or t.get("jito_bundle") or t.get("bundle_id") or _f(t.get("jito_tip_lamports")) > 0) for d, t in bs) / nb)
  fs = [str(t["funder"]) for _, t in bs if t.get("funder")]
  fm = Counter(fs)
  fc = _c(sum(c for c in fm.values() if c > 1) / len(fs)) if len(fs) > 1 else _c(_f(ev.get("funder_cluster_ratio")))
  pos = [a for _, t in bs if (a := _amt(t)) > 0]
  uni = _c((.25 - math.sqrt(sum((a - (mu := sum(pos) / len(pos))) ** 2 for a in pos) / len(pos)) / mu) / .25) if len(pos) > 3 and sum(pos) > 0 else 0.
  sp = _c(sum(_amt(t) for _, t in ss) / (sum(pos) + 1e-9))
  bset, sset = {_wal(t, i) for i, (_, t) in enumerate(bs)}, {_wal(t, "") for _, t in ss} - {""}
  sh = {f for f, c in fm.items() if c > 1}
  org = {_wal(t, i) for i, (d, t) in enumerate(bs) if d > 1 and not t.get("jito_bundle") and not t.get("bundle_id") and str(t.get("funder") or "") not in sh}
  return (s0_r, bun_r, fc, uni, sp, float(len(org)), _c(len(bset & sset) / max(len(bset), 1))), True

def score_launch(event):
  """Score SPL launch (<=15 blocks) -> calibrated [0..1] rug & momentum probs."""
  g = event.get
  ma, fa = bool(g("mint_authority_active", g("mint_authority") is not None)), bool(g("freeze_authority_active", g("freeze_authority") is not None))
  fee, liq, fdv, dev_s = _f(g("transfer_fee_bps")), _f(g("initial_liquidity_sol", g("liquidity_sol"))), _f(g("fdv_sol")), _pct(g("dev_sold_pct"))
  lp_sec = _c(_pct(g("lp_burned_pct")) + _pct(g("lp_locked_pct")) * (.3 + .7 * _c(_f(g("lp_lock_days")) / 90)))
  lfdv = (liq / fdv) if fdv > 0 else .15
  gini, top1, top10, hhi, has_h = _holders(event)
  (s0_r, bun_r, fc, uni, sp, org, wash), has_t = _bundles(event)
  z, rs = -2.15, []
  def add(w, tag):
    nonlocal z; z += w
    if abs(w) >= .3: rs.append((w, tag))
  if ma: add(2.35, "mint_authority_active")
  if fa: add(2.6, "freeze_authority_active")
  if g("permanent_delegate"): add(3.25, "token2022_permanent_delegate")
  if g("transfer_hook_active"): add(.9, "token2022_transfer_hook")
  if g("metadata_mutable"): add(.35, "mutable_metadata")
  if fee > 150: add(_c((fee - 150) / 500, 0, 2.2), f"high_transfer_fee_{int(fee)}bps")
  add(2.45 * (1 - lp_sec), "unsecured_lp" if lp_sec < .6 else "lp_secured")
  if liq < 10: add(1.05 * (1 - _c(liq / 10)), "thin_initial_liquidity")
  elif liq >= 40: add(-.35, "deep_initial_liquidity")
  if fdv > 0 and lfdv < .03: add(.95 * _c((.03 - lfdv) / .03), "micro_liq_to_fdv_trap")
  add(1.85 * max(0, gini - .35), "high_top10_gini")
  add(2.1 * max(0, top10 - .3), "top10_concentration")
  if top1 > .12: add(1.65 * _c((top1 - .12) / .25), "dominant_top1_holder")
  if dev_s > .15: add(1.9 * dev_s, "dev_early_dump")
  bs = .35 * bun_r + .2 * s0_r + .3 * fc + .15 * uni
  add(3.85 * max(0, bs - .15), "slot_bundler_cluster")
  add(1.3 * max(0, sp - .4), "early_sell_pressure")
  add(.85 * max(0, wash - .25), "wash_round_tripping")
  org_n = _c(org / 25); add(-.85 * org_n, "organic_buyer_growth")
  rp = round(_sig(z), 4)
  mp = round(_c(_sig(-1.1 + 2.35 * org_n + 1.3 * lp_sec + .65 * _c(liq / 50) - 2.8 * rp - .9 * sp - .85 * bs) * (1 - .55 * rp)), 4)
  tier = "CRITICAL_RUG" if rp >= .75 else "ELEVATED_RUG" if rp >= .45 else "STRONG_MOMENTUM" if mp >= .55 else "WATCH"
  rs.sort(key=lambda x: abs(x[0]), reverse=True)
  r4 = lambda v: round(v, 4)
  cov = (any(k in event for k in AUTH_K) + any(k in event for k in LP_K) + has_h + has_t) / 4
  return {
    "mint": g("mint", "unknown"), "rug_prob": rp, "momentum_prob": mp, "risk_tier": tier, "signal_coverage": round(cov, 2),
    "metrics": {"top10_gini": r4(gini), "top1_share": r4(top1), "top10_share": r4(top10), "top10_hhi": r4(hhi), "lp_secured_ratio": r4(lp_sec), "slot0_ratio": r4(s0_r), "bundle_ratio": r4(bun_r), "funder_cluster_ratio": r4(fc), "uniform_buy_score": r4(uni), "organic_buyers_15b": int(org)},
    "top_factors": [{"factor": k, "delta_logit": round(w, 3)} for w, k in rs[:5]],
  }

class SPLRugRadar:
  """Stateful 15-block stream ingester."""
  def __init__(self): self.state = {}
  def ingest(self, ev):
    m = str(ev.get("mint") or "unknown")
    st = self.state.setdefault(m, {"mint": m, "trades": [], "top_holders": []})
    k = str(ev.get("type", "")).lower()
    if k in ("swap", "trade"): st["trades"].append(ev)
    elif k == "holder_snapshot": st["top_holders"] = ev.get("top_holders", ev.get("holders", []))
    else:
      for a, v in ev.items():
        if a == "trades" and isinstance(v, list): st["trades"].extend(v)
        elif a != "type": st[a] = v
    return score_launch(st)

def main():
  if "--selftest" in sys.argv:
    rg = score_launch({"mint": "GoodSPL", "launch_slot": 100, "mint_authority_active": 0, "freeze_authority_active": 0, "lp_burned_pct": 1, "liquidity_sol": 55, "holders": [.025] * 10, "swaps": [{"slot": 102 + i % 12, "wallet": f"w{i}", "funder": f"f{i}", "sol_amount": .4 + i % 5 * .5} for i in range(26)]})
    rb = score_launch({"mint": "RugSPL", "launch_slot": 100, "mint_authority_active": 1, "freeze_authority_active": 1, "lp_burned_pct": 0, "liquidity_sol": 3, "holders": [.35, .15], "swaps": [{"slot": 100, "wallet": f"b{i}", "funder": "c", "sol_amount": 1.5, "jito_bundle": 1} for i in range(12)]})
    assert rg["rug_prob"] < .2 and rg["momentum_prob"] > .6 and rb["rug_prob"] > .9
    print(json.dumps({"selftest": "PASS", "good": rg, "bad": rb}, indent=2)); return 0
  d = json.load(sys.stdin)
  if isinstance(d, list) and d and isinstance(d[0], dict) and "type" in d[0]:
    r = SPLRugRadar(); o = [r.ingest(e) for e in d][-1]
  else: o = [score_launch(e) for e in d] if isinstance(d, list) else score_launch(d)
  print(json.dumps(o, indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
