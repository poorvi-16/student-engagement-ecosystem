"""A/B testing for nudge copy: balanced exploration first, then mostly the best variant with a little exploration.

Pure and deterministic: the variant for a (student, nudge) pair is a hash of their ids, so a student always sees the same
copy and refreshing never flips it. `stats` maps variant -> (exposures, clicks).
"""

import hashlib
import math

VARIANTS = ("A", "B")  # A = control copy, B = benefit-led copy
MIN_EXPOSURES = 20  # per variant before the best one is favoured
EXPLORE = 0.2  # share of students who still get a random variant afterwards


def _unit(seed: str) -> float:
    return int(hashlib.md5(seed.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def smoothed_ctr(exposures: int, clicks: int) -> float:
    return (clicks + 1) / (exposures + 2)


def best(stats: dict[str, tuple[int, int]]) -> str:
    return max(VARIANTS, key=lambda v: (smoothed_ctr(*stats.get(v, (0, 0))), v == "A"))


def choose(stats: dict[str, tuple[int, int]], seed: str) -> str:
    h = _unit(seed)
    if any(stats.get(v, (0, 0))[0] < MIN_EXPOSURES for v in VARIANTS):
        return VARIANTS[int(h * len(VARIANTS)) % len(VARIANTS)]  # even split while we have little data
    if h < EXPLORE:
        return VARIANTS[int(h / EXPLORE * len(VARIANTS)) % len(VARIANTS)]
    return best(stats)


def compare(stats: dict[str, tuple[int, int]]) -> dict:
    """Readout for the admin console: CTR per variant, the leader, and a two-proportion z-test (95%)."""
    rows = {v: {"exposures": stats.get(v, (0, 0))[0], "clicks": stats.get(v, (0, 0))[1]} for v in VARIANTS}
    for r in rows.values():
        r["ctr"] = round(r["clicks"] / r["exposures"], 4) if r["exposures"] else 0.0
    (na, ca), (nb, cb) = (rows["A"]["exposures"], rows["A"]["clicks"]), (rows["B"]["exposures"], rows["B"]["clicks"])
    z = 0.0
    if na and nb:
        pooled = (ca + cb) / (na + nb)
        se = math.sqrt(pooled * (1 - pooled) * (1 / na + 1 / nb))
        z = (cb / nb - ca / na) / se if se else 0.0
    leader = best(stats)
    lift = (rows["B"]["ctr"] / rows["A"]["ctr"] - 1) if rows["A"]["ctr"] else None
    return {"variants": rows, "leader": leader, "z": round(z, 2), "significant": abs(z) >= 1.96,
            "lift_b_vs_a": round(lift, 3) if lift is not None else None}
