 # config.py

import streamlit as st
from datetime import timedelta

# --- CONFIGURAÇÕES DE SEGURANÇA ---
# 🛑 ATENÇÃO: Após o deploy, a senha real será lida do arquivo .streamlit/secrets.toml
try:
    # Tenta ler a senha do Streamlit Secrets (funciona no Cloud)
    SENHA_ACESSO = st.secrets["SENHA_ACESSO"]
except Exception:
    # Usa a senha local (para desenvolvimento/teste no seu computador)
    SENHA_ACESSO = "csc2026" 

# --- CONFIGURAÇÕES GERAIS ---
PRAZO_SLA = timedelta(hours=4)
LISTA_PROJETOS = ['Ambev', 'Saque e Pague', 'Tokio', 'Rumo', 'Outros']

COLUNAS_ESPERADAS = [
    'ID Chamado', 'Data', 'Hora Agendamento', 'Hora Chegada', 'Hora Final', 
    'Compl. Aberto?', 'ID Compl. Aberto', 'Analista BO', 'Observações', 'Projeto' 
]