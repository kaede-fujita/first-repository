from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st


APP_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = APP_DIR.parents[3]
DEFAULT_DEMAND_CSV = WORKSPACE_DIR / "soars/logs/test/test8/results/demand_geo_daily.csv"
DEFAULT_RESIDENTS_CSV = WORKSPACE_DIR / "soars/src/test/test8/residents_microdata.csv"
DEFAULT_FACILITIES_CSV = WORKSPACE_DIR / "soars/src/test/test8/facilities_kako_iryoken.csv"

LOG_SUMMARY_JSON = APP_DIR / "streamlit_summary.json"
LOG_FILTERED_CSV = APP_DIR / "streamlit_filtered_cells.csv"

AGE_GROUPS = ["All", "0-17", "18-39", "40-64", "65-74", "75+"]
MODE_KEYS = ["SELF_DRIVE", "FAMILY_CAR", "PUBLIC_TRANSPORT", "TAXI"]
MODE_LABELS = {
    "SELF_DRIVE": "自分で運転",
    "FAMILY_CAR": "家族の車",
    "PUBLIC_TRANSPORT": "公共交通",
    "TAXI": "タクシー",
}
PRESET_BINS = {
    "0-4分": (0.0, 4.9999),
    "5-9分": (5.0, 9.9999),
    "10-19分": (10.0, 19.9999),
    "20-29分": (20.0, 29.9999),
    "30分以上": (30.0, float("inf")),
}


def weighted_summary(df: pd.DataFrame, by: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[by, "平均アクセス時間(分)", "平均年齢(歳)", "対象人数"])
    wk = df.copy()
    wk["w_count"] = wk["count"] * wk["n"]
    wk["w_age"] = wk["age_avg"] * wk["n"]
    out = wk.groupby(by, as_index=False).agg(
        w_count=("w_count", "sum"),
        w_age=("w_age", "sum"),
        n=("n", "sum"),
    )
    out["平均アクセス時間(分)"] = out["w_count"] / out["n"]
    out["平均年齢(歳)"] = out["w_age"] / out["n"]
    out["対象人数"] = out["n"].astype(int)
    return out[[by, "平均アクセス時間(分)", "平均年齢(歳)", "対象人数"]]


def round_grid(value: float, grid: float) -> float:
    return round(value / grid) * grid


def age_group(age: int) -> str:
    if age <= 17:
        return "0-17"
    if age <= 39:
        return "18-39"
    if age <= 64:
        return "40-64"
    if age <= 74:
        return "65-74"
    return "75+"


def car_ownership_by_age(age: int) -> float:
    if age <= 17:
        return 0.00
    if age <= 19:
        return 0.25
    if age <= 24:
        return 0.50
    if age <= 29:
        return 0.65
    if age <= 34:
        return 0.80
    if age <= 39:
        return 0.85
    if age <= 44:
        return 0.88
    if age <= 49:
        return 0.90
    if age <= 54:
        return 0.90
    if age <= 59:
        return 0.88
    if age <= 64:
        return 0.85
    if age <= 69:
        return 0.80
    if age <= 74:
        return 0.70
    if age <= 79:
        return 0.55
    return 0.35


def clip(value: float, min_v: float, max_v: float) -> float:
    return max(min_v, min(max_v, value))


def self_drive_probability(age: int, gender_id: int) -> float:
    base = car_ownership_by_age(age)
    if gender_id == 1:
        base += 0.05
    elif gender_id == 2:
        base -= 0.05
    return clip(base, 0.02, 0.90)


def family_car_probability(age: int) -> float:
    if age < 65:
        return 0.22
    if age < 75:
        return 0.35
    if age < 85:
        return 0.50
    return 0.42


def public_transport_probability(age: int, distance_road_km: float) -> float:
    age_boost = 0.20 if age >= 75 else 0.10
    distance_penalty = max(0.0, distance_road_km - 18.0) * 0.015
    return clip(0.45 + age_boost - distance_penalty, 0.10, 0.80)


def access_time_by_mode_minutes(distance_road_km: float) -> dict[str, float]:
    t_self = (distance_road_km / 28.0 + 0.08) * 60.0
    t_family = (distance_road_km / 28.0 + 0.10) * 60.0
    t_public = ((distance_road_km * 1.25) / 18.0 + 0.35) * 60.0
    t_taxi = (distance_road_km / 24.0 + 0.10) * 60.0
    return {
        "SELF_DRIVE": t_self,
        "FAMILY_CAR": t_family,
        "PUBLIC_TRANSPORT": t_public,
        "TAXI": t_taxi,
    }


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_provider_distance_km(lat: float, lon: float, providers: list[tuple[float, float]]) -> float:
    if not providers:
        return 0.0
    best = float("inf")
    for p_lat, p_lon in providers:
        d = distance_km(lat, lon, p_lat, p_lon)
        if d < best:
            best = d
    return 0.0 if not math.isfinite(best) else best


@st.cache_data(show_spinner=False)
def load_resident_lookup(path_str: str) -> dict[int, tuple[int, int]]:
    path = Path(path_str)
    out: dict[int, tuple[int, int]] = {}
    with path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                pid = int(row.get("person_id", ""))
                age = int(row.get("age", ""))
                gender = int(row.get("gender_id", "-1"))
            except ValueError:
                continue
            out[pid] = (age, gender)
    return out


@st.cache_data(show_spinner=False)
def demand_bounds(path_str: str) -> tuple[float, float, float, float]:
    path = Path(path_str)
    lats: list[float] = []
    lons: list[float] = []
    with path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lats.append(float(row["lat"]))
                lons.append(float(row["lon"]))
            except (ValueError, KeyError):
                continue
    if not lats:
        raise ValueError("需要CSVの緯度経度が読み取れません")
    return min(lats), max(lats), min(lons), max(lons)


@st.cache_data(show_spinner=False)
def load_provider_points(path_str: str, lat_min: float, lat_max: float, lon_min: float, lon_max: float, margin: float = 0.1) -> list[tuple[float, float]]:
    path = Path(path_str)
    rows: list[list[str]] = []
    for enc, err in (
        ("utf-8-sig", "strict"),
        ("cp932", "strict"),
        ("cp932", "ignore"),
        ("shift_jis", "ignore"),
    ):
        try:
            with path.open("r", encoding=enc, errors=err, newline="") as f:
                rows = list(csv.reader(f))
            break
        except UnicodeDecodeError:
            rows = []
    if not rows:
        return []

    points: list[tuple[float, float]] = []
    for row in rows[1:]:
        nums: list[float] = []
        for v in row:
            try:
                nums.append(float(v))
            except (TypeError, ValueError):
                continue
        cand: tuple[float, float] | None = None
        for i in range(len(nums) - 1):
            lat = nums[i]
            lon = nums[i + 1]
            if 30.0 <= lat <= 46.5 and 129.0 <= lon <= 146.5:
                cand = (lat, lon)
        if cand is None:
            continue
        lat, lon = cand
        if (lat_min - margin) <= lat <= (lat_max + margin) and (lon_min - margin) <= lon <= (lon_max + margin):
            points.append(cand)
    return points


@st.cache_data(show_spinner=False)
def aggregate_cells(
    demand_csv: str,
    resident_csv: str,
    facility_csv: str,
    grid_size: float,
) -> pd.DataFrame:
    resident_lookup = load_resident_lookup(resident_csv)
    lat_min, lat_max, lon_min, lon_max = demand_bounds(demand_csv)
    providers = load_provider_points(facility_csv, lat_min, lat_max, lon_min, lon_max, margin=0.1)
    if not providers:
        raise ValueError("医療施設座標が0件です。施設CSVを確認してください。")

    agg: dict[tuple[str, str, float, float], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    ticks: set[int] = set()
    with Path(demand_csv).open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                tick = int(row["tick"])
                src_lat = float(row["lat"])
                src_lon = float(row["lon"])
            except (ValueError, KeyError):
                continue
            ticks.add(tick)
            if row.get("need_medical", "1") not in ("1", "1.0", "true", "True"):
                continue

            try:
                rid = int(row.get("resident_id", ""))
            except ValueError:
                rid = -1
            age, gender_id = resident_lookup.get(rid, (-1, -1))
            if age < 0:
                age = 50
            if gender_id < 0:
                gender_id = 1

            d_direct = nearest_provider_distance_km(src_lat, src_lon, providers)
            d_road = d_direct * 3.0
            _ = self_drive_probability(age, gender_id)
            _ = family_car_probability(age)
            _ = public_transport_probability(age, d_road)
            mode_values = access_time_by_mode_minutes(d_road)

            lat = round_grid(src_lat, grid_size)
            lon = round_grid(src_lon, grid_size)
            g = age_group(age)
            for mode, value in mode_values.items():
                for g2 in ("All", g):
                    k = (mode, g2, lat, lon)
                    agg[k][0] += value
                    agg[k][1] += 1.0
                    agg[k][2] += float(age)

    rows: list[dict[str, float | str | int]] = []
    for (mode, g, lat, lon), (sum_t, n, sum_age) in agg.items():
        if n <= 0:
            continue
        rows.append(
            {
                "mode": mode,
                "age_group": g,
                "lat": lat,
                "lon": lon,
                "count": sum_t / n,
                "n": int(n),
                "age_avg": sum_age / n,
            }
        )
    df = pd.DataFrame(rows)
    df.attrs["num_days"] = len(ticks)
    return df


def combine_selected(df: pd.DataFrame, selected_ages: list[str], selected_modes: list[str]) -> pd.DataFrame:
    if not selected_ages or not selected_modes:
        return pd.DataFrame(columns=["lat", "lon", "count", "n", "age_avg"])

    active_ages = ["All"] if "All" in selected_ages else selected_ages
    target = df[df["mode"].isin(selected_modes) & df["age_group"].isin(active_ages)].copy()
    if target.empty:
        return pd.DataFrame(columns=["lat", "lon", "count", "n", "age_avg"])

    target["w_count"] = target["count"] * target["n"]
    target["w_age"] = target["age_avg"] * target["n"]
    grouped_mode = target.groupby(["mode", "lat", "lon"], as_index=False).agg(
        w_count=("w_count", "sum"),
        w_age=("w_age", "sum"),
        n=("n", "sum"),
    )
    grouped_mode["mode_avg"] = grouped_mode["w_count"] / grouped_mode["n"]
    grouped_mode["mode_age_avg"] = grouped_mode["w_age"] / grouped_mode["n"]

    out = (
        grouped_mode.groupby(["lat", "lon"], as_index=False)
        .agg(
            count=("mode_avg", "mean"),
            age_avg=("mode_age_avg", "mean"),
            n=("n", "sum"),
        )
        .sort_values(["lat", "lon"])
    )
    return out


def apply_preset(df: pd.DataFrame, selected_presets: list[str]) -> pd.DataFrame:
    if df.empty or not selected_presets:
        return df.iloc[0:0]
    mask = pd.Series(False, index=df.index)
    for p in selected_presets:
        lo, hi = PRESET_BINS[p]
        if math.isfinite(hi):
            mask = mask | ((df["count"] >= lo) & (df["count"] <= hi))
        else:
            mask = mask | (df["count"] >= lo)
    return df[mask]


def write_logs(df: pd.DataFrame, selected_ages: list[str], selected_modes: list[str], selected_presets: list[str], num_days: int) -> None:
    summary = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "num_days": num_days,
        "selected_age_layers": selected_ages,
        "selected_modes": selected_modes,
        "selected_presets": selected_presets,
        "cells_after_filter": int(len(df)),
        "avg_access_time_min": float(df["count"].mean()) if not df.empty else None,
        "avg_age": float(df["age_avg"].mean()) if not df.empty else None,
    }
    LOG_SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if df.empty:
        LOG_FILTERED_CSV.write_text("lat,lon,count,n,age_avg\n", encoding="utf-8")
    else:
        df.to_csv(LOG_FILTERED_CSV, index=False, encoding="utf-8")


def main() -> None:
    st.set_page_config(page_title="外来アクセス時間3Dビュー", layout="wide")
    st.title("外来アクセス時間 3Dビュー（Streamlit）")

    st.caption(f"ログ出力先: {APP_DIR}")

    c1, c2 = st.columns(2)
    with c1:
        demand_csv = st.text_input("需要CSV", str(DEFAULT_DEMAND_CSV))
        residents_csv = st.text_input("住民CSV", str(DEFAULT_RESIDENTS_CSV))
    with c2:
        facilities_csv = st.text_input("施設CSV", str(DEFAULT_FACILITIES_CSV))
        grid_size = st.number_input("グリッド幅(度)", min_value=0.001, max_value=0.05, value=0.005, step=0.001, format="%.3f")

    try:
        base_df = aggregate_cells(demand_csv, residents_csv, facilities_csv, grid_size)
    except Exception as e:
        st.error(f"データ集計に失敗しました: {e}")
        return

    num_days = int(base_df.attrs.get("num_days", 0))
    st.write(f"集計期間: {num_days}日累計（全tick）")

    selected_ages = st.multiselect("年齢レイヤ", AGE_GROUPS, default=["All"])
    selected_modes = st.multiselect("移動手段", [MODE_LABELS[m] for m in MODE_KEYS], default=[MODE_LABELS[m] for m in MODE_KEYS])
    selected_mode_keys = [k for k, v in MODE_LABELS.items() if v in selected_modes]
    selected_presets = st.multiselect("時間プリセット", list(PRESET_BINS.keys()), default=["0-4分"])

    # Summary tables (separate from map)
    summary_age_src = base_df[
        base_df["mode"].isin(selected_mode_keys)
        & base_df["age_group"].isin(["0-17", "18-39", "40-64", "65-74", "75+"])
    ].copy()
    age_summary = weighted_summary(summary_age_src, "age_group")
    if not age_summary.empty:
        age_summary["age_group"] = pd.Categorical(age_summary["age_group"], ["0-17", "18-39", "40-64", "65-74", "75+"], ordered=True)
        age_summary = age_summary.sort_values("age_group").reset_index(drop=True)
        age_summary = age_summary.rename(columns={"age_group": "年齢層"})

    active_age_keys = ["All"] if "All" in selected_ages else selected_ages
    summary_mode_src = base_df[
        base_df["mode"].isin(selected_mode_keys)
        & base_df["age_group"].isin(active_age_keys)
    ].copy()
    mode_summary = weighted_summary(summary_mode_src, "mode")
    if not mode_summary.empty:
        mode_summary["mode"] = mode_summary["mode"].map(MODE_LABELS).fillna(mode_summary["mode"])
        mode_summary = mode_summary.rename(columns={"mode": "交通手段"}).reset_index(drop=True)

    st.subheader("外来アクセス時間サマリー（地図とは別）")
    s1, s2 = st.columns(2)
    with s1:
        st.markdown("**年齢別サマリー**")
        if age_summary.empty:
            st.info("年齢別サマリーの表示対象がありません")
        else:
            st.dataframe(age_summary, use_container_width=True)
    with s2:
        st.markdown("**交通手段別サマリー**")
        if mode_summary.empty:
            st.info("交通手段別サマリーの表示対象がありません")
        else:
            st.dataframe(mode_summary, use_container_width=True)

    merged = combine_selected(base_df, selected_ages, selected_mode_keys)
    filtered = apply_preset(merged, selected_presets)
    write_logs(filtered, selected_ages, selected_mode_keys, selected_presets, num_days)

    if filtered.empty:
        st.warning("表示対象データがありません（年齢レイヤ / 移動手段 / プリセットを見直してください）")
        return

    elev_scale = st.slider("バー高さスケール", min_value=20, max_value=300, value=120, step=10)
    opacity = st.slider("透明度", min_value=0.1, max_value=1.0, value=0.65, step=0.05)

    color_expr = [
        [171, 217, 233, 150],
        [224, 243, 248, 160],
        [255, 255, 191, 170],
        [253, 174, 97, 180],
        [215, 25, 28, 200],
    ]

    def row_color(v: float) -> list[int]:
        if v < 5:
            return color_expr[0]
        if v < 10:
            return color_expr[1]
        if v < 20:
            return color_expr[2]
        if v < 30:
            return color_expr[3]
        return color_expr[4]

    vis_df = filtered.copy()
    vis_df["elevation"] = vis_df["count"] * elev_scale
    vis_df["color"] = vis_df["count"].map(row_color)

    view_state = pdk.ViewState(
        latitude=float(vis_df["lat"].mean()),
        longitude=float(vis_df["lon"].mean()),
        zoom=11,
        pitch=50,
        bearing=-20,
    )

    layer = pdk.Layer(
        "ColumnLayer",
        data=vis_df,
        get_position="[lon, lat]",
        get_elevation="elevation",
        elevation_scale=1,
        radius=250,
        get_fill_color="color",
        pickable=True,
        auto_highlight=True,
        opacity=opacity,
    )

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style="light",
        tooltip={
            "html": "<b>平均アクセス時間:</b> {count}分<br/>"
            "<b>平均年齢:</b> {age_avg}歳<br/>"
            "<b>対象人数:</b> {n}人",
            "style": {"backgroundColor": "white", "color": "black"},
        },
    )
    st.pydeck_chart(deck, use_container_width=True)

    st.subheader("集計結果（先頭100件）")
    st.dataframe(
        vis_df[["lat", "lon", "count", "age_avg", "n"]].rename(
            columns={"count": "平均アクセス時間(分)", "age_avg": "平均年齢(歳)", "n": "対象人数"}
        ).head(100),
        use_container_width=True,
    )
    st.caption(f"ログ保存: {LOG_SUMMARY_JSON.name}, {LOG_FILTERED_CSV.name}")


if __name__ == "__main__":
    main()
