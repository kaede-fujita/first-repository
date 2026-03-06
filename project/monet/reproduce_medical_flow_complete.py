#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

import pandas as pd


# ----------------------------
# Utilities
# ----------------------------
def read_lines_auto(path: Path) -> list[str]:
    for enc in ("cp932", "shift_jis", "utf-8-sig", "utf-8"):
        try:
            return path.read_text(encoding=enc).splitlines()
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace").splitlines()


def parse_num(x) -> float:
    s = str(x).strip()
    if s in ("", "-", "－"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip())


def is_med_area_row(s: str) -> bool:
    return re.match(r"^\d{4}\s+", norm_space(s)) is not None


def split_code_name(s: str) -> tuple[str, str]:
    t = norm_space(s)
    m = re.match(r"^(\d{4})\s+(.+)$", t)
    if not m:
        return "", t
    return m.group(1), m.group(2)


def to_int_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0).round().astype("int64")


# ----------------------------
# Raw -> Tidy
# ----------------------------
def tidy_n1(n1_path: Path) -> pd.DataFrame:
    lines = read_lines_auto(n1_path)
    rows = list(csv.reader(lines[5:]))  # 6行目以降が本体

    out = []
    for r in rows:
        if len(r) < 6:
            continue
        if not is_med_area_row(r[0]):
            continue

        code, area = split_code_name(r[0])
        out.append({"医療圏コード": code, "二次医療圏名": area, "区分": "二次医療圏内", "値": parse_num(r[2])})
        out.append({"医療圏コード": code, "二次医療圏名": area, "区分": "二次医療圏外(県内)", "値": parse_num(r[4])})
        out.append({"医療圏コード": code, "二次医療圏名": area, "区分": "二次医療圏外(県外)", "値": parse_num(r[5])})

    return pd.DataFrame(out)


def tidy_n2(n2_path: Path) -> pd.DataFrame:
    lines = read_lines_auto(n2_path)
    rows = list(csv.reader(lines[4:]))  # 5行目以降
    rows = [r for r in rows if len(r) >= 33]
    if not rows:
        raise ValueError("N2本体が読み取れませんでした。")

    bed_header = rows[0]
    bed_blocks = [(str(v).strip(), i) for i, v in enumerate(bed_header) if str(v).strip()]

    out = []
    for r in rows:
        if not is_med_area_row(r[0]):
            continue

        code, area = split_code_name(r[0])
        for bed, i in bed_blocks:
            if i + 3 >= len(r):
                continue
            out.append({"医療圏コード": code, "二次医療圏名": area, "病床種別": bed, "区分": "二次医療圏内", "値": parse_num(r[i + 1])})
            out.append({"医療圏コード": code, "二次医療圏名": area, "病床種別": bed, "区分": "二次医療圏外(県内)", "値": parse_num(r[i + 2])})
            out.append({"医療圏コード": code, "二次医療圏名": area, "病床種別": bed, "区分": "二次医療圏外(県外)", "値": parse_num(r[i + 3])})

    return pd.DataFrame(out)


# ----------------------------
# Aggregation
# ----------------------------
def aggregate_flow(n1_tidy: pd.DataFrame, n2_tidy: pd.DataFrame):
    # N1: D_i, C_i, O_inpref_i, O_outpref_i
    p1 = n1_tidy.pivot_table(index="二次医療圏名", columns="区分", values="値", aggfunc="sum", fill_value=0)
    for c in ["二次医療圏内", "二次医療圏外(県内)", "二次医療圏外(県外)"]:
        if c not in p1.columns:
            p1[c] = 0.0

    t1 = pd.DataFrame(index=p1.index)
    t1["入院需要"] = p1["二次医療圏内"] + p1["二次医療圏外(県内)"] + p1["二次医療圏外(県外)"]
    t1["圏内入院"] = p1["二次医療圏内"]
    t1["県内流出"] = p1["二次医療圏外(県内)"]
    t1["県外流出"] = p1["二次医療圏外(県外)"]
    t1["完結率"] = (t1["圏内入院"] / t1["入院需要"].replace(0, pd.NA)).fillna(0).round(4)
    t1["流出率"] = (1 - t1["完結率"]).round(4)

    # N2: S_i, I_inpref_i, I_outpref_i
    # 注意: 総数は病床種別「病院」を使用（病床別単純合算は二重計上の恐れ）
    n2_hosp = n2_tidy[n2_tidy["病床種別"] == "病院"].copy()
    p2 = n2_hosp.pivot_table(index="二次医療圏名", columns="区分", values="値", aggfunc="sum", fill_value=0)
    for c in ["二次医療圏内", "二次医療圏外(県内)", "二次医療圏外(県外)"]:
        if c not in p2.columns:
            p2[c] = 0.0

    t2 = pd.DataFrame(index=p2.index)
    t2["受入総数"] = p2["二次医療圏内"] + p2["二次医療圏外(県内)"] + p2["二次医療圏外(県外)"]
    t2["県内流入"] = p2["二次医療圏外(県内)"]
    t2["県外流入"] = p2["二次医療圏外(県外)"]
    t2["流入率"] = ((t2["県内流入"] + t2["県外流入"]) / t2["受入総数"].replace(0, pd.NA)).fillna(0).round(4)

    result = t1.join(t2, how="outer").fillna(0).reset_index()
    result = result.rename(columns={"index": "二次医療圏名"})
    result = result[
        ["二次医療圏名", "入院需要", "圏内入院", "県内流出", "県外流出", "完結率", "受入総数", "県内流入", "県外流入", "流入率"]
    ]

    # 病床種別別の流入構造（病院=総計のため除外）
    bed = n2_tidy[n2_tidy["病床種別"] != "病院"].copy()
    pb = bed.pivot_table(index=["二次医療圏名", "病床種別"], columns="区分", values="値", aggfunc="sum", fill_value=0)
    for c in ["二次医療圏内", "二次医療圏外(県内)", "二次医療圏外(県外)"]:
        if c not in pb.columns:
            pb[c] = 0.0

    bed_out = pd.DataFrame(index=pb.index)
    bed_out["圏内住所患者"] = pb["二次医療圏内"]
    bed_out["県内流入"] = pb["二次医療圏外(県内)"]
    bed_out["県外流入"] = pb["二次医療圏外(県外)"]
    bed_out["受入総数"] = bed_out["圏内住所患者"] + bed_out["県内流入"] + bed_out["県外流入"]
    bed_out["流入率"] = ((bed_out["県内流入"] + bed_out["県外流入"]) / bed_out["受入総数"].replace(0, pd.NA)).fillna(0).round(4)
    bed_out["県内流入構成比"] = (bed_out["県内流入"] / bed_out["受入総数"].replace(0, pd.NA)).fillna(0).round(4)
    bed_out["県外流入構成比"] = (bed_out["県外流入"] / bed_out["受入総数"].replace(0, pd.NA)).fillna(0).round(4)
    bed_out = bed_out.reset_index()

    # 単位: 元データは千人。出力は常に人単位（×1000）に換算。
    scale = 1000
    for c in ["入院需要", "圏内入院", "県内流出", "県外流出", "受入総数", "県内流入", "県外流入"]:
        result[c] = result[c] * scale
    for c in ["圏内住所患者", "県内流入", "県外流入", "受入総数"]:
        bed_out[c] = bed_out[c] * scale

    # 型・丸め
    for c in ["入院需要", "圏内入院", "県内流出", "県外流出", "受入総数", "県内流入", "県外流入"]:
        result[c] = to_int_series(result[c])
    result["完結率"] = pd.to_numeric(result["完結率"], errors="coerce").fillna(0).round(4)
    result["流入率"] = pd.to_numeric(result["流入率"], errors="coerce").fillna(0).round(4)

    for c in ["圏内住所患者", "県内流入", "県外流入", "受入総数"]:
        bed_out[c] = to_int_series(bed_out[c])
    for c in ["流入率", "県内流入構成比", "県外流入構成比"]:
        bed_out[c] = pd.to_numeric(bed_out[c], errors="coerce").fillna(0).round(4)

    # 整合チェック Σ(O_inpref_i) ≈ Σ(I_inpref_i)
    sum_o = int(result["県内流出"].sum())
    sum_i = int(result["県内流入"].sum())
    diff = sum_o - sum_i
    err = round(abs(diff) / (sum_o if sum_o != 0 else 1), 6)
    check = pd.DataFrame([{"Σ県内流出": sum_o, "Σ県内流入": sum_i, "差分(流出-流入)": diff, "誤差率": err}])

    return result, bed_out, check


def make_repro_report(summary: pd.DataFrame, bed: pd.DataFrame, check: pd.DataFrame, report_path: Path) -> None:
    n_area = len(summary)
    D = int(summary["入院需要"].sum())
    C = int(summary["圏内入院"].sum())
    O_in = int(summary["県内流出"].sum())
    O_out = int(summary["県外流出"].sum())
    S = int(summary["受入総数"].sum())
    I_in = int(summary["県内流入"].sum())
    I_out = int(summary["県外流入"].sum())

    stay_w = round(C / D, 4) if D else 0
    inflow_w = round((I_in + I_out) / S, 4) if S else 0

    row = check.iloc[0]
    sum_o = int(row["Σ県内流出"])
    sum_i = int(row["Σ県内流入"])
    diff = int(row["差分(流出-流入)"])
    err = float(row["誤差率"])

    low_stay = summary.sort_values("完結率").head(10)[["二次医療圏名", "完結率", "入院需要", "県内流出", "県外流出"]]
    high_in = summary.sort_values("流入率", ascending=False).head(10)[["二次医療圏名", "流入率", "受入総数", "県内流入", "県外流入"]]

    bed_agg = bed.groupby("病床種別")[["受入総数", "県内流入", "県外流入"]].sum().sort_values("受入総数", ascending=False)
    bed_agg["流入率"] = ((bed_agg["県内流入"] + bed_agg["県外流入"]) / bed_agg["受入総数"]).round(4)

    lines = []
    lines.append("# 患者調査（二次医療圏編）再現分析レポート")
    lines.append("")
    lines.append("## 方法")
    lines.append("- 入力: n0001.csv（患者住所地）, n0002.csv（施設所在地）")
    lines.append("- 前処理: 先頭メタ情報行除去、多段ヘッダを縦持ちtidyへ正規化、欠損・'-'は0")
    lines.append("- 指標: 入院完結率=圏内入院/入院需要、流入率=(県内流入+県外流入)/受入総数")
    lines.append("- 単位: 出力値はすべて人単位（元データ千人を×1000換算）")
    lines.append("- N2総数は病床種別'病院'を採用（病床別単純合算による二重計上回避）")
    lines.append("")
    lines.append("## 結果（全体）")
    lines.append(f"- 対象二次医療圏数: {n_area}")
    lines.append(f"- 入院需要合計 D: {D}")
    lines.append(f"- 圏内入院合計 C: {C}")
    lines.append(f"- 県内流出合計: {O_in}")
    lines.append(f"- 県外流出合計: {O_out}")
    lines.append(f"- 需要加重の入院完結率: {stay_w:.4f}")
    lines.append(f"- 受入総数合計 S: {S}")
    lines.append(f"- 県内流入合計: {I_in}")
    lines.append(f"- 県外流入合計: {I_out}")
    lines.append(f"- 受入加重の流入率: {inflow_w:.4f}")
    lines.append("")
    lines.append("## 整合チェック")
    lines.append(f"- Σ県内流出: {sum_o}")
    lines.append(f"- Σ県内流入: {sum_i}")
    lines.append(f"- 差分（流出-流入）: {diff}")
    lines.append(f"- 誤差率: {err:.6f}")
    lines.append("")
    lines.append("## 低完結率 上位10（CSV形式）")
    lines.append(low_stay.to_csv(index=False).strip())
    lines.append("")
    lines.append("## 高流入率 上位10（CSV形式）")
    lines.append(high_in.to_csv(index=False).strip())
    lines.append("")
    lines.append("## 病床種別流入構造（全医療圏合計, CSV形式）")
    lines.append(bed_agg.reset_index().to_csv(index=False).strip())

    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="患者調査（二次医療圏編）再現分析")
    parser.add_argument("--n1", required=True, help="N1元CSV（患者住所地）")
    parser.add_argument("--n2", required=True, help="N2元CSV（施設所在地）")
    parser.add_argument("--outdir", required=True, help="出力ディレクトリ")
    parser.add_argument("--report", action="store_true", help="再現レポート(reproducibility_report.md)も出力")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    n1_tidy = tidy_n1(Path(args.n1))
    n2_tidy = tidy_n2(Path(args.n2))

    (outdir / "n0001_tidy.csv").write_text(n1_tidy.to_csv(index=False), encoding="utf-8-sig")
    (outdir / "n0002_tidy.csv").write_text(n2_tidy.to_csv(index=False), encoding="utf-8-sig")

    summary, bed, check = aggregate_flow(n1_tidy, n2_tidy)

    summary_path = outdir / "medical_area_flow_summary.csv"
    bed_path = outdir / "medical_area_bed_inflow_structure.csv"
    check_path = outdir / "medical_area_inpref_balance_check.csv"

    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    bed.to_csv(bed_path, index=False, encoding="utf-8-sig")
    check.to_csv(check_path, index=False, encoding="utf-8-sig")

    print(summary_path)
    print(bed_path)
    print(check_path)

    if args.report:
        report_path = outdir / "reproducibility_report.md"
        make_repro_report(summary, bed, check, report_path)
        print(report_path)


if __name__ == "__main__":
    main()
