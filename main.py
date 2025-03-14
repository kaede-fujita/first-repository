import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from shapely.geometry import Point
from streamlit_folium import st_folium
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
import numpy as np

# --- セッションステートの初期化 ---
st.set_page_config(layout="wide")

if "user_coords" not in st.session_state:
    st.session_state["user_coords"] = (33.85, 132.75)  # デフォルト起点（松山市）
if "shelter_selected" not in st.session_state:
    st.session_state["shelter_selected"] = set()
if "num_vehicles" not in st.session_state:
    st.session_state["num_vehicles"] = 1
if "route_distance" not in st.session_state:
    st.session_state["route_distance"] = None
if "route_time" not in st.session_state:
    st.session_state["route_time"] = None
if "route_data" not in st.session_state:
    st.session_state["route_data"] = []

# --- データの読み込み ---
@st.cache_data
def load_shapefile(file_path):
    return gpd.read_file(file_path)

@st.cache_data
def load_shelter_data(file_path):
    df = pd.read_excel(file_path, sheet_name="愛媛県_避難所一覧")
    df = df.rename(columns={"施設名": "避難所", "市区町村コード": "市区町村", "A32_004": "学校区", "緯度": "Latitude", "経度": "Longitude", "施設コ": "施設コード"})
    df = df[["市区町村", "学校区", "避難所", "施設コード", "Latitude", "Longitude"]]
    return df

shp_file_path = 'resources/A32-23_38_GML/A32-23_38.shp'
school_districts = load_shapefile(shp_file_path)

shelter_excel_path = 'resources/愛媛県_避難所一覧.xlsx'
shelter_data = load_shelter_data(shelter_excel_path)

# --- データ前処理 ---
shelter_data = shelter_data.loc[:, ~shelter_data.columns.duplicated()]  # ✅ カラムの重複削除
shelter_data['学校区'] = shelter_data['学校区'].astype(str).str.strip()  # ✅ 文字列の前後の空白削除
shelter_data = shelter_data.dropna(subset=['学校区'])  # ✅ NaNデータの削除

# ✅ 学校区ごとに重複したデータを削除（避難所リストが被っていないか確認）
shelter_data = shelter_data.drop_duplicates(subset=["学校区", "避難所"])

# --- UI 設定 ---
st.markdown('<h2>避難所巡回計画 Webアプリ</h2>', unsafe_allow_html=True)

# --- 🚗 起点の設定（緯度・経度入力） ---
st.markdown("### 起点の設定（緯度・経度）")
lat_input = st.number_input("緯度", value=st.session_state["user_coords"][0], format="%.6f")
lon_input = st.number_input("経度", value=st.session_state["user_coords"][1], format="%.6f")

if st.button("起点を設定"):
    st.session_state["user_coords"] = (lat_input, lon_input)
    st.success(f"起点を {lat_input}, {lon_input} に設定しました。")

# --- UIの上段（地図を上部に配置） ---
st.markdown("### 避難所マップ")
map_ = folium.Map(location=st.session_state["user_coords"], zoom_start=12)

# 起点のマーカー（緑）
folium.Marker(
    st.session_state["user_coords"],
    icon=folium.Icon(color="green"),
    popup="起点"
).add_to(map_)

# 避難所のマーカー（選択状態で色を変更）
for _, row in shelter_data.iterrows():
    color = "blue"
    if row['避難所'] in st.session_state["shelter_selected"]:
        color = "red"
    folium.Marker(
        [row["Latitude"], row["Longitude"]],
        popup=row["避難所"],
        icon=folium.Icon(color=color)
    ).add_to(map_)

map_click = st_folium(map_, height=500, width="100%")

if map_click["last_clicked"]:
    st.session_state["user_coords"] = (map_click["last_clicked"]["lat"], map_click["last_clicked"]["lng"])
    st.success(f"起点が {map_click['last_clicked']['lat']}, {map_click['last_clicked']['lng']} に設定されました。")

# --- UIの下段（学校区選択、巡回計画） ---
top_columns = st.columns([60, 40], gap="small")

with top_columns[1]:
    st.markdown("### 中学校区を選択")
    school_district_names = school_districts["A32_004"].astype(str).unique()
    school_district = st.selectbox('学校区を選択してください', school_district_names)

    filtered_shelters = shelter_data[shelter_data['学校区'] == school_district].reset_index(drop=True)

    st.markdown(f'### {school_district}区の避難所一覧')

    for _, row in filtered_shelters.iterrows():
        shelter_name = row['避難所']
        checked = shelter_name in st.session_state["shelter_selected"]
        new_checked = st.checkbox(shelter_name, value=checked)

        if new_checked:
            st.session_state["shelter_selected"].add(shelter_name)
        else:
            st.session_state["shelter_selected"].discard(shelter_name)

    st.markdown("### 巡回車両の台数")
    st.session_state["num_vehicles"] = st.slider("巡回車両の数", 1, 25, 1)

# --- 🚗 巡回計画の実行 ---
if st.button("巡回計画を実行"):
    def solve_vrp(start_point, shelters, num_vehicles):
        if shelters.empty:
            st.warning("避難所を選択してください。")
            return None

        locations = [start_point] + [(row['Latitude'], row['Longitude']) for _, row in shelters.iterrows()]
        num_locations = len(locations)

        # ✅ 距離行列の作成
        distance_matrix = np.zeros((num_locations, num_locations), dtype=int)
        for i in range(num_locations):
            for j in range(num_locations):
                if i != j:
                    distance_matrix[i][j] = int(Point(locations[i]).distance(Point(locations[j])) * 100000)

        # ✅ OR-Tools 用のマネージャー
        manager = pywrapcp.RoutingIndexManager(num_locations, num_vehicles, 0)
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return distance_matrix[from_node][to_node]

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # ✅ 各車両を必ず起点に戻す
        for vehicle_id in range(num_vehicles):
            routing.SetFixedCostOfAllVehicles(1000)

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        search_parameters.time_limit.seconds = 30

        solution = routing.SolveWithParameters(search_parameters)

        if solution:
            total_distance = solution.ObjectiveValue() / 1000  # ✅ 距離を km に変換
            total_stop_time = 0  # ✅ 追加の待機時間（避難所ごとに1時間）
            st.session_state["route_data"] = []

            for vehicle_id in range(num_vehicles):
                index = routing.Start(vehicle_id)
                route = []
                while not routing.IsEnd(index):
                    node = manager.IndexToNode(index)
                    route.append(locations[node])
                    index = solution.Value(routing.NextVar(index))

                # ✅ OR-Toolsに起点復帰を強制
                route.append(start_point)

                # ✅ 訪問した避難所数をカウント（起点と復帰地点を除外）
                num_stops = len(route) - 2
                total_stop_time += num_stops * 60  # ✅ 避難所ごとに60分追加

                st.session_state["route_data"].append(route)

            # ✅ 走行時間（分）+ 避難所待機時間
            st.session_state["route_distance"] = total_distance
            travel_time = round(total_distance / 0.667, 2)  # **km → 分換算**
            st.session_state["route_time"] = travel_time + total_stop_time  # **待機時間を追加**

    solve_vrp(st.session_state["user_coords"], shelter_data[shelter_data["避難所"].isin(st.session_state["shelter_selected"])] , st.session_state["num_vehicles"])

# ✅ ルート描画
for route in st.session_state["route_data"]:
    folium.PolyLine(route, color="blue", weight=2.5, opacity=1).add_to(map_)
st_folium(map_, height=500, width="100%")

# ✅ 総移動距離と推定移動時間の表示（kmに修正 & 訪問ごとに1時間追加）
st.metric(label="総移動距離 (km)", value=st.session_state["route_distance"])
st.metric(label="推定移動時間 (分)", value=st.session_state["route_time"])
