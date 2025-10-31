# tab1_usecase.py
from __future__ import annotations
import os, json, re, io
import streamlit as st
from dotenv import load_dotenv
from groq import Groq
from satellites_db import SATELLITES

# ========= 環境変数 & Secrets =========
load_dotenv()
API_KEY = os.getenv("GROQ_API_KEY") or st.secrets.get("GROQ_API_KEY")
MODEL = st.secrets.get("GROQ_MODEL") or os.getenv("GROQ_MODEL") or "llama-3.2-11b-text"
client  = Groq(api_key=API_KEY) if API_KEY else None

# ========= システムプロンプト =========
PROMPT_SYS = (
    "あなたは衛星リモートセンシングの技術コンサルタントです。"
    "ユーザーの自由記述ユースケースを読み、以下のJSONのみで出力してください。"
    "フィールド: {"
    '"usecase_name": string,'
    '"objective": string,'
    '"actions": string[],'
    '"requirements": {'
    '  "bands": string[],'
    '  "spatial_resolution_m_target": number,'
    '  "revisit_days_target": number'
    "}"
    "}"
)

def _prompt_messages(uc_text: str):
    user = (
        "ユースケース:\n"
        f"{uc_text}\n\n"
        "上記を実現するための観測設計を提示してください。\n"
        "- objective: 何を把握・評価（または監視）したいか\n"
        "- actions: 目的達成のために何をするか（例: 植生指数で作物ストレス推定、熱画像で冷害推定、SARで洪水抽出 など）\n"
        "- requirements: 推奨観測バンド（bands）、目標空間分解能[m]、目標観測頻度[日]\n"
        "出力はJSONのみ。説明文は書かないでください。"
    )
    return [
        {"role": "system", "content": PROMPT_SYS},
        {"role": "user", "content": user},
    ]

# ========= ユーティリティ =========
def _extract_json_block(text: str) -> str:
    """バッククォート付きのJSONコードブロックを優先抽出（無ければ全文）"""
    m = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    return (m.group(1) if m else text).strip()

def _json_loads_safe(s: str):
    """最小限の安全ロード。壊れていたらそのまま例外を上げる（デバッグ用に生テキスト表示）"""
    return json.loads(s)

def _parse_min_res(s: str) -> float:
    # 例: "0.31/1.24/3.7" → 0.31, "5–40" → 5, "約 3"→3
    s = (s or "").replace("–", "/").replace("約", "")
    nums = re.findall(r"\d+\.?\d*", s)
    return float(nums[0]) if nums else 9999.0

def _parse_revisit_days(s: str) -> float:
    # 例: "5 日", "< 1 日", "6–12 日", "1 日 (constellation)" → 平均値
    s = (s or "").replace("日", "").replace("<", "").strip()
    parts = re.split(r"[/\-–\s]+", s)
    nums = [float(p) for p in parts if re.match(r"^\d+\.?\d*$", p)]
    return sum(nums) / len(nums) if nums else 9999.0

def _search_satellites(bands, res_target: float, revisit_target: float):
    """ゆるい一致で候補抽出し、目標に近い順に上位を返す"""
    recs = []
    for sat in SATELLITES:
        res = _parse_min_res(sat.get("spatial_resolution_m"))
        rv  = _parse_revisit_days(sat.get("revisit"))
        band_text = (sat.get("spectral_band", "") or "").lower()

        band_ok = all(b.lower() in band_text for b in (bands or [])) if bands else True
        res_ok  = (res <= res_target * 1.5)
        rv_ok   = (rv  <= revisit_target * 1.5)
        if band_ok and res_ok and rv_ok:
            recs.append(sat)

    def score(sat):
        res = _parse_min_res(sat.get("spatial_resolution_m"))
        rv  = _parse_revisit_days(sat.get("revisit"))
        return abs(res - res_target) + abs(rv - revisit_target)

    recs.sort(key=score)
    return recs[:5]

def _json_download_bytes(data: dict) -> bytes:
    buf = io.BytesIO()
    buf.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
    buf.seek(0)
    return buf.read()

# ========= メイン描画 =========
def render():
    st.subheader("ユースケース入力（Tab1）")

    default_uc = (
        "農業保険の損害査定は現地調査に時間とコストがかかり、迅速な支払いが困難。"
        "衛星データを活用して、干ばつや冷害などの被害を評価できるようにしたい。"
    )
    uc_text = st.text_area(
        "ユースケースを自由に記述",
        value=default_uc,
        height=160,
        help="自由記述で課題や目的、期待する効果を書いてください。"
    )

    # セッション初期化
    st.session_state.setdefault("draft_plan", None)

    # 生成ボタン
    col_gen, _ = st.columns([1, 1])
    with col_gen:
        if not client:
            st.warning("GROQ_API_KEY が未設定です（Manage app → Settings → Secrets）。LLM生成は無効。")
        if st.button("下見立てを生成（LLM）", type="primary", disabled=(client is None)):
            with st.spinner("LLMで観測設計の下見立てを作成中..."):
                resp = client.chat.completions.create(
                    model=MODEL,
                    temperature=0.1,
                    max_tokens=1000,
                    messages=_prompt_messages(uc_text),
                )
                text = resp.choices[0].message.content or ""
                try:
                    data = _json_loads_safe(_extract_json_block(text))
                    st.session_state["draft_plan"] = data
                except Exception as e:
                    st.error(f"JSONの解析に失敗しました: {e}")
                    with st.expander("LLM生テキスト（デバッグ用）", expanded=False):
                        st.code(text, language="json")

    draft = st.session_state.get("draft_plan")
    if not draft:
        return

    # ===== 人間可読ビュー =====
    st.markdown("### 下見立て（LLM案・人間可読ビュー）")
    usecase_name = draft.get("usecase_name") or "（名称未設定）"
    objective    = draft.get("objective") or ""
    actions      = draft.get("actions") or []
    req          = draft.get("requirements") or {}
    bands        = req.get("bands") or []
    res_target   = req.get("spatial_resolution_m_target")
    rv_target    = req.get("revisit_days_target")

    st.write(f"**ユースケース名**：{usecase_name}")
    st.write(f"**観測目的**：{objective if objective else '—'}")

    st.markdown("**やること（Actions）**")
    if actions:
        for a in actions:
            st.markdown(f"- {a}")
    else:
        st.write("—")

    st.markdown("**要求指標（ターゲット）**")
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("観測バンド", ", ".join(bands) if bands else "—")
    with m2:
        st.metric("空間分解能 目標 [m]", str(res_target) if res_target is not None else "—")
    with m3:
        st.metric("観測頻度 目標 [日]", str(rv_target) if rv_target is not None else "—")

    # JSONダウンロード
    with st.expander("詳細（JSON／再現用）", expanded=False):
        st.code(json.dumps(draft, ensure_ascii=False, indent=2), language="json")
        st.download_button(
            "この下見立てJSONをダウンロード",
            data=_json_download_bytes(draft),
            file_name=f"draft_plan_{usecase_name}.json",
            mime="application/json",
        )

    # ===== OK / 修正 =====
    ok_col, ng_col = st.columns([1, 1])
    with ok_col:
        if st.button("OK（Tab2へ反映）", type="primary"):
            # 数値フォールバック
            res_f = float(res_target if isinstance(res_target, (int, float)) else 30.0)
            rv_f  = float(rv_target  if isinstance(rv_target,  (int, float)) else 5.0)

            # 候補衛星
            recs = _search_satellites(bands, res_f, rv_f)
            proposed = [f'{r["mission_name"]} / {r["instrument_name"]}' for r in recs[:3]]

            supplemental = (
                "要求された空間分解能・観測頻度・バンド条件に近い衛星を候補抽出。"
                "無償データ（Sentinel/Landsat）を優先しつつ、要件が厳しければ有償のVHR/高頻度コンステを併用します。"
            )

            st.session_state["final_plan"] = {
                "usecase_name": usecase_name,
                "observation_objective": objective,
                "observation_bands": bands,
                "spatial_resolution_target_m": res_f,
                "revisit_target_days": rv_f,
                "recommended_satellites": recs,
                "proposed_configuration": proposed,
                "supplemental_note": supplemental,
            }
            st.success("Tab2に反映しました。「Tab2: 構成方針提示」を開いてください。")

    with ng_col:
        if st.button("修正が必要（下見立てクリア）"):
            st.session_state["draft_plan"] = None
            st.info("下見立てをクリアしました。ユースケースを修正して再生成してください。")
