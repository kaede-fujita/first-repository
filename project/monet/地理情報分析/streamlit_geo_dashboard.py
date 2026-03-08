#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
AREA_CSV = BASE_DIR / "output" / "medical_area_evaluation.csv"
FACILITY_CSV = BASE_DIR / "output" / "facility_geoeval.csv"

st.set_page_config(page_title="医療圏内 医療体制評価ダッシュボード", layout="wide")
st.title("施設緯度経度ベース 医療圏内の医療体制評価")

if not AREA_CSV.exists() or not FACILITY_CSV.exists():
    st.error("先に geo_medical_analysis.py を実行してください。output配下のCSVが見つかりません。")
    st.stop()

area = pd.read_csv(AREA_CSV)
facility = pd.read_csv(FACILITY_CSV)

area_names = sorted([str(x) for x in area["二次医療圏名"].dropna().unique()])
if not area_names:
    st.warning("二次医療圏データが見つかりません。")
    st.stop()

selected_area = st.selectbox("二次医療圏を選択", area_names)
a = area[area["二次医療圏名"] == selected_area].iloc[0]
f = facility[facility["二次医療圏名"] == selected_area].copy()

st.subheader("医療圏サマリー")
col1, col2, col3, col4 = st.columns(4)
col1.metric("施設数", int(a["施設数"]))
col2.metric("救急受入件数（年間）", f"{int(a['救急車受入件数_年間']):,}")
col3.metric("平均最近接距離 (km)", f"{a['平均最近接距離_km']:.2f}" if pd.notna(a["平均最近接距離_km"]) else "NA")
col4.metric("圏内体制評価スコア", f"{a['圏内体制評価スコア']:.2f}" if pd.notna(a["圏内体制評価スコア"]) else "NA")

st.dataframe(
    pd.DataFrame(
        [
            {
                "都道府県": a["都道府県名"],
                "二次医療圏": a["二次医療圏名"],
                "緯度経度あり施設数": a["緯度経度あり施設数"],
                "平均中心距離_km": a["平均中心距離_km"],
                "最大中心距離_km": a["最大中心距離_km"],
                "施設密度_10km2あたり": a["施設密度_10km2あたり"],
                "救急受入上位3施設集中度": a["救急受入上位3施設集中度"],
                "平均構造スコア": a["平均構造スコア"],
                "構造スコア標準偏差": a["構造スコア標準偏差"],
            }
        ]
    ),
    use_container_width=True,
)

st.subheader("施設分布マップ（選択医療圏）")
map_df = f[["医療機関名", "緯度", "経度", "救急車の受入件数（年間）", "構造スコア偏差値"]].dropna(subset=["緯度", "経度"])
if not map_df.empty:
    st.map(map_df.rename(columns={"緯度": "latitude", "経度": "longitude"}), size="救急車の受入件数（年間）")
else:
    st.info("この医療圏に地図表示可能な施設座標がありません。")

st.subheader("施設ランキング（選択医療圏）")
sort_col = st.selectbox("並び替え", ["施設評価スコア", "救急車の受入件数（年間）", "構造スコア偏差値", "中心距離_km"])
ascending = sort_col == "中心距離_km"
view = f.sort_values(sort_col, ascending=ascending)
st.dataframe(
    view[[
        "医療機関名", "住所", "救急車の受入件数（年間）", "医師 常勤", "看護師 常勤",
        "診療科対応数", "高度機器保有数", "構造スコア偏差値", "中心距離_km", "施設評価スコア"
    ]],
    use_container_width=True,
)
