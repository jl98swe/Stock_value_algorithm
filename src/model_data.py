from __future__ import annotations

import base64
import hashlib
import json
import re
import zlib
from pathlib import Path

from .config import ROOT

MODEL_DIR = ROOT / "data" / "model"
MODEL_JSON = MODEL_DIR / "gbm_model.json"
MODEL_PART_GLOB = "gbm_model.b85.part*"
EXPECTED_JSON_SHA256 = "ea557ed23ef61363b6dd392e0135ea7c3c9d1119036c47b5dea1638234b7a73c"
EXPECTED_LENGTHS = {
    "node_feat": 4324,
    "node_thr": 4324,
    "node_left": 4324,
    "node_right": 4324,
    "tree_root": 100,
}


def _part_number(path: Path) -> int:
    match = re.search(r"part(\d+)$", path.name)
    if match is None:
        raise ValueError(f"Ogiltigt GBM-delnummer: {path.name}")
    return int(match.group(1))


def _validate_payload(payload: dict[str, object]) -> None:
    for key, expected in EXPECTED_LENGTHS.items():
        values = payload.get(key)
        if not isinstance(values, list) or len(values) != expected:
            actual = len(values) if isinstance(values, list) else None
            raise ValueError(f"GBM {key}: förväntade {expected} värden, fick {actual}")

    node_count = EXPECTED_LENGTHS["node_feat"]
    children = list(payload["node_left"]) + list(payload["node_right"])
    invalid_children = [value for value in children if int(value) >= node_count]
    if invalid_children:
        raise ValueError("GBM-modellen innehåller barnindex utanför nodtabellen")

    roots = [int(value) for value in payload["tree_root"]]
    if any(value < 0 or value >= node_count for value in roots):
        raise ValueError("GBM-modellen innehåller ogiltigt trädrotindex")


def ensure_gbm_model(target: Path = MODEL_JSON) -> Path:
    """Skapa gbm_model.json från de versionshanterade Base85-delarna.

    Delarna är en förlustfri zlib+Base85-kodning av de 100 GBM-träden som
    extraherades ur Pine v3.0. SHA-256 och arraylängder verifieras innan modellen
    får användas av värderingspipen.
    """
    if target.exists() and target.stat().st_size:
        raw = target.read_bytes()
        if hashlib.sha256(raw).hexdigest() == EXPECTED_JSON_SHA256:
            payload = json.loads(raw.decode("utf-8"))
            _validate_payload(payload)
            return target

    parts = sorted(MODEL_DIR.glob(MODEL_PART_GLOB), key=_part_number)
    if not parts:
        raise FileNotFoundError(f"Inga GBM-modelldelar hittades i {MODEL_DIR}")

    expected_part_numbers = list(range(1, len(parts) + 1))
    actual_part_numbers = [_part_number(path) for path in parts]
    if actual_part_numbers != expected_part_numbers:
        raise ValueError(
            f"GBM-modelldelar saknas eller ligger fel: {actual_part_numbers}"
        )

    encoded = "".join(path.read_text(encoding="ascii").strip() for path in parts)
    try:
        raw = zlib.decompress(base64.b85decode(encoded.encode("ascii")))
    except Exception as exc:
        raise ValueError("Kunde inte avkoda GBM-modelldelarna") from exc

    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_JSON_SHA256:
        raise ValueError(
            "GBM-modellen klarade inte integritetskontrollen: "
            f"{digest} != {EXPECTED_JSON_SHA256}"
        )

    payload = json.loads(raw.decode("utf-8"))
    _validate_payload(payload)

    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_bytes(raw)
    temp.replace(target)
    return target


if __name__ == "__main__":
    path = ensure_gbm_model()
    print(f"GBM-modell klar: {path}")
