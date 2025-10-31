# tab1_usecase.py
# Tab1: ユースケース入力 → 観測設計ドラフト（LLM案）生成
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
# ※ 既存互換: 外から上書きできるようにしつつ安全なデフォルトを用意
MODEL = st.secrets.get("GROQ_MODEL") or os.getenv("GROQ_MODEL") or "llama-3.1-8b-instant"

client = Groq(api_key=API_KEY) if API_KEY else None


# ========= Helpers (既存踏襲 + 安全化) =========
def _extract_json_block(text: str) -> str:
    """```json ... ``` or 最初の { ... } を抽出（簡易ネスト対応）。"""
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


def _prompt_messages(uc_text: str) -> List[Dict[str, str]]:
    """元の設計思想を保ちつつ、名称/用語だけ整える。"""
    sys = (
        "あなたは衛星データの観測設計エンジニアです。"
        "ユーザーのユースケース説明から、観測要件を簡潔にドラフト化してください。"
        "出力時は、人間可読の短い要約→JSON（有効な1オブジェクト）の順で提示してください。"
    )
    usr = f"""ユースケース説明:
{uc_text}

出力要件:
1) まず人間可読の短い要約を書いた後、JSONを1つだけ返す
2) JSONスキーマ（固定）:
{{
  "usecase": "短いユースケース名",
  "goal": "観測目的（1〜2文）",
  "requirements": {{
    "actions": ["観測/推定したいこと（箇条書き）"],
    "bands": "使う波長帯（例: 可視・近赤外・短波赤外・熱赤外・SAR）",
    "gsd_m": "<目標地上分解能（m単位の推奨値）>",
    "revisit_days": "<目標観測頻度（日単位の推奨値）>"
  }}
}}

注意:
- 数値は数値型
- 不明なら妥当な初期値を推奨
- 1000トークン以内
"""
    return [
        {"role": "system", "content": sys},
        {"role": "user", "content": usr},
    ]


def _inject_css():
    """既存UIを壊さない範囲で視認性UP。"""
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


# ========= Main =========
def render():
    _inject_css()

    st.caption("ユースケースを自由に記述")
    default_uc = (
        "農業保険の損害査定は現地調査に時間とコストがかかり、迅速な支払いが困難。"
        "衛星データを活用して、干ばつや冷害などの被害を評価できるようにしたい。"
    )
    uc_text = st.text_area("ユースケース入力（Tab1）", value=default_uc, height=140)

    # 生成/クリア ボタン（元の配置を崩さず拡張）
    col_gen, col_clear = st.columns([1, 1])

    with col_gen:
        if not client:
            st.warning("GROQ_API_KEY が未設定です（Manage app → Settings → Secrets）。LLM生成は無効。")
        if st.button("観測設計ドラフトを生成（LLM）", type="primary", disabled=(client is None)):
            with st.spinner("LLMで観測設計ドラフトを作成中..."):
                try:
                    resp = client.chat.completions.create(
                        model=MODEL,
                        temperature=0.1,
                        max_tokens=1000,
                        messages=_prompt_messages(uc_text),
                    )
                except Exception as e:
                    st.error(f"Groq API呼び出しエラー: {e}")
                    return

                text = resp.choices[0].message.content or ""
                try:
                    data = _json_loads_safe(_extract_json_block(text))
                    st.session_state["draft_plan"] = data
                except Exception as e:
                    st.error(f"JSON解析に失敗しました: {e}")
                    with st.expander("LLM生テキスト（デバッグ用）", expanded=False):
                        st.code(text, language="markdown")

    with col_clear:
        if st.button("ユースケースを修正", type="secondary"):
            # 出力のみクリア（入力テキストは保持）
            st.session_state.pop("draft_plan", None)
            st.success("出力を削除しました。")
            st.rerun()

    draft: Optional[Dict[str, Any]] = st.session_state.get("draft_plan")
    if not draft:
        return

    # === 人間可読ビュー（名称・用語をリフレッシュ） ===
    st.subheader("観測設計ドラフト（LLM案）")

    usecase = draft.get("usecase") or "（名称未設定）"
    goal = draft.get("goal") or "（観測目的未記載）"
    req = draft.get("requirements") or {}
    actions = req.get("actions") or []
    bands = req.get("bands") or "（未指定）"
    gsd_m = req.get("gsd_m")
    revisit = req.get("revisit_days")

    st.markdown(f"**ユースケース名：** {usecase}")
    st.markdown(f"**観測目的：** {goal}")

    # ✅ 観測目的の直下に「やること（actions）」を移動
    if actions:
        st.caption("観測で実施すること")
        st.markdown("- " + "\n- ".join(actions))

    # ✅ 観測要件の下には 3 指標のみを掲載
    st.markdown("### 観測要件")

    # 使う波長帯
    st.markdown("**使う波長帯（観測バンド）** 例：可視・近赤外・短波赤外・熱赤外")
    st.markdown(str(bands))

    # 目標の解像度
    st.markdown("**目標の解像度（地上分解能） [m]** 例：10mなら圃場レベルの把握が可能")
    st.markdown(str(gsd_m) if gsd_m is not None else "（未指定）")

    # 目標の更新間隔
    st.markdown("**目標の更新間隔（観測頻度） [日]** 例：3日なら天候を跨いで監視しやすい")
    st.markdown(str(revisit) if revisit is not None else "（未指定）")

    # （任意）デバッグ支援は残しつつ折りたたみ
    with st.expander("デバッグ（MODEL / APIキー有無 / JSON原文）", expanded=False):
        st.write("MODEL =", MODEL)
        st.write("Has GROQ_API_KEY =", bool(API_KEY))
        st.code(json.dumps(draft, ensure_ascii=False, indent=2), language="json")
