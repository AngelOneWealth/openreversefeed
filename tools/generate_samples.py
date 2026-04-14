"""Synthetic CAMS and KFintech sample file generator.

Produces fake but format-correct files for local testing + demos. All PAN
numbers start with AAAPL/ZZZZZ so it's obvious they are synthetic.
Folio numbers, transaction IDs, and scheme codes are deterministic per-seed
so runs are reproducible.
"""
from __future__ import annotations

import argparse
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# ---- Fixed fake reference data ----
_FAKE_PANS = [
    "AAAPL0001A",  # individual
    "AAAPL0002B",  # joint
    "AAAPL0003C",  # family - individual
    "AAAPL0003D",  # family - joint (same PAN stem, different last char illustrative)
    "AAAPL0004E",
]

# Synthetic scheme codes and fund names — not real ISINs, not real funds.
# Every code starts with SYN so it is obvious these are fake reference data.
_FAKE_SCHEMES = [
    ("SYNLRGCAP001", "Alpha Largecap Growth Fund - Direct"),
    ("SYNTOP100002", "Beta Top 100 Growth Fund - Direct"),
    ("SYNSMLCAP003", "Gamma Smallcap Growth Fund - Direct"),
    ("SYNMIDCAP004", "Delta Midcap Growth Fund - Direct"),
    ("SYNFLEXI005", "Epsilon Flexicap Growth Fund - Direct"),
]

_FAKE_AMC_CODES = ["ALPHA01", "BETA02", "GAMMA03", "DELTA04", "EPSILON5"]


# ---- CAMS generator ----
def generate_cams(out_path: Path, num_rows: int = 20, seed: int = 42) -> None:
    rng = random.Random(seed)
    rows = []
    base_date = date(2025, 1, 1)
    for i in range(num_rows):
        pan = rng.choice(_FAKE_PANS)
        scheme_code, _scheme_name = rng.choice(_FAKE_SCHEMES)
        amc_idx = _FAKE_SCHEMES.index((scheme_code, _scheme_name))
        prodcode = _FAKE_AMC_CODES[amc_idx]
        txn_type = rng.choices(["P", "R", "SI", "SO"], weights=[6, 2, 1, 1])[0]
        units = round(rng.uniform(10, 500), 4)
        nav = round(rng.uniform(15, 450), 4)
        amount = round(units * nav, 2)
        if txn_type == "R":
            units, amount = -units, -amount
        rows.append(
            {
                "USRTRXNO": f"CAMS{10000000 + i}",
                "FOLIO_NO": f"F{1000000 + (i % 5)}",
                "PRODCODE": prodcode,
                "SCHEME_CODE": scheme_code,
                "UNITS": units,
                "AMOUNT": amount,
                "TRADDATE": (base_date + timedelta(days=i * 3)).isoformat(),
                "TRXNMODE": "N",
                "TRXNTYPE": txn_type,
                "TRNSERIALNO": f"T{2000000 + i}",
                "NAV": nav,
                "BROKCODE": "BRK001",
                "PANNO": pan,
                "INVNAME": f"Synthetic Investor {i % 5}",
            }
        )
    df = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)


# ---- KFintech Format1 generator ----
def generate_kfintech(
    out_path: Path,
    num_rows: int = 20,
    seed: int = 43,
    start_trno: int = 5000,
    inward_prefix: str = "KF",
    inward_base: int = 30000000,
    folio_base: int = 2000000,
    base_date: date = date(2025, 2, 1),
) -> None:
    rng = random.Random(seed)
    rows = []
    for i in range(num_rows):
        pan = rng.choice(_FAKE_PANS)
        scheme_code, _ = rng.choice(_FAKE_SCHEMES)
        amc_idx = _FAKE_SCHEMES.index((scheme_code, _))
        fmcode = _FAKE_AMC_CODES[amc_idx]
        purred = rng.choices(["P", "R", "D"], weights=[7, 2, 1])[0]
        trflag = rng.choice(["", "", "", "TI", "TO"])  # mostly empty
        units = round(rng.uniform(10, 500), 4)
        nav = round(rng.uniform(15, 450), 4)
        amount = round(units * nav, 2)
        if purred == "R":
            units, amount = -units, -amount
        rows.append(
            {
                "INWARDNUM0": f"{inward_prefix}{inward_base + i}",
                "TD_TRNO": f"{start_trno + i}",
                "TD_PTRNO": "0",
                "TD_ACNO": f"F{folio_base + (i % 5)}",
                "FMCODE": fmcode,
                "SCHPLN": scheme_code,
                "TD_UNITS": units,
                "TD_AMT": amount,
                "TD_NAV": nav,
                "TD_TRDT": (base_date + timedelta(days=i * 3)).isoformat(),
                "TRNMODE": "N",
                "TD_PURRED": purred,
                "TRFLAG": trflag,
                "TD_TRTYPE": "",
                "PANNO": pan,
                "INV_NAME": f"Synthetic Investor {i % 5}",
                "BROK_CODE": "BRK001",
            }
        )
    df = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)


def generate_kfintech_dbf(out_path: Path, num_rows: int = 20, seed: int = 44) -> None:
    """Write a KFintech sample as a dBase (.dbf) file — the classic upload format.

    Uses a disjoint range of inward numbers / TD_TRNO / folio base / date so that
    composite keys do not collide with the CSV sample.
    """
    import dbf

    # Build rows via the same generator logic, then write into a fresh dbf Table.
    # IMPORTANT: use a unique tmp path so we don't clobber the sibling kfintech_sample.csv.
    csv_tmp = out_path.with_name(out_path.stem + "_dbfrows_tmp.csv")
    generate_kfintech(
        csv_tmp,
        num_rows=num_rows,
        seed=seed,
        start_trno=7000,
        inward_prefix="KD",
        inward_base=40000000,
        folio_base=3000000,
        base_date=date(2025, 6, 1),
    )
    df = pd.read_csv(csv_tmp, dtype=str).fillna("")
    csv_tmp.unlink()

    # DBF field spec: the KFintech Format1 mandatory headers + a few extras.
    # dbf field types:
    #   C = character (string)
    #   N = numeric (we keep everything as C for simplicity and to match dtype=str behavior in parse())
    field_spec = (
        "INWARDNUM0 C(30); "
        "TD_TRNO C(20); "
        "TD_PTRNO C(20); "
        "TD_ACNO C(30); "
        "FMCODE C(10); "
        "SCHPLN C(20); "
        "TD_UNITS C(20); "
        "TD_AMT C(20); "
        "TD_NAV C(20); "
        "TD_TRDT C(10); "
        "TRNMODE C(2); "
        "TD_PURRED C(4); "
        "TRFLAG C(4); "
        "TD_TRTYPE C(4); "
        "PANNO C(12); "
        "INV_NAME C(50); "
        "BROK_CODE C(10)"
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    table = dbf.Table(str(out_path), field_spec, codepage="utf8")
    table.open(mode=dbf.READ_WRITE)
    try:
        for _, row in df.iterrows():
            table.append(
                {
                    "inwardnum0": str(row["INWARDNUM0"])[:30],
                    "td_trno": str(row["TD_TRNO"])[:20],
                    "td_ptrno": str(row["TD_PTRNO"])[:20],
                    "td_acno": str(row["TD_ACNO"])[:30],
                    "fmcode": str(row["FMCODE"])[:10],
                    "schpln": str(row["SCHPLN"])[:20],
                    "td_units": str(row["TD_UNITS"])[:20],
                    "td_amt": str(row["TD_AMT"])[:20],
                    "td_nav": str(row["TD_NAV"])[:20],
                    "td_trdt": str(row["TD_TRDT"])[:10],
                    "trnmode": str(row["TRNMODE"])[:2],
                    "td_purred": str(row["TD_PURRED"])[:4],
                    "trflag": str(row["TRFLAG"])[:4],
                    "td_trtype": str(row["TD_TRTYPE"])[:4],
                    "panno": str(row["PANNO"])[:12],
                    "inv_name": str(row["INV_NAME"])[:50],
                    "brok_code": str(row["BROK_CODE"])[:10],
                }
            )
    finally:
        table.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic CAMS and KFintech samples")
    parser.add_argument("--out-dir", type=Path, default=Path("tests/fixtures/generated"))
    parser.add_argument("--num-rows", type=int, default=20)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    cams_path = args.out_dir / "cams_sample.csv"
    kf_path = args.out_dir / "kfintech_sample.csv"
    kf_dbf_path = args.out_dir / "kfintech_sample.dbf"

    generate_cams(cams_path, num_rows=args.num_rows)
    generate_kfintech(kf_path, num_rows=args.num_rows)
    generate_kfintech_dbf(kf_dbf_path, num_rows=args.num_rows)

    print(f"Wrote {cams_path} ({args.num_rows} rows)")
    print(f"Wrote {kf_path} ({args.num_rows} rows)")
    print(f"Wrote {kf_dbf_path} ({args.num_rows} rows)")


if __name__ == "__main__":
    main()
