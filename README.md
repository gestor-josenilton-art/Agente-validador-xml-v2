# Agente Leitor de XML Fiscal (NF-e) — Streamlit

## O que faz
- Upload de **XML(s) de NF-e** ou **ZIP** com vários XMLs
- Leitura do **cabeçalho** (emitente, destinatário, chave, número, série, data, vNF)
- Leitura dos **itens** (NCM, CFOP, CST/CSOSN, qCom, vUnCom, vProd, etc.)
- Gera **Consolidado** por agrupamento
- Exporta **Excel** (e CSV opcional)

## Como rodar no Streamlit Cloud
1. Suba esta pasta como repositório no **GitHub**.
2. No **Streamlit Community Cloud**:
   - **Repository**: selecione seu repo
   - **Main file path**: `app/app.py`
3. Em **Settings → Secrets**, cadastre:
   - `ADMIN_USER` (ex.: `admin`)
   - `ADMIN_PASS` (troque a senha!)
4. Deploy.

> Dica: o arquivo `.streamlit/secrets.example.toml` é apenas um modelo.  
> **Não** suba `secrets.toml` para o GitHub.

## Como rodar local (opcional)
```bash
pip install -r requirements.txt
streamlit run app/app.py
```

## Login e usuários
- O app exige login.
- O admin é criado automaticamente na primeira execução com `ADMIN_USER/ADMIN_PASS`.
- Usuários ficam em `data/users.json` (senha em hash PBKDF2).

⚠️ **Observação sobre Streamlit Cloud**: o sistema de arquivos pode ser **efêmero** (reset em restart/redeploy).  
Se você criar/editar usuários pela tela de Admin, isso pode não persistir para sempre.  
Para uso multiusuário “definitivo”, o ideal é plugar um armazenamento externo (ex.: banco/arquivo em storage).

## Base Legal (Validação Fiscal)
- A validação CFOP/NCM/CST/CSOSN usa as planilhas em `data/base_legal/current/`:
  - `ncm_regras.xlsx` (colunas: `ncm`, `descricao`)
  - `cfop_regras.xlsx` (colunas: `cfop`, `descricao`)
  - `cst_csosn_regras.xlsx` (colunas: `codigo`, `tipo` [CST/CSOSN], `descricao`)
- A página **📚 Admin — Base Legal** (somente admin) permite atualizar as planilhas.
- Ao atualizar, o app cria backup em `data/base_legal/history/`.
