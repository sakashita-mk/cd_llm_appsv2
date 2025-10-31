# tab2_plan.py
from __future__ import annotations
import streamlit as st
import pandas as pd

def render():
    st.subheader("構成方針提示（Tab2）")

    final_plan = st.session_state.get("final_plan")
    if not final_plan:
        st.info("Tab1で『OK（Tab2へ反映）』すると、ここに構成方針が表示されます。")
        return

    # --- 基本情報 ---
    st.markdown("### 基本情報")
    st.write(f'**ユースケース名**：{final_plan.get("usecase_name", "")}')
    st.write(f'**観測目的**：{final_plan.get("observation_objective", "")}')

    # --- 要求指標 ---
    st.markdown("---")
    st.markdown("### 要求指標（ターゲット）")
    bands = ", ".join(final_plan.get("observation_bands", [])) or "（指定なし）"
    st.write(f'**観測バンド**：{bands}')
    st.write(f'**空間分解能（目標）**：{final_plan.get("spatial_resolution_target_m", "")} m')
    st.write(f'**観測頻度（目標）**：{final_plan.get("revisit_target_days", "")} 日')

    # --- 推奨衛星（候補一覧） ---
    st.markdown("---")
    st.markdown("### 推奨衛星（候補）")
    recs = final_plan.get("recommended_satellites", [])
    if recs:
        cols = [
            "mission_name","constellation","instrument_name","operator",
            "sensor_type","spectral_band","spatial_resolution_m","revisit",
            "coverage","data_access","official_url","notes"
        ]
        # 存在する列だけに絞る
        cols = [c for c in cols if any(c in r for r in recs)]
        df = pd.DataFrame(recs)[cols]
        st.dataframe(df, use_container_width=True)
    else:
        st.write("（該当候補なし）")

    # --- 提案構成 ---
    st.markdown("---")
    st.markdown("### 提案構成（例）")
    proposed = final_plan.get("proposed_configuration", [])
    st.write(" / ".join(proposed) if proposed else "（未構成）")

    # --- 補足説明 ---
    st.markdown("### 補足説明")
    st.write(final_plan.get("supplemental_note", ""))

    # --- JSON確認（開発者向け） ---
    with st.expander("最終プラン（JSON／デバッグ用）"):
        st.json(final_plan)
