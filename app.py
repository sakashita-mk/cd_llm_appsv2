import streamlit as st
st.set_page_config(page_title="宇宙事業デザインセッションプラットフォーム（仮）, layout="wide")
st.title("宇宙事業デザインセッションプラットフォーム（仮）")
t1, t2, t3 = st.tabs(["Tab1: ユースケース入力", "Tab2: 構成方針提示", "Tab3: 統合プラン（Under Construction）"])
with t1:
    import tab1_usecase as T1; T1.render()
with t2:
    import tab2_plan as T2; T2.render()
with t3:
    import tab3_plan as T3; T3.render()
