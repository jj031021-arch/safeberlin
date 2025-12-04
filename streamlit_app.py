import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import requests
import google.generativeai as genai
# Google Maps 라이브러리는 Geocoding(주소찾기)용으로만 유지하고, 장소 검색은 무료인 OSM을 씁니다.
import googlemaps 

# ---------------------------------------------------------
# 1. 설정 및 API 키 로드
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="베를린 풀코스 가이드")

GMAPS_API_KEY = st.secrets.get("google_maps_api_key", "")
GEMINI_API_KEY = st.secrets.get("gemini_api_key", "")

# 클라이언트 초기화
gmaps = None
if GMAPS_API_KEY:
    try:
        gmaps = googlemaps.Client(key=GMAPS_API_KEY)
    except:
        pass

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except:
        pass

# ---------------------------------------------------------
# 2. 무료 데이터 소스 (OpenStreetMap) 함수
# ---------------------------------------------------------
@st.cache_data
def get_osm_places(category, lat, lng, radius_m=2000):
    """
    구글 대신 OpenStreetMap(Overpass API)을 사용하여 제한 없이 장소를 가져옵니다.
    """
    overpass_url = "http://overpass-api.de/api/interpreter"
    
    # OSM 태그 설정
    if category == 'restaurant':
        tag = '["amenity"="restaurant"]'
    elif category == 'hotel':
        tag = '["tourism"="hotel"]'
    elif category == 'tourism':
        tag = '["tourism"~"attraction|museum|artwork|viewpoint"]'
    else:
        return []

    # 쿼리 작성 (반경 내 검색)
    query = f"""
    [out:json];
    (
      node{tag}(around:{radius_m},{lat},{lng});
    );
    out body;
    """
    
    try:
        response = requests.get(overpass_url, params={'data': query})
        data = response.json()
        
        results = []
        for element in data['elements']:
            if 'tags' in element and 'name' in element['tags']:
                results.append({
                    "name": element['tags']['name'],
                    "lat": element['lat'],
                    "lng": element['lon'],
                    "type": category,
                    "cuisine": element['tags'].get('cuisine', 'General') # 음식 종류
                })
        return results
    except Exception as e:
        return []

@st.cache_data
def load_crime_data(csv_file):
    try:
        df = pd.read_csv(csv_file, on_bad_lines='skip')
        if 'District' not in df.columns: return pd.DataFrame()
        if 'Year' in df.columns:
            latest_year = df['Year'].max()
            df = df[df['Year'] == latest_year]
        numeric_cols = df.select_dtypes(include=['number']).columns
        cols_to_sum = [c for c in numeric_cols if c not in ['Year', 'Code', 'District', 'Location']]
        df['Total_Crime'] = df[cols_to_sum].sum(axis=1)
        return df.groupby('District')['Total_Crime'].sum().reset_index()
    except:
        return pd.DataFrame()

def get_gemini_response(prompt):
    if not GEMINI_API_KEY: return "API 키가 필요합니다."
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        return response.text
    except: return "AI 응답 오류"

# ---------------------------------------------------------
# 3. 여행 코스 데이터 (6테마 x 6장소) - 상세 설명
# ---------------------------------------------------------
courses = {
    "🌳 Theme 1: 숲과 힐링 (티어가르텐)": [
        {"name": "1. 전승기념탑 (Siegessäule)", "lat": 52.5145, "lng": 13.3501, "type": "view", "desc": "베를린 전경이 한눈에 보이는 황금 천사상"},
        {"name": "2. 티어가르텐 산책", "lat": 52.5135, "lng": 13.3575, "type": "walk", "desc": "도심 속 거대한 허파, 맑은 공기 마시기"},
        {"name": "3. Cafe am Neuen See", "lat": 52.5076, "lng": 13.3448, "type": "food", "desc": "호수 바로 앞, 피자와 맥주가 맛있는 비어가든"},
        {"name": "4. 베를린 동물원/수족관", "lat": 52.5079, "lng": 13.3377, "type": "view", "desc": "세계 최대 종을 보유한 역사 깊은 동물원"},
        {"name": "5. Monkey Bar", "lat": 52.5049, "lng": 13.3353, "type": "food", "desc": "동물원 원숭이를 내려다보며 칵테일 한잔 (25hours 호텔 루프탑)"},
        {"name": "6. 카이저 빌헬름 교회", "lat": 52.5048, "lng": 13.3350, "type": "view", "desc": "전쟁의 참상을 기억하기 위해 부서진 채 보존된 교회"}
    ],
    "🎨 Theme 2: 예술과 고전 (박물관 섬)": [
        {"name": "1. 베를린 돔", "lat": 52.5190, "lng": 13.4010, "type": "view", "desc": "웅장한 돔 지붕 위에서 보는 시내 뷰"},
        {"name": "2. 구 국립 미술관", "lat": 52.5208, "lng": 13.3982, "type": "view", "desc": "그리스 신전 같은 외관과 19세기 회화"},
        {"name": "3. 제임스 사이먼 공원", "lat": 52.5213, "lng": 13.4005, "type": "walk", "desc": "슈프레 강변에 앉아 쉬어가는 현지인 핫플"},
        {"name": "4. Hackescher Hof", "lat": 52.5246, "lng": 13.4020, "type": "view", "desc": "아르누보 양식의 아름다운 8개 안뜰"},
        {"name": "5. Monsieur Vuong", "lat": 52.5244, "lng": 13.4085, "type": "food", "desc": "항상 줄 서서 먹는 전설적인 베트남 쌀국수 맛집"},
        {"name": "6. Zeit für Brot", "lat": 52.5265, "lng": 13.4090, "type": "food", "desc": "시나몬 롤(Schnecke)이 입에서 녹는 베이커리"}
    ],
    "🏰 Theme 3: 분단의 역사 (장벽 투어)": [
        {"name": "1. 베를린 장벽 기념관", "lat": 52.5352, "lng": 13.3903, "type": "view", "desc": "장벽이 실제 모습 그대로 보존된 야외 박물관"},
        {"name": "2. Mauerpark (마우어파크)", "lat": 52.5404, "lng": 13.4048, "type": "walk", "desc": "일요일엔 거대한 벼룩시장과 가라오케가 열림"},
        {"name": "3. Prater Beer Garden", "lat": 52.5399, "lng": 13.4101, "type": "food", "desc": "베를린에서 가장 오래된 야외 맥주집"},
        {"name": "4. 체크포인트 찰리", "lat": 52.5074, "lng": 13.3904, "type": "view", "desc": "미군과 소련군이 대치했던 검문소"},
        {"name": "5. Topography of Terror", "lat": 52.5065, "lng": 13.3835, "type": "view", "desc": "나치 비밀경찰 본부 터에 지어진 무료 역사관"},
        {"name": "6. Mall of Berlin", "lat": 52.5106, "lng": 13.3807, "type": "food", "desc": "역사 투어 후 쇼핑과 식사를 해결하는 대형 몰"}
    ],
    "🕶️ Theme 4: 힙스터 성지 (크로이츠베르크)": [
        {"name": "1. 오버바움 다리", "lat": 52.5015, "lng": 13.4455, "type": "view", "desc": "동서를 잇는 붉은 벽돌 다리, 최고의 포토존"},
        {"name": "2. 이스트 사이드 갤러리", "lat": 52.5050, "lng": 13.4397, "type": "walk", "desc": "형제의 키스 그림이 있는 세계 최장 야외 갤러리"},
        {"name": "3. Burgermeister", "lat": 52.5005, "lng": 13.4420, "type": "food", "desc": "다리 밑 공중화장실을 개조해 만든 힙한 버거집"},
        {"name": "4. Markthalle Neun", "lat": 52.5020, "lng": 13.4310, "type": "food", "desc": "목요일엔 스트릿 푸드 마켓이 열리는 실내 시장"},
        {"name": "5. Voo Store", "lat": 52.5005, "lng": 13.4215, "type": "view", "desc": "패션 피플들이 찾는 숨겨진 편집샵"},
        {"name": "6. Landwehr Canal", "lat": 52.4960, "lng": 13.4150, "type": "walk", "desc": "백조를 보며 걷거나 보트를 타는 운하 산책로"}
    ],
    "🛍️ Theme 5: 럭셔리 & 쇼핑 (쿠담)": [
        {"name": "1. KaDeWe 백화점", "lat": 52.5015, "lng": 13.3414, "type": "view", "desc": "유럽 대륙 최대의 백화점, 6층 식품관 필수"},
        {"name": "2. 쿠담 거리", "lat": 52.5028, "lng": 13.3323, "type": "walk", "desc": "베를린의 샹젤리제, 명품 브랜드 거리"},
        {"name": "3. Bikini Berlin", "lat": 52.5055, "lng": 13.3370, "type": "view", "desc": "동물원이 보이는 독특한 컨셉의 쇼핑몰"},
        {"name": "4. C/O Berlin", "lat": 52.5065, "lng": 13.3325, "type": "view", "desc": "사진 예술 전문 미술관"},
        {"name": "5. Schwarzes Café", "lat": 52.5060, "lng": 13.3250, "type": "food", "desc": "24시간 영업하는 예술가들의 아지트 카페"},
        {"name": "6. Savignyplatz", "lat": 52.5060, "lng": 13.3220, "type": "walk", "desc": "고풍스러운 서점과 레스토랑이 많은 광장"}
    ],
    "🌙 Theme 6: 화려한 밤 (미테 & 야경)": [
        {"name": "1. 알렉산더 광장 TV타워", "lat": 52.5208, "lng": 13.4094, "type": "view", "desc": "베를린 가장 높은 곳에서 야경 감상"},
        {"name": "2. 로젠탈러 거리", "lat": 52.5270, "lng": 13.4020, "type": "walk", "desc": "트렌디한 샵과 갤러리가 모인 골목"},
        {"name": "3. Clärchens Ballhaus", "lat": 52.5265, "lng": 13.3965, "type": "food", "desc": "100년 넘은 무도회장에서 식사 (분위기 최고)"},
        {"name": "4. House of Small Wonder", "lat": 52.5240, "lng": 13.3920, "type": "food", "desc": "식물원 같은 인테리어의 유명 브런치/디너"},
        {"name": "5. Friedrichstadt-Palast", "lat": 52.5235, "lng": 13.3885, "type": "view", "desc": "라스베가스 스타일의 화려한 쇼 공연장"},
        {"name": "6. 브란덴부르크 문 (야경)", "lat": 52.5163, "lng": 13.3777, "type": "walk", "desc": "밤에 조명이 켜지면 더 웅장한 랜드마크"}
    ]
}

# ---------------------------------------------------------
# 4. 메인 화면 구성
# ---------------------------------------------------------
st.title("🇩🇪 베를린 풀코스 가이드")
st.caption("OpenStreetMap을 이용해 수많은 장소를 확인하고, 완벽한 여행 코스를 즐기세요.")

# 세션 초기화
if 'reviews' not in st.session_state: st.session_state['reviews'] = {}
if 'messages' not in st.session_state: st.session_state['messages'] = []

# --- 탭 구성 (UI 개선) ---
tab1, tab2, tab3 = st.tabs(["🗺️ 자유 탐험 (모든 장소)", "🚩 추천 코스 (6 Themes)", "💬 여행자 수다방"])

# =========================================================
# TAB 1: 자유 탐험 (OSM 데이터 사용 - 장소 폭발!)
# =========================================================
with tab1:
    col_a, col_b = st.columns([1, 3])
    with col_a:
        st.subheader("지도 필터")
        show_crime = st.toggle("🚨 범죄 위험도", True)
        show_food = st.toggle("🍽️ 식당 (무제한)", True)
        show_tour = st.toggle("📸 관광지 (무제한)", False)
        st.info("지도를 움직여 중심을 바꾸면 해당 위치 주변을 검색합니다.")

    with col_b:
        m1 = folium.Map(location=[52.5200, 13.4050], zoom_start=14)

        # 범죄 레이어
        if show_crime:
            crime_df = load_crime_data("Berlin_crimes.csv")
            if not crime_df.empty:
                folium.Choropleth(
                    geo_data="https://raw.githubusercontent.com/funkeinteraktiv/Berlin-Geodaten/master/berlin_bezirke.geojson",
                    data=crime_df,
                    columns=["District", "Total_Crime"],
                    key_on="feature.properties.name",
                    fill_color="YlOrRd",
                    fill_opacity=0.4,
                    line_opacity=0.2,
                    name="범죄"
                ).add_to(m1)

        # OSM 데이터 가져오기 (베를린 중심 기준 3km)
        # 실제 앱에서는 지도 중심좌표를 받아오면 좋으나, 여기선 고정값 주변 검색
        if show_food:
            foods = get_osm_places('restaurant', 52.5200, 13.4050, 3000)
            fg_food = folium.FeatureGroup(name="식당")
            for f in foods:
                # OSM은 별점이 없으므로 이름과 종류만 표시
                popup_html = f"<b>{f['name']}</b><br>{f['cuisine']}"
                folium.CircleMarker(
                    location=[f['lat'], f['lng']],
                    radius=4,
                    color='green',
                    fill=True,
                    popup=popup_html
                ).add_to(fg_food)
            fg_food.add_to(m1)
        
        if show_tour:
            tours = get_osm_places('tourism', 52.5200, 13.4050, 3000)
            fg_tour = folium.FeatureGroup(name="관광")
            for t in tours:
                folium.CircleMarker(
                    location=[t['lat'], t['lng']],
                    radius=5,
                    color='purple',
                    fill=True,
                    popup=t['name']
                ).add_to(fg_tour)
            fg_tour.add_to(m1)

        st_folium(m1, width="100%", height=500)

# =========================================================
# TAB 2: 추천 코스 (예쁜 UI, 6테마 x 6장소)
# =========================================================
with tab2:
    st.subheader("🌟 테마별 완벽 코스 추천")
    
    # 탭으로 코스 선택
    theme_names = list(courses.keys())
    selected_theme = st.radio("테마를 선택하세요:", theme_names, horizontal=True)
    
    # 선택된 코스 데이터
    c_data = courses[selected_theme]
    
    # 레이아웃: 왼쪽(지도) / 오른쪽(상세 설명)
    c_col1, c_col2 = st.columns([1.5, 1])
    
    with c_col1:
        # 코스 지도
        m2 = folium.Map(location=[c_data[2]['lat'], c_data[2]['lng']], zoom_start=13)
        points = []
        for item in c_data:
            loc = [item['lat'], item['lng']]
            points.append(loc)
            
            # 아이콘 색상 구분
            color = 'orange' if item['type'] == 'food' else 'blue'
            icon = 'cutlery' if item['type'] == 'food' else 'camera'
            
            folium.Marker(
                loc, 
                popup=item['name'],
                tooltip=item['name'],
                icon=folium.Icon(color=color, icon=icon)
            ).add_to(m2)
            
        # 경로 연결
        folium.PolyLine(points, color="red", weight=4, opacity=0.7).add_to(m2)
        st_folium(m2, width="100%", height=500)
        
    with c_col2:
        st.markdown(f"### {selected_theme}")
        st.markdown("---")
        # 깔끔하게 Expander(접이식) 메뉴로 표시
        for item in c_data:
            icon_str = "🍽️" if item['type'] == 'food' else "📸" if item['type'] == 'view' else "🚶"
            with st.expander(f"{icon_str} {item['name']}", expanded=True):
                st.write(f"_{item['desc']}_")
                # 구글 검색 링크
                q = item['name'].replace(" ", "+") + "+Berlin"
                st.markdown(f"[🔍 구글 상세정보 보기](https://www.google.com/search?q={q})")

# =========================================================
# TAB 3: 수다방 & AI (삭제 기능 추가)
# =========================================================
with tab3:
    col_chat, col_ai = st.columns([1, 1])
    
    # --- 채팅방 (삭제 기능 구현) ---
    with col_chat:
        st.subheader("💬 여행자 수다방")
        
        # 채팅방 선택
        # 모든 코스의 장소 이름을 리스트로 수집
        all_places = []
        for k, v in courses.items():
            for p in v:
                all_places.append(p['name'].split(". ")[1]) # 번호 제외한 이름만
        
        sel_place = st.selectbox("어느 장소 이야기인가요?", sorted(list(set(all_places))))
        
        # 메시지 저장소 초기화
        if sel_place not in st.session_state['reviews']:
            st.session_state['reviews'][sel_place] = []

        # 입력 폼
        with st.form("msg_form", clear_on_submit=True):
            txt = st.text_input("내용 입력")
            if st.form_submit_button("등록"):
                st.session_state['reviews'][sel_place].append(txt)
                st.rerun()
        
        # 메시지 출력 및 삭제 기능
        st.write("---")
        # 인덱스(i)를 사용하여 삭제 버튼 식별
        for i, msg in enumerate(st.session_state['reviews'][sel_place]):
            c1, c2 = st.columns([8, 1])
            with c1:
                st.info(f"🗣️ {msg}")
            with c2:
                # 삭제 버튼 (각 메시지마다 고유 키 할당)
                if st.button("🗑️", key=f"del_{sel_place}_{i}"):
                    del st.session_state['reviews'][sel_place][i]
                    st.rerun()

    # --- AI 비서 ---
    with col_ai:
        st.subheader("🤖 Gemini 가이드")
        chat_area = st.container(height=400)
        
        for msg in st.session_state['messages']:
            chat_area.chat_message(msg['role']).write(msg['content'])
            
        if prompt := st.chat_input("질문하세요 (예: 3일차 일정 추천해줘)"):
            st.session_state['messages'].append({"role": "user", "content": prompt})
            chat_area.chat_message("user").write(prompt)
            
            with chat_area.chat_message("assistant"):
                resp = get_gemini_response(prompt)
                st.write(resp)
            st.session_state['messages'].append({"role": "assistant", "content": resp})
