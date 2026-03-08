#!/usr/bin/env python3
"""R5 外来機能報告（年間値）を施設緯度経度ベースで地理評価する。"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd

PREF_META = {
    "01": "北海道", "02": "青森県", "03": "岩手県", "04": "宮城県", "05": "秋田県", "06": "山形県", "07": "福島県",
    "08": "茨城県", "09": "栃木県", "10": "群馬県", "11": "埼玉県", "12": "千葉県", "13": "東京都", "14": "神奈川県",
    "15": "新潟県", "16": "富山県", "17": "石川県", "18": "福井県", "19": "山梨県", "20": "長野県", "21": "岐阜県",
    "22": "静岡県", "23": "愛知県", "24": "三重県", "25": "滋賀県", "26": "京都府", "27": "大阪府", "28": "兵庫県",
    "29": "奈良県", "30": "和歌山県", "31": "鳥取県", "32": "島根県", "33": "岡山県", "34": "広島県", "35": "山口県",
    "36": "徳島県", "37": "香川県", "38": "愛媛県", "39": "高知県", "40": "福岡県", "41": "佐賀県", "42": "長崎県",
    "43": "熊本県", "44": "大分県", "45": "宮崎県", "46": "鹿児島県", "47": "沖縄県",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="施設緯度経度ベースの地理情報分析")
    parser.add_argument("--input", required=True, help="入力Excelパス（r5rokko1.xlsx など）")
    parser.add_argument("--outdir", default=".", help="出力先ディレクトリ")
    return parser.parse_args()


def to_numeric(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.strip()
    cleaned = cleaned.replace({"*": pd.NA, "-": pd.NA, "nan": pd.NA, "": pd.NA})
    return pd.to_numeric(cleaned, errors="coerce")


def zscore(series: pd.Series) -> pd.Series:
    s = series.fillna(series.median())
    std = s.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / std


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nearest_neighbor_mean_km(points: pd.DataFrame) -> float:
    n = len(points)
    if n <= 1:
        return float("nan")
    mins = []
    coords = points[["緯度", "経度"]].to_records(index=False)
    for i in range(n):
        dmin = None
        for j in range(n):
            if i == j:
                continue
            d = haversine_km(coords[i][0], coords[i][1], coords[j][0], coords[j][1])
            if dmin is None or d < dmin:
                dmin = d
        mins.append(dmin)
    return float(sum(mins) / len(mins)) if mins else float("nan")


def build_facility_leaflet_html(df: pd.DataFrame, value_col: str, title: str) -> str:
    if df.empty:
        center_lat, center_lon = 36.2, 138.2
        max_val = 0.0
    else:
        center_lat = float(df["緯度"].mean())
        center_lon = float(df["経度"].mean())
        max_val = float(df[value_col].max())

    records = df[["医療機関名", "二次医療圏名", "住所", "緯度", "経度", value_col]].to_dict(orient="records")
    records_json = json.dumps(records, ensure_ascii=False)

    return f"""<!doctype html>
<html lang=\"ja\">
<head>
<meta charset=\"utf-8\" />
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
<title>{title}</title>
<link rel=\"stylesheet\" href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\" />
<style>
body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }}
h1 {{ margin: 12px 16px; font-size: 18px; }}
#map {{ height: calc(100vh - 48px); }}
</style>
</head>
<body>
<h1>{title}</h1>
<div id=\"map\"></div>
<script src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\"></script>
<script>
  const data = {records_json};
  const maxVal = {max_val};
  const map = L.map('map').setView([{center_lat}, {center_lon}], 9);
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 18,
    attribution: '&copy; OpenStreetMap contributors'
  }}).addTo(map);

  function radius(v) {{
    if (!maxVal || v <= 0) return 5;
    return 5 + 14 * Math.sqrt(v / maxVal);
  }}

  data.forEach((r) => {{
    const v = Number(r['{value_col}']) || 0;
    L.circleMarker([r.緯度, r.経度], {{
      radius: radius(v),
      color: '#9b2226',
      fillColor: '#ee9b00',
      fillOpacity: 0.75,
      weight: 1
    }}).bindPopup(
      `${{r.医療機関名}}<br>医療圏: ${{r.二次医療圏名}}<br>{value_col}: ${{v.toLocaleString()}}<br>住所: ${{r.住所 || ''}}`
    ).addTo(map);
  }});
</script>
</body>
</html>
"""


def calc_area_geo_metrics(group: pd.DataFrame) -> pd.Series:
    g = group[group["緯度"].notna() & group["経度"].notna()].copy()
    if g.empty:
        return pd.Series(
            {
                "中心緯度": pd.NA,
                "中心経度": pd.NA,
                "平均中心距離_km": pd.NA,
                "最大中心距離_km": pd.NA,
                "平均最近接距離_km": pd.NA,
                "施設空間カバー面積_km2": pd.NA,
                "施設密度_10km2あたり": pd.NA,
                "救急受入上位3施設集中度": pd.NA,
            }
        )

    c_lat = float(g["緯度"].mean())
    c_lon = float(g["経度"].mean())

    dists = [haversine_km(float(r["緯度"]), float(r["経度"]), c_lat, c_lon) for _, r in g.iterrows()]
    mean_dist = float(sum(dists) / len(dists)) if dists else float("nan")
    max_dist = float(max(dists)) if dists else float("nan")

    nn_mean = nearest_neighbor_mean_km(g)
    cover_km2 = math.pi * (max_dist**2) if pd.notna(max_dist) else float("nan")
    density_10 = (len(g) / (cover_km2 / 10.0)) if cover_km2 and cover_km2 > 0 else float("nan")

    emer = g["救急車の受入件数（年間）"].fillna(0)
    total_emer = float(emer.sum())
    top3_ratio = float(emer.nlargest(min(3, len(emer))).sum() / total_emer) if total_emer > 0 else float("nan")

    return pd.Series(
        {
            "中心緯度": c_lat,
            "中心経度": c_lon,
            "平均中心距離_km": mean_dist,
            "最大中心距離_km": max_dist,
            "平均最近接距離_km": nn_mean,
            "施設空間カバー面積_km2": cover_km2,
            "施設密度_10km2あたり": density_10,
            "救急受入上位3施設集中度": top3_ratio,
        }
    )


def main() -> None:
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = pd.read_excel(args.input, sheet_name="年間値", header=4)

    # 既存クリーニング条件は維持
    df = df[df["病診区分"].notna() & df["医療機関名"].notna()].copy()

    df["都道府県コード"] = pd.to_numeric(df["都道府県コード"], errors="coerce").astype("Int64").astype(str).str.zfill(2)
    df["都道府県名"] = df["都道府県コード"].map(lambda c: PREF_META.get(c, "不明"))

    numeric_cols = [
        "医師 常勤", "医師 非常勤", "看護師 常勤", "看護師 非常勤",
        "初診患者数（年間）", "紹介患者数（年間）", "逆紹介患者数（年間）",
        "休日に受診した患者延べ数（年間）", "夜間・時間外に受診した患者延べ数（年間）",
        "診察後直ちに入院となった患者延べ数（年間）", "診察後直ちに入院となった患者延べ数（年間）.1",
        "救急車の受入件数（年間）", "緯度", "経度",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = to_numeric(df[col])

    dept_cols = [c for c in df.columns if str(c).startswith("外来を行っている診療科")]
    df["診療科対応数"] = df[dept_cols].eq("〇").sum(axis=1)

    equipment_cols = [
        c for c in df.columns if any(k in str(c) for k in ["CT", "MRI", "ＰＥＴ", "ガンマナイフ", "IMRT", "内視鏡手術用支援機器"])
    ]
    df["高度機器保有数"] = (
        df[equipment_cols]
        .apply(lambda col: col.map(lambda v: 1 if str(v).strip() in {"〇", "1"} else 0))
        .sum(axis=1)
        if equipment_cols
        else 0
    )

    df["構造スコア"] = (
        zscore(df.get("医師 常勤", pd.Series(index=df.index, dtype=float)))
        + zscore(df.get("看護師 常勤", pd.Series(index=df.index, dtype=float)))
        + zscore(df["診療科対応数"])
        + zscore(df.get("救急車の受入件数（年間）", pd.Series(index=df.index, dtype=float)))
        + zscore(df["高度機器保有数"])
    )
    df["構造スコア偏差値"] = 50 + 10 * zscore(df["構造スコア"])

    area_base = (
        df.groupby(["都道府県コード", "都道府県名", "二次医療圏名"], dropna=False)
        .agg(
            施設数=("医療機関名", "count"),
            緯度経度あり施設数=("緯度", lambda s: int(s.notna().sum())),
            救急車受入件数_年間=("救急車の受入件数（年間）", "sum"),
            医師常勤数=("医師 常勤", "sum"),
            看護師常勤数=("看護師 常勤", "sum"),
            平均診療科対応数=("診療科対応数", "mean"),
            高度機器保有数=("高度機器保有数", "sum"),
            平均構造スコア=("構造スコア", "mean"),
            構造スコア標準偏差=("構造スコア", lambda s: float(s.std(ddof=0))),
        )
        .reset_index()
    )

    area_geo = (
        df.groupby(["都道府県コード", "都道府県名", "二次医療圏名"], dropna=False)
        .apply(calc_area_geo_metrics, include_groups=False)
        .reset_index()
    )

    area = area_base.merge(area_geo, on=["都道府県コード", "都道府県名", "二次医療圏名"], how="left")
    area["圏内体制評価スコア"] = (
        zscore(area["平均構造スコア"])
        + zscore(area["救急車受入件数_年間"])
        + zscore(area["高度機器保有数"])
        - zscore(area["平均最近接距離_km"])
    )
    area = area.sort_values(["圏内体制評価スコア", "救急車受入件数_年間"], ascending=[False, False])

    centers = area[["都道府県コード", "都道府県名", "二次医療圏名", "中心緯度", "中心経度"]].copy()
    df = df.merge(centers, on=["都道府県コード", "都道府県名", "二次医療圏名"], how="left")

    def _dist_to_center(row: pd.Series):
        if pd.isna(row.get("緯度")) or pd.isna(row.get("経度")) or pd.isna(row.get("中心緯度")) or pd.isna(row.get("中心経度")):
            return pd.NA
        return haversine_km(float(row["緯度"]), float(row["経度"]), float(row["中心緯度"]), float(row["中心経度"]))

    df["中心距離_km"] = df.apply(_dist_to_center, axis=1)
    df["施設評価スコア"] = zscore(df["構造スコア"]) + zscore(df["救急車の受入件数（年間）"]) - zscore(df["中心距離_km"])

    facility_geo = df[df["緯度"].notna() & df["経度"].notna()].copy()
    facility_geo = facility_geo.sort_values("施設評価スコア", ascending=False)

    df.to_csv(outdir / "facility_cleaned.csv", index=False, encoding="utf-8-sig")
    facility_geo.to_csv(outdir / "facility_geoeval.csv", index=False, encoding="utf-8-sig")
    area.to_csv(outdir / "medical_area_summary.csv", index=False, encoding="utf-8-sig")
    area.to_csv(outdir / "medical_area_evaluation.csv", index=False, encoding="utf-8-sig")
    area.head(10).to_csv(outdir / "top10_medical_areas.csv", index=False, encoding="utf-8-sig")

    map1 = build_facility_leaflet_html(facility_geo, "救急車の受入件数（年間）", "施設別 救急受入件数マップ")
    map2 = build_facility_leaflet_html(facility_geo, "構造スコア偏差値", "施設別 構造スコア偏差値マップ")
    (outdir / "map_facility_emergency.html").write_text(map1, encoding="utf-8")
    (outdir / "map_facility_structure.html").write_text(map2, encoding="utf-8")

    print(f"分析完了: {outdir}")
    print(" - facility_cleaned.csv")
    print(" - facility_geoeval.csv")
    print(" - medical_area_summary.csv")
    print(" - medical_area_evaluation.csv")
    print(" - top10_medical_areas.csv")
    print(" - map_facility_emergency.html")
    print(" - map_facility_structure.html")


if __name__ == "__main__":
    main()
