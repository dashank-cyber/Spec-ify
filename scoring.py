"""
scoring.py — Weighted scoring engine for Spec-ify.

Our seed data is real, hand-collected spec text (e.g. "8GB", "6000mAh",
"13th Gen Intel Core i5", "4/6GB"), not clean numeric columns. This module
first PARSES that text into comparable numbers, then NORMALIZES each
criterion to a 0-1 scale across the current result set, then applies the
user's weights to produce a final score (FR3, FR4, FR5, FR9 — no
criterion is hardcoded to favor a brand, only numeric spec strength).

Missing/unparseable specs are treated as the lowest value for that
criterion (0 after normalization) rather than excluded — a device with
unverified specs simply can't score well on a criterion it has no data
for, which is an honest reflection of "we don't know if this is good"
rather than skipping the device via a special case.
"""

import re

# --- crude tier tables for non-numeric specs -------------------------------
# These are simple heuristics, not a definitive performance benchmark —
# good enough for ranking within a mini-project's seed dataset.

_PROCESSOR_KEYWORDS = [
    # (regex pattern, score out of 10) — checked in order, first match wins
    (r"i9|ryzen\s*9|ultra\s*9|m5|apple\s*m5", 10),
    (r"i7|ryzen\s*7|ultra\s*7|snapdragon\s*8|dimensity\s*(8|9)|m4", 8.5),
    (r"i5|ryzen\s*5|ultra\s*5|snapdragon\s*7|dimensity\s*7", 7),
    (r"i3|ryzen\s*3|snapdragon\s*6|dimensity\s*6", 5),
    (r"celeron|dimensity\s*[1-5]\d{2}|a18", 3),
]

_GPU_KEYWORDS = [
    (r"rtx\s*50\d0|rtx\s*4090|rtx\s*4080", 10),
    (r"rtx\s*4070|rtx\s*4060|rtx\s*5060", 8.5),
    (r"rtx\s*4050|rtx\s*5050|rtx\s*3060", 7),
    (r"rtx\s*3050|rtx\s*2050|gtx", 5.5),
    (r"\d+gb dedicated", 5.5),
    (r"integrated", 2),
]


def _score_from_keywords(text, table, default=1.0):
    if not text:
        return default
    text_lower = text.lower()
    for pattern, score in table:
        if re.search(pattern, text_lower):
            return score
    return default


def _expand_slash_ranges(text, unit):
    """
    '4/6GB' -> '4GB 6GB' so each number in a slash-separated range picks
    up the trailing unit before we run the plain number+unit regex.
    Leaves normal text (no slash) untouched.
    """
    pattern = re.compile(
        r"(\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)+)\s*" + unit, re.IGNORECASE)

    def _replace(match):
        nums = re.split(r"\s*/\s*", match.group(1))
        return " ".join(f"{n}{unit}" for n in nums)

    return pattern.sub(_replace, text)


def parse_ram_gb(ram_text):
    """'8GB' -> 8.0 ; '4/6GB' -> 5.0 (average of range) ; None/unparseable -> None"""
    if not ram_text:
        return None
    expanded = _expand_slash_ranges(ram_text, "GB")
    nums = [float(n) for n in re.findall(r"(\d+(?:\.\d+)?)\s*GB", expanded, re.IGNORECASE)]
    if not nums:
        return None
    return sum(nums) / len(nums)


def parse_storage_gb(storage_text):
    """'128GB' -> 128.0 ; '1TB SSD' -> 1024.0 ; '128/256GB' -> 192.0 (avg)"""
    if not storage_text:
        return None
    text = _expand_slash_ranges(storage_text.upper(), "GB")
    text = _expand_slash_ranges(text, "TB")
    tb_vals = [float(n) * 1024 for n in re.findall(r"(\d+(?:\.\d+)?)\s*TB", text)]
    gb_vals = [float(n) for n in re.findall(r"(\d+(?:\.\d+)?)\s*GB", text)]
    vals = tb_vals + gb_vals
    if not vals:
        return None
    return sum(vals) / len(vals)


def parse_battery_mah(battery_text):
    """'6000mAh' -> 6000.0 ; '90WHr' -> None (different unit, laptops) """
    if not battery_text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*mAh", battery_text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def processor_score(processor_text):
    return _score_from_keywords(processor_text, _PROCESSOR_KEYWORDS, default=4.0)


def gpu_score(gpu_text):
    return _score_from_keywords(gpu_text, _GPU_KEYWORDS, default=2.0)


# --- criteria definitions ---------------------------------------------------
# Each entry: key -> (display label, function that extracts a raw numeric
# value from a device dict). Higher raw value = better, for every criterion.

PHONE_CRITERIA = {
    "ram": ("RAM", lambda d: parse_ram_gb(d.get("ram"))),
    "storage": ("Storage", lambda d: parse_storage_gb(d.get("storage"))),
    "battery": ("Battery", lambda d: parse_battery_mah(d.get("battery"))),
    "performance": ("Performance", lambda d: processor_score(d.get("processor"))),
}

LAPTOP_CRITERIA = {
    "ram": ("RAM", lambda d: parse_ram_gb(d.get("ram"))),
    "storage": ("Storage", lambda d: parse_storage_gb(d.get("storage"))),
    "cpu_performance": ("CPU Performance", lambda d: processor_score(d.get("processor"))),
    "gpu_performance": ("Graphics Performance", lambda d: gpu_score(d.get("gpu"))),
}


def criteria_for(device_type):
    return LAPTOP_CRITERIA if device_type == "laptop" else PHONE_CRITERIA


def _normalize(values):
    """Min-max normalize a list of (possibly None) raw values to 0-1. None -> 0 after scaling."""
    numeric = [v for v in values if v is not None]
    if not numeric:
        return [0.0 for _ in values]
    lo, hi = min(numeric), max(numeric)
    if hi == lo:
        # everyone's tied on this criterion — give a neutral 0.5, except
        # None values still score 0 (no data beats "same as everyone")
        return [0.5 if v is not None else 0.0 for v in values]
    return [((v - lo) / (hi - lo)) if v is not None else 0.0 for v in values]


def score_devices(devices, device_type, weights):
    """
    devices: list of device dicts (from db.fetch_devices)
    device_type: 'phone' or 'laptop'
    weights: dict of criterion_key -> weight (e.g. 0-5); missing keys = 0

    Returns the same list of devices, each with a 'score' field added
    (0-100 scale), sorted by score descending (FR4, FR5).
    """
    criteria = criteria_for(device_type)
    if not devices:
        return []

    # extract raw values per criterion, across the whole result set
    raw_by_criterion = {}
    for key, (_, extractor) in criteria.items():
        raw_by_criterion[key] = [extractor(d) for d in devices]

    # normalize each criterion 0-1 across the result set
    norm_by_criterion = {key: _normalize(vals) for key, vals in raw_by_criterion.items()}

    total_weight = sum(weights.get(k, 0) for k in criteria) or 1  # avoid div by zero

    for i, device in enumerate(devices):
        weighted_sum = 0.0
        for key in criteria:
            w = weights.get(key, 0)
            weighted_sum += w * norm_by_criterion[key][i]
        device["score"] = round((weighted_sum / total_weight) * 100, 1)

    devices.sort(key=lambda d: d["score"], reverse=True)
    return devices
