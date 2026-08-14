from pathlib import Path

import pandas as pd
import yfinance as yf


# ---- Inställningar ----

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
CANDIDATES_FILE = HERE / "yahoo_ticker_candidates.txt"
DIVIDEND_FILE = REPO_ROOT / "data" / "dividends.csv"


# ---- Läs tickers ----

def load_tickers() -> list[str]:
    tickers = []

    for raw in CANDIDATES_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()

        if not line or line.startswith("#"):
            continue

        _, yahoo = line.split("\t", 1)
        tickers.append(yahoo)

    return tickers


# ---- Uppdatera utdelningar ----

def main() -> None:
    if not DIVIDEND_FILE.exists():
        raise FileNotFoundError(
            f"{DIVIDEND_FILE} saknas. Lägg in den historiska dividends.csv först."
        )

    old = pd.read_csv(
        DIVIDEND_FILE,
        dtype={"ticker": str, "ex_date": str},
    )

    old["dividend"] = pd.to_numeric(old["dividend"], errors="coerce")

    tickers = load_tickers()
    rows = []

    for i, ticker in enumerate(tickers, start=1):
        print(f"[{i}/{len(tickers)}] {ticker}")

        try:
            dividends = yf.Ticker(ticker).get_dividends(period="max")
        except Exception as exc:
            print(f"  Fel: {exc}")
            continue

        for ex_date, amount in dividends.items():
            rows.append(
                {
                    "ticker": ticker,
                    "ex_date": pd.Timestamp(ex_date).date().isoformat(),
                    "dividend": float(amount),
                }
            )

    fetched = pd.DataFrame(rows, columns=["ticker", "ex_date", "dividend"])

    if fetched.empty:
        print("Ingen utdelningsdata hämtades.")
        return

    old_keys = set(zip(old["ticker"], old["ex_date"]))

    new_rows = fetched[
        ~fetched.apply(
            lambda row: (row["ticker"], row["ex_date"]) in old_keys,
            axis=1,
        )
    ].copy()

    combined = pd.concat([old, fetched], ignore_index=True)

    # Senast hämtade Yahoo-värde får ersätta samma ticker/ex-datum
    # om Yahoo har korrigerat en äldre post.
    combined = (
        combined.drop_duplicates(subset=["ticker", "ex_date"], keep="last")
        .sort_values(["ticker", "ex_date"])
        .reset_index(drop=True)
    )

    old_sorted = (
        old.sort_values(["ticker", "ex_date"])
        .reset_index(drop=True)
    )

    changed = not combined.equals(old_sorted)

    if changed:
        combined.to_csv(DIVIDEND_FILE, index=False)

    print()

    if not new_rows.empty:
        print(f"Nya utdelningar: {len(new_rows)}")
        print(
            new_rows
            .sort_values(["ticker", "ex_date"])
            .to_string(index=False)
        )
    elif changed:
        print("Ingen ny utdelning, men en befintlig post uppdaterades.")
    else:
        print("Ingen ny utdelning.")


if __name__ == "__main__":
    main()
