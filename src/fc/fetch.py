"""Fetch the M4 subsets used here from the public competition repository."""
from __future__ import annotations

import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/Mcompetitions/M4-methods/master/Dataset"
FILES = ["Train/Hourly-train", "Test/Hourly-test", "Train/Weekly-train", "Test/Weekly-test"]
DATA = Path(__file__).resolve().parents[2] / "data"


def main() -> None:
    DATA.mkdir(exist_ok=True)
    for f in FILES:
        dest = DATA / f"{f.split('/')[-1]}.csv"
        if dest.exists():
            print(f"have {dest.name}")
            continue
        print(f"fetching {f} ...")
        urllib.request.urlretrieve(f"{BASE}/{f}.csv", dest)
    print(f"-> {DATA}")


if __name__ == "__main__":
    main()
