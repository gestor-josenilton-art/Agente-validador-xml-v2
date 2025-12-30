import io
import os
import zipfile
from datetime import datetime

import pandas as pd
import streamlit as st

from utils.nfe_parser import parse_nfe_xml
from utils.users import ensure_admin, authenticate
from utils.base_legal import ensure_base_legal, load_tables, get_status
from utils.validator import validar_itens

st.set_page_config(page_title="Agente XML Fiscal — v2", page_icon="🧾", layout="wide")

# Bootstrap admin credentials (override via Streamlit secrets/env)
ADMIN_USER = st.secrets.get("ADMIN_USER", os.environ.get("ADMIN_USER", "admin"))
ADMIN_PASS = st.secrets.get("ADMIN_PASS", os.environ.get("ADMIN_PASS", "admin123"))
ensure_admin(admin_username=ADMIN_USER, admin_password=ADMIN_PASS)

# Ensure base legal templates exist
ensure_base_legal()


def require_login():
    if "auth" not in st.session_state:
        st.session_state.auth = None

    if st.session_state.auth is None:
        st.title("🔒 Login")
        st.caption("Acesso restrito. Solicite seu usuário e senha ao administrador.")
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Usuário")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar")
        if submitted:
            auth = authenticate(username.strip(), password)
            if auth:
                st.session_state.auth = auth
                st.success("Login realizado.")
                st.rerun()
            else:
                st.error("Usuário/senha inválidos ou usuário inativo.")
        st.stop()


require_login()

auth = st.session_state.auth
st.sidebar.markdown("### aplicativo")
st.sidebar.caption(f"Logado como: **{auth['username']}** ({auth.get('role','user')})")
if st.sidebar.button("Sair"):
    st.session_state.auth = None
    st.rerun()

st.title("🧾 Agente Leitor + Validador de XML Fiscal (NF-e) — v2")
st.write(
    "Faça upload de **XML(s) de NF-e** (ou um **.zip** com vários XMLs). "
    "O sistema lê, consolida, e agora **valida CFOP/NCM/CST/CSOSN** com base na **Base Legal** (gerenciável pelo Admin)."
)

uploaded = st.file_uploader("Envie XML(s) ou ZIP", type=["xml", "zip"], accept_multiple_files=True)

colA, colB, colC, colD = st.columns([2, 2, 2, 2])
with colA:
    consolidar_por = st.selectbox(
        "Consolidar por",
        ["xProd + NCM + CFOP", "cProd + NCM + CFOP", "NCM + CFOP", "xProd"],
        index=0,
    )
with colB:
    incluir_cabecalho = st.checkbox("Incorporar aba 'Cabeçalho NF-e'", value=True)
with colC:
    gerar_csv = st.checkbox("Gerar CSV junto (opcional)", value=False)
with colD:
    executar_validacao = st.checkbox("Executar validação fiscal (Base Legal)", value=True)

def _read_files(uploaded_files):
    xml_payloads = []
    for uf in uploaded_files or []:
        name = uf.name
        data = uf.read()
        if name.lower().endswith(".zip"):
            try:
                zf = zipfile.ZipFile(io.BytesIO(data))
                for zi in zf.infolist():
                    if zi.filename.lower().endswith(".xml"):
                        xml_payloads.append((zi.filename, zf.read(zi)))
            except Exception as e:
                st.warning(f"Falha ao ler ZIP {name}: {e}")
        elif name.lower().endswith(".xml"):
            xml_payloads.append((name, data))
    return xml_payloads

xml_files = _read_files(uploaded)

if xml_files:
    headers = []
    itens_all = []

    with st.spinner("Lendo XML(s)..."):
        for fname, payload in xml_files:
            try:
                parsed = parse_nfe_xml(payload)
                h = parsed["header"]
                h["arquivo"] = fname
                headers.append(h)
                for it in parsed["items"]:
                    row = {}
                    row.update(h)  # include header fields for traceability
                    row.update(it)
                    itens_all.append(row)
            except Exception as e:
                st.error(f"Erro ao processar {fname}: {e}")

    if not itens_all:
        st.warning("Nenhum item encontrado nos XMLs enviados.")
        st.stop()

    df_itens = pd.DataFrame(itens_all)

    # numeric conversions (best-effort)
    for c in ["qCom", "vUnCom", "vProd", "pICMS", "vICMS", "vNF"]:
        if c in df_itens.columns:
            df_itens[c] = pd.to_numeric(
                df_itens[c].astype(str).str.replace(",", ".", regex=False),
                errors="coerce",
            )

    # Choose consolidation keys
    if consolidar_por.startswith("xProd +"):
        key_cols = ["xProd", "NCM", "CFOP"]
    elif consolidar_por.startswith("cProd +"):
        key_cols = ["cProd", "NCM", "CFOP"]
    elif consolidar_por.startswith("NCM"):
        key_cols = ["NCM", "CFOP"]
    else:
        key_cols = ["xProd"]

    # Consolidate
    agg = (
        df_itens.groupby(key_cols, dropna=False, as_index=False)
        .agg(
            quantidade=("qCom", "sum"),
            valor_total=("vProd", "sum"),
            valor_unit_medio=("vUnCom", "mean"),
        )
        .sort_values(["valor_total"], ascending=False)
    )

    # Validation
    df_findings = pd.DataFrame()
    bl_status = get_status()
    if executar_validacao:
        with st.spinner("Executando validações..."):
            tables = load_tables()
            df_findings = validar_itens(df_itens, tables)

    # UI tabs
    tabs = st.tabs(["Itens (leitura bruta)", "Consolidado", "Validação", "Base Legal (status)"])

    with tabs[0]:
        st.subheader("Itens (det/prod) — leitura bruta")
        st.dataframe(df_itens, use_container_width=True, height=360)

    with tabs[1]:
        st.subheader("Consolidado")
        st.dataframe(agg, use_container_width=True, height=360)

    with tabs[2]:
        st.subheader("Validação fiscal (CFOP/NCM/CST/CSOSN)")
        if not executar_validacao:
            st.info("Validação desativada no topo. Marque a opção para executar.")
        elif df_findings.empty:
            st.success("Nenhuma inconsistência encontrada nas regras atuais (ou a base está vazia).")
        else:
            # Summary
            c1, c2 = st.columns(2)
            with c1:
                st.metric("Erros", int((df_findings["severidade"] == "ERRO").sum()))
            with c2:
                st.metric("Alertas", int((df_findings["severidade"] == "ALERTA").sum()))
            st.dataframe(df_findings, use_container_width=True, height=360)

    with tabs[3]:
        st.subheader("Status da Base Legal vigente")
        st.caption("Para substituir a Base Legal, use a página **📚 Admin — Base Legal** no menu lateral (apenas ADMIN).")
        st.write(pd.DataFrame([
            {"tabela": "NCM", "arquivo": "ncm_regras.xlsx", "linhas": bl_status["ncm"].rows, "status": bl_status["ncm"].message},
            {"tabela": "CFOP", "arquivo": "cfop_regras.xlsx", "linhas": bl_status["cfop"].rows, "status": bl_status["cfop"].message},
            {"tabela": "CST/CSOSN", "arquivo": "cst_csosn_regras.xlsx", "linhas": bl_status["cst"].rows, "status": bl_status["cst"].message},
        ]))

    # Downloads
    st.divider()
    st.subheader("Exportações")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        if incluir_cabecalho:
            pd.DataFrame(headers).to_excel(writer, sheet_name="Cabecalho_NFe", index=False)
        df_itens.to_excel(writer, sheet_name="Itens_Bruto", index=False)
        agg.to_excel(writer, sheet_name="Consolidado", index=False)
        if executar_validacao:
            df_findings.to_excel(writer, sheet_name="Validacao", index=False)
    buffer.seek(0)

    st.download_button(
        "📥 Baixar Excel (com abas)",
        data=buffer,
        file_name=f"xml_fiscal_v2_{ts}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    if gerar_csv:
        st.download_button(
            "📥 Baixar CSV (Itens_Bruto)",
            data=df_itens.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"itens_bruto_{ts}.csv",
            mime="text/csv",
        )

else:
    st.info("Envie ao menos 1 XML ou 1 ZIP contendo XMLs para começar.")

st.caption("Admin: gerenciamento de usuários e Base Legal ficam nas páginas do menu lateral (apenas admin).")
