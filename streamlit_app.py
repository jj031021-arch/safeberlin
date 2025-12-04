import streamlit as st
import pandas as pd
import folium
import os  # <--- 이 줄 추가

# ... (다른 import 들) ...

# [디버깅용 코드] 앱 맨 위에 이 코드를 잠시 넣어보세요!
st.write("📂 현재 폴더에 있는 파일 목록:", os.listdir('.'))
