# tab2_plan.py
# Tab2: Tab1の観測設計ドラフト（confirmed_plan）を受け取り、
#       センサ構成/衛星候補/運用・処理/リスク/次アクション等の「構成方針」をLLMで提案するタブ
import os
import json
import re
from typing import Dict, Any, List, Optional

import streamlit as st
from dotenv import load_dotenv
from groq import Groq

# ========= Env / Secrets =========
load_dotenv()

API_KEY = st.secrets.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
MODEL   = st.secrets.get("GROQ_MODEL")   or os.getenv("GROQ_MODEL")   or "llama-3.1-8b-instant"
client  = Groq(api_key=API_KEY) if API_KEY else None


# ========= Helpers =========
def _inject_css():
    st.markdown(
        """
<style>
html, body, [class*="css"] { font-size: 16px; }
h1 { font-size: 2rem; }
h2 { font-size: 1.5rem; margin-top: .5rem; }
h3 { font-size: 1.25rem; margin-top: .5rem; }
ul, ol { line-height: 1.6; }
.stButton>button { padding: .6rem 1rem; font-size: 1rem; }
.block-container { padding-top: .75rem; }
</style>
        """,
        unsafe_allow_html=True,
    )


def _extract_json_block(text: str) -> str:
    """```json ... ``` もしくは最初の { ... } を抽出（簡易ネスト対応）"""
    if not text:
        return "{}"
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if m:
        return m.group(1).strip()
    start = text.find("{")
    if start < 0:
        return "{}"
    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1].strip()
    return "{}"


def _json_loads_safe(s: str) -> Dict[str, Any]:
    try:
        return json.loads(s)
    except Exception:
        return {}


def _prompt_messages(plan: Dict[str, Any]) -> List[Dict[str, str]]:
    """Tab1のconfirmed_planを入力に、構成方針（JSON）を生成するプロンプト。"""
    usecase = plan.get("usecase", "")
    goal = plan.get("goal", "")
    req  = plan.get("requirements", {})
    actions = req.get("actions", [])
    bands   = req.get("bands", "")
    gsd_m   = req.get("gsd_m", None)
    revisit = req.get("revisit_days", None)

    sys = (
        "あなたはリモートセンシングの観測設計アーキテクトです。"
        "与えられた観測要件（バンド/解像度/更新間隔/やること）を満たすための"
        "『構成方針』を簡潔にまとめてください。"
        "出力は日本語の短い要約のあと、必ず有効なJSONオブジェクトで返します。"
    )

    usr = f"""前提:
- ユースケース: {usecase}
- 観測目的: {goal}
- 観測で実施すること（actions）: {actions}
- 希望バンド: {bands}
- 目標解像度[g/m]: {gsd_m}
- 目標更新間隔[日]: {revisit}

出力形式:
1) まず人間可読で2〜4行の短い要約
2) その後にJSONを1つだけ。スキーマ:
{{
  "stack": {{
    "sensors": [
      {{
        "type": "optical|sar|thermal|other",
        "bands": "例: 可視・近赤外・短波赤外・熱赤外",
        "gsd_target_m": 10,
        "revisit_target_days": 3,
        "usage": "このセンサで何を満たすか（例: 植生/水分/温度/洪水等）"
      }}
    ],
    "satellite_candidates": [
      {{
        "name": "例: Sentinel-2 / Landsat-8 / ALOS-2 / WorldView-3 など",
        "why": "候補とする理由（バンド/解像度/頻度/コスト/雲の影響等）"
      }}
    ],
    "complements": {{
      "cloud_mitigation": "雲対策（SAR/高頻度/季節考慮等）",
      "alternative_layers": ["UAV","HAPS","地上IoTセンサ など必要に応じて"],
      "data_sources": ["衛星オープンデータ/商用/気象データ/地図/GIS 等"]
    }}
  }},
  "processing": {{
    "preprocess": ["幾何補正","雲・影マスク","再サンプリング","合成等"],
    "features": ["NDVI/NDWI/水温/土壌水分 proxies等"],
    "fusion": "複数センサ/外部データの融合方針（空間/時間/特徴レベル）",
    "qa": "品質管理/基準点/地上真値の扱い"
  }},
  "deliverables": ["出力物（例: 被害推定マップ","集計CSV","ダッシュボード）"],
  "risks": ["雲被り","季節性/観測ギャップ","地上真値不足","データ取得制限","コスト等"],
  "next_actions": ["小規模PoCの設計","必要データの収集計画","評価指標の確定"],
  "assumptions": ["前提条件（対象地域/期間/作物や地物など）"]
}}

注意:
- JSONの数値は数値型で
- 候補衛星はオープン/商用を混ぜて2〜6件程度で具体名を
- actions/bands/gsd/revisitの整合をとること
- 1000トークン以内
"""
    return [
        {"role": "system", "content": sys},
        {"role": "user", "content": usr},
    ]


# ========= Main =========
def render():
    _inject_css()
    st.header("構成方針提示（Tab2）")

    plan = st.session_state.get("confirmed_plan")
    if not plan:
        st.info("Tab1で『OK（次へ）』を押すと、ここに構成方針が表示されます。")
        return

    # 生成/確定/クリア ボタン行
    col_gen, col_ok, col_clear = st.columns([1, 1, 1])

    with col_gen:
        if not client:
            st.warning("GROQ_API_KEY が未設定です（Manage app → Settings → Secrets）。LLM生成は無効。")
        if st.button("構成方針を生成（LLM）", type="primary", disabled=(client is None)):
            with st.spinner("LLMで構成方針案を作成中..."):
                try:
                    resp = client.chat.completions.create(
                        model=MODEL,
                        temperature=0.1,
                        max_tokens=1100,
                        messages=_prompt_messages(plan),
                    )
                    text = resp.choices[0].message.content or ""
                    data = _json_loads_safe(_extract_json_block(text))
                    st.session_state["design_plan_draft"] = data
                except Exception as e:
                    st.error(f"Groq API呼び出しエラー: {e}")

    with col_ok:
        if st.session_state.get("design_plan_draft") and st.button("OK（確定）", type="secondary"):
            st.session_state["design_plan_confirmed"] = st.session_state["design_plan_draft"]
            st.success("構成方針案を確定しました。")

    with col_clear:
        if st.button("修正が必要", type="secondary"):
            st.session_state.pop("design_plan_draft", None)
            st.session_state.pop("design_plan_confirmed", None)
            st.success("Tab2の出力を削除しました。")
            st.rerun()

    # 表示対象の選択：確定済みがあれば優先
    design: Optional[Dict[str, Any]] = (
        st.session_state.get("design_plan_confirmed")
        or st.session_state.get("design_plan_draft")
    )

    if not design:
        st.stop()

    # ===== 人間可読ビュー =====
    st.subheader("構成方針（LLM案）")

    stack = design.get("stack", {})
    sensors = stack.get("sensors", [])
    sats = stack.get("satellite_candidates", [])
    complements = stack.get("complements", {})

    processing = design.get("processing", {})
    deliverables = design.get("deliverables", [])
    risks = design.get("risks", [])
    next_actions = design.get("next_actions", [])
    assumptions = design.get("assumptions", [])

    # Stack
    st.markdown("### センサ構成（Stack）")
    if sensors:
        for i, s in enumerate(sensors, 1):
            st.markdown(
                f"- **[{i}] {s.get('type','(type)')}**｜"
                f"バンド: {s.get('bands','-')}｜"
                f"GSD目標[m]: {s.get('gsd_target_m','-')}｜"
                f"更新間隔目標[日]: {s.get('revisit_target_days','-')}  \n"
                f"  用途: {s.get('usage','-')}"
            )
    else:
        st.markdown("- （センサ構成が未提示です）")

    st.markdown("#### 衛星候補")
    if sats:
        for s in sats:
            st.markdown(f"- **{s.get('name','(名称不明)')}**：{s.get('why','')}")
    else:
        st.markdown("- （候補なし）")

#    st.markdown("#### 補完・取得戦略")
#    st.markdown(f"- 雲対策: {complements.get('cloud_mitigation', '（未記載）')}")
#    if complements.get("alternative_layers"):
#        st.markdown("- 代替/補完レイヤー: " + ", ".join(complements.get("alternative_layers")))
#    if complements.get("data_sources"):
#        st.markdown("- データソース: " + ", ".join(complements.get("data_sources")))

#    # Processing
#    st.markdown("### データ処理・融合・QA")
#    if processing.get("preprocess"):
#        st.markdown("- 前処理: " + " / ".join(processing.get("preprocess")))
#    if processing.get("features"):
#        st.markdown("- 特徴量: " + " / ".join(processing.get("features")))
#    if processing.get("fusion"):
#        st.markdown("- 融合: " + str(processing.get("fusion")))
#    if processing.get("qa"):
#        st.markdown("- QA: " + str(processing.get("qa")))

#    # Deliverables
#    st.markdown("### 出力物（Deliverables）")
#    if deliverables:
#        st.markdown("- " + "\n- ".join(deliverables))
#    else:
#        st.markdown("- （未提示）")

    # Risks
#    st.markdown("### リスク＆留意点")
#    if risks:
#        st.markdown("- " + "\n- ".join(risks))
#    else:
#        st.markdown("- （未提示）")

    # Next actions
#    st.markdown("### 次アクション")
#    if next_actions:
#        st.markdown("- " + "\n- ".join(next_actions))
#    else:
#        st.markdown("- （未提示）")

    # Assumptions
#    if assumptions:
#        st.markdown("### 前提条件")
#        st.markdown("- " + "\n- ".join(assumptions))

    # Debug expander
    with st.expander("デバッグ（MODEL / APIキー有無 / JSON原文）", expanded=False):
        st.write("MODEL =", MODEL)
        st.write("Has GROQ_API_KEY =", bool(API_KEY))
        st.code(json.dumps(design, ensure_ascii=False, indent=2), language="json")
