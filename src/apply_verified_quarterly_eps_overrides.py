from __future__ import annotations

import pandas as pd

from .config import ROOT
from .quarterly_eps import QUARTERLY_COLUMNS, _publish_json, load_quarterly_eps, save_quarterly_eps

OVERRIDES_FILE = ROOT / "data" / "earnings" / "quarterly_eps_verified_overrides.csv"


def main() -> None:
    if not OVERRIDES_FILE.exists() or OVERRIDES_FILE.stat().st_size == 0:
        print("Inga verifierade kvartals-EPS-overrides att applicera.")
        return

    overrides = pd.read_csv(OVERRIDES_FILE)
    missing = sorted(set(QUARTERLY_COLUMNS).difference(overrides.columns))
    if missing:
        raise ValueError("Override-filen saknar kolumner: " + ", ".join(missing))

    existing = load_quarterly_eps()
    combined = pd.concat([existing, overrides[QUARTERLY_COLUMNS]], ignore_index=True)
    save_quarterly_eps(combined)
    saved = load_quarterly_eps()
    _publish_json(saved)
    print(f"Applicerade {len(overrides)} verifierade kvartals-EPS-overrides.")


if __name__ == "__main__":
    main()
