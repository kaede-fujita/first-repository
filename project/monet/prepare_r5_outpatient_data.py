from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd


def to_number(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("％", "", regex=False)
        .str.replace("-", "", regex=False)
        .str.strip()
        .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
    )
    return pd.to_numeric(cleaned, errors="coerce").fillna(0)


def to_num_value(value: object) -> float:
    return float(to_number(pd.Series([value])).iat[0])


def read_rokko1(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="年間値", header=4, dtype=str)
    use_cols = [
        "都道府県コード",
        "二次医療圏コード",
        "二次医療圏名",
        "医療機関コード（医科）",
        "医療機関名",
        "初診患者数（年間）",
        "休日に受診した患者延べ数（年間）",
        "夜間・時間外に受診した患者延べ数（年間）",
        "救急車の受入件数（年間）",
    ]
    out = df[use_cols].copy()
    for c in [
        "初診患者数（年間）",
        "休日に受診した患者延べ数（年間）",
        "夜間・時間外に受診した患者延べ数（年間）",
        "救急車の受入件数（年間）",
    ]:
        out[c] = to_number(out[c])
    return out


def read_rokko2(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=0, header=4, dtype=str)
    df["報告月"] = to_number(df["報告月"])
    annual = df[df["報告月"] == 0].copy()

    use_cols = [
        "都道府県コード",
        "二次医療圏コード",
        "二次医療圏名",
        "医療機関コード（医科）",
        "医療機関名",
        "初診の外来の患者延べ数（年間）",
        "再診の外来の患者延べ数",
        "紹介受診重点外来の患者延べ数",
    ]
    out = annual[use_cols].copy()
    out["紹介受診重点外来の患者延べ数"] = to_number(out["紹介受診重点外来の患者延べ数"])
    out["初診の外来の患者延べ数（年間）"] = to_number(out["初診の外来の患者延べ数（年間）"])
    out["再診の外来の患者延べ数"] = to_number(out["再診の外来の患者延べ数"])
    return out


def read_cp932_rows(path: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    with path.open("r", encoding="cp932", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append(row)
    return rows


def parse_prefecture_rates(path: Path, inpatient_col: int, outpatient_col: int) -> pd.DataFrame:
    rows = read_cp932_rows(path)

    start_idx = next((i for i, r in enumerate(rows) if len(r) > 0 and r[0] == "全国"), None)
    if start_idx is None:
        raise ValueError(f"{path.name} で '全国' 行を見つけられませんでした。")

    current_region = None
    records: list[dict[str, float | str]] = []

    for row in rows[start_idx:]:
        c0 = row[0].strip() if len(row) > 0 else ""
        c1 = row[1].strip() if len(row) > 1 else ""

        if c0 and c1 == "":
            current_region = c0
            continue

        if current_region and c0 == "総数" and c1 == "総数":
            inpatient = to_num_value(row[inpatient_col] if len(row) > inpatient_col else "")
            outpatient = to_num_value(row[outpatient_col] if len(row) > outpatient_col else "")
            records.append(
                {
                    "地域": current_region,
                    "入院受療率_人口10万対": inpatient,
                    "外来受療率_人口10万対": outpatient,
                }
            )

    if not records:
        raise ValueError(f"{path.name} から地域別受療率を抽出できませんでした。")

    return pd.DataFrame(records)


def parse_t0038_prefecture(path: Path) -> pd.DataFrame:
    pref = parse_prefecture_rates(path, inpatient_col=2, outpatient_col=5)
    total = pref["入院受療率_人口10万対"] + pref["外来受療率_人口10万対"]
    pref["入院受療率_pct"] = (pref["入院受療率_人口10万対"] / total.replace(0, pd.NA) * 100).fillna(0)
    pref["外来受療率_pct"] = (pref["外来受療率_人口10万対"] / total.replace(0, pd.NA) * 100).fillna(0)
    return pref


def parse_g0016_prefecture(path: Path) -> pd.DataFrame:
    pref = parse_prefecture_rates(path, inpatient_col=2, outpatient_col=5)
    return pref.rename(
        columns={
            "入院受療率_人口10万対": "入院受療率_人口10万対_H29",
            "外来受療率_人口10万対": "外来受療率_人口10万対_H29",
        }
    )


def build_emergency_by_area(rokko1: pd.DataFrame, rokko2: pd.DataFrame) -> pd.DataFrame:
    key_cols = ["都道府県コード", "二次医療圏コード", "二次医療圏名", "医療機関コード（医科）", "医療機関名"]
    merged = rokko1.merge(rokko2, on=key_cols, how="inner")

    merged["外来患者延べ数_年間"] = merged["初診の外来の患者延べ数（年間）"] + merged["再診の外来の患者延べ数"]

    agg = (
        merged.groupby(["都道府県コード", "二次医療圏コード", "二次医療圏名"], as_index=False)[
            [
                "初診患者数（年間）",
                "外来患者延べ数_年間",
                "休日に受診した患者延べ数（年間）",
                "夜間・時間外に受診した患者延べ数（年間）",
                "救急車の受入件数（年間）",
                "紹介受診重点外来の患者延べ数",
            ]
        ]
        .sum()
    )

    base = agg["外来患者延べ数_年間"].where(agg["外来患者延べ数_年間"] > 0, pd.NA)
    agg["救急発生率_pct"] = (agg["救急車の受入件数（年間）"] / base * 100).fillna(0)
    agg["紹介受診重点外来率_pct"] = (agg["紹介受診重点外来の患者延べ数"] / base * 100).fillna(0)

    return agg.sort_values("救急発生率_pct", ascending=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="R5 外来機能・外来（二次医療圏編）データクリーニング")
    parser.add_argument("--rokko1", type=Path, default=Path("/Users/fujitakaede/Downloads/r5rokko1.xlsx"))
    parser.add_argument("--rokko2", type=Path, default=Path("/Users/fujitakaede/Downloads/r5rokko2.xlsx"))
    parser.add_argument("--t0038", type=Path, default=Path("/Users/fujitakaede/Downloads/t0038.csv"))
    parser.add_argument("--g0016", type=Path, default=Path("/Users/fujitakaede/Downloads/g0016.csv"))
    parser.add_argument("--outdir", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)

    rokko1 = read_rokko1(args.rokko1)
    rokko2 = read_rokko2(args.rokko2)
    area_emergency = build_emergency_by_area(rokko1, rokko2)

    pref_r5 = parse_t0038_prefecture(args.t0038)
    pref_h29 = parse_g0016_prefecture(args.g0016)
    pref = pref_r5.merge(pref_h29, on="地域", how="left")
    pref["入院受療率_変化率_pct"] = (
        (pref["入院受療率_人口10万対"] - pref["入院受療率_人口10万対_H29"])
        / pref["入院受療率_人口10万対_H29"].replace(0, pd.NA)
        * 100
    ).fillna(0)
    pref["外来受療率_変化率_pct"] = (
        (pref["外来受療率_人口10万対"] - pref["外来受療率_人口10万対_H29"])
        / pref["外来受療率_人口10万対_H29"].replace(0, pd.NA)
        * 100
    ).fillna(0)

    area_emergency.to_csv(args.outdir / "r5_outpatient_emergency_by_area.csv", index=False, encoding="utf-8-sig")
    pref.to_csv(args.outdir / "r5_prefecture_care_rates.csv", index=False, encoding="utf-8-sig")

    print("created:")
    print(args.outdir / "r5_outpatient_emergency_by_area.csv")
    print(args.outdir / "r5_prefecture_care_rates.csv")


if __name__ == "__main__":
    main()
