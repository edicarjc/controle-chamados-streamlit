# pages/Dashboard.py (Nova Página do Dashboard)

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import timedelta
import numpy as np

# Importa as configurações do arquivo config.py
from config import PRAZO_SLA 

# ----------------------------------------------------------------------
# --- FUNÇÕES DE CÁLCULO (Copiadas da Home para garantir a funcionalidade) ---
# ----------------------------------------------------------------------

@st.cache_data
def carregar_dados_e_calcular_dash(df_entrada):
    """Calcula SLA, Duração e define o Status Visual para o Dashboard."""
    
    if df_entrada.empty:
        return pd.DataFrame()

    df = df_entrada.copy()
    
    df['Data'] = df['Data'].astype(str).str.strip()
    for col in ['Hora Chegada', 'Hora Final']:
        df[col] = df[col].astype(str).str.strip().replace('', '00:00', regex=False)

    data_hora_chegada_str = df['Data'] + ' ' + df['Hora Chegada']
    
    # 🟢 ADICIONADO: Tratamento da coluna Data para análise de tendência
    df['Data Analise'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')

    df['Data/Hora Chegada'] = pd.to_datetime(data_hora_chegada_str, format='%d/%m/%Y %H:%M', errors='coerce')
    df['Data/Hora Final'] = pd.to_datetime(df['Data'] + ' ' + df['Hora Final'], format='%d/%m/%Y %H:%M', errors='coerce')
    
    df['Duração Total'] = df['Data/Hora Final'] - df['Data/Hora Chegada']
    
    df.loc[df['Duração Total'].isna(), 'Duração Total'] = pd.Timedelta(seconds=0)

    df['Exige Compl.?'] = (df['Duração Total'] > PRAZO_SLA).map({True: 'SIM', False: 'NÃO'})
    df['Status Visual'] = 'OK' 
    
    condicao_alerta = (df['Exige Compl.?'] == 'SIM') & (df['Compl. Aberto?'] == 'NÃO')
    df.loc[condicao_alerta, 'Status Visual'] = 'ALERTA'
    
    condicao_concluido = (df['Exige Compl.?'] == 'SIM') & (df['Compl. Aberto?'] == 'SIM')
    df.loc[condicao_concluido, 'Status Visual'] = 'CONCLUÍDO'
    
    df['Total de Horas'] = df['Duração Total'].apply(
        lambda x: str(x).split('days')[-1].split('.')[0].strip() if x.total_seconds() > 0 else '0:00:00'
    )
    
    return df

# ----------------------------------------------------------------------
# --- EXECUÇÃO DA PÁGINA DASHBOARD ---
# ----------------------------------------------------------------------

st.set_page_config(layout="wide", page_title="Dashboard SLA")

# 1. Lógica de Acesso (Garanta que o usuário esteja logado)
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("Acesso negado. Por favor, faça login na página inicial.")
    st.stop() 

# 2. Lógica de Carregamento de Dados (Garantir que o DF exista)
if 'dados_chamados' not in st.session_state:
    st.error("Dados não carregados. Retorne à página inicial e faça login.")
    st.stop()

df_calculado = carregar_dados_e_calcular_dash(st.session_state.dados_chamados)

# Opcional: Botão de Logoff no sidebar
if st.sidebar.button("Sair (Logoff)"):
    st.session_state.logged_in = False
    st.rerun()


st.header("📊 Resumo do Desempenho SLA (4 Horas)")

if not df_calculado.empty and 'Duração Total' in df_calculado.columns:
    
    # 1. Indicadores de Status (Mantido)
    total_chamados = len(df_calculado)
    alerta = len(df_calculado[df_calculado['Status Visual'] == 'ALERTA'])
    concluido = len(df_calculado[df_calculado['Status Visual'] == 'CONCLUÍDO'])
    ok = len(df_calculado[df_calculado['Status Visual'] == 'OK'])
    
    df_validos = df_calculado[df_calculado['Duração Total'].dt.total_seconds() > 0].copy()
    if not df_validos.empty:
        tempo_medio_seconds = df_validos['Duração Total'].mean().total_seconds()
        tempo_medio = str(pd.Timedelta(seconds=int(tempo_medio_seconds))).split('.')[0]
    else:
        tempo_medio = "0:00:00"
        
    
    col_d1, col_d2, col_d3 = st.columns(3)
    
    with col_d1:
        st.metric(label="Total Geral de Chamados", value=total_chamados)
    with col_d2:
        st.metric(
            label="Média de Resolução (HH:MM:SS)", 
            value=tempo_medio, 
            delta="SLA: 4:00:00", 
            delta_color="off"
        )
    with col_d3:
        with st.container(border=True):
            st.markdown(f"**Em OK (Dentro do SLA):** **<span style='color:#00AA00; font-size:18px;'>{ok}</span>**", unsafe_allow_html=True)
            st.markdown(f"**ALERTA (SLA Estourado):** **<span style='color:#FF7F7F; font-size:18px;'>{alerta}</span>**", unsafe_allow_html=True)
            st.markdown(f"**CONCLUÍDO (SLA Estourado c/ Compl.):** **<span style='color:#FFD700; font-size:18px;'>{concluido}</span>**", unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Prepara o DataFrame para análise dos pendentes (ALERTA)
    df_analise = df_calculado.copy()
    df_analise['Analista BO'] = df_analise['Analista BO'].fillna('Não Informado').replace('', 'Não Informado')
    df_analise['Projeto'] = df_analise['Projeto'].fillna('Não Informado').replace('', 'Não Informado')
    df_alerta = df_analise[df_analise['Status Visual'] == 'ALERTA'].copy()

    
    st.subheader("Gráficos de Chamados Pendentes (ALERTA)")
    
    if df_alerta.empty:
        st.info("Nenhum chamado atualmente em ALERTA para análise detalhada.")
        st.stop()


    # --- LINHA 1 DE GRÁFICOS ---
    col_g1, col_g2 = st.columns(2)
    
    # 2. Pendentes por Projeto (Mantido e Ajustado)
    with col_g1:
        st.markdown("##### Pendentes por Projeto")
        df_pendentes_projeto = df_alerta.groupby('Projeto').size().reset_index(name='Total')
        
        fig_pendente_proj = px.bar(
            df_pendentes_projeto, 
            x='Total', 
            y='Projeto', 
            orientation='h',
            color_discrete_sequence=['#FF7F7F'],
            labels={'Total': 'Nº Pendentes', 'Projeto': 'Projeto'},
            height=350
        )
        fig_pendente_proj.update_layout(yaxis={'categoryorder': 'total ascending'}, margin={"t":20, "b":20, "l":20, "r":20})
        st.plotly_chart(fig_pendente_proj, use_container_width=True)
        

    # 3. Pendentes por Analista (Novo Gráfico)
    with col_g2:
        st.markdown("##### Pendentes por Analista")
        df_pendentes_analista = df_alerta.groupby('Analista BO').size().reset_index(name='Total')
        
        fig_pendente_analista = px.bar(
            df_pendentes_analista, 
            x='Analista BO', 
            y='Total', 
            color_discrete_sequence=['#FFC0CB'], # Cor rosa clara para diferenciar
            labels={'Total': 'Nº Pendentes', 'Analista BO': 'Analista'},
            height=350
        )
        fig_pendente_analista.update_layout(xaxis={'categoryorder': 'total descending', 'tickangle': 45}, margin={"t":20, "b":20, "l":20, "r":20})
        st.plotly_chart(fig_pendente_analista, use_container_width=True)


    st.markdown("---")


    # --- LINHA 2 DE GRÁFICOS (Gráfico Pendentes por Data) ---
    st.markdown("##### Tendência de Pendentes por Data (Diário)")
    
    # 4. Pendentes por Data (Sugestão para o 3º Gráfico)
    # Agrupa por data e conta.
    df_pendentes_data = df_alerta.groupby('Data Analise').size().reset_index(name='Total')
    df_pendentes_data = df_pendentes_data.sort_values(by='Data Analise')
    
    fig_pendente_data = px.line(
        df_pendentes_data,
        x='Data Analise',
        y='Total',
        markers=True,
        line_shape='spline',
        color_discrete_sequence=['#FFA500'], # Cor Laranja
        labels={'Total': 'Nº Pendentes', 'Data Analise': 'Data'},
        height=400
    )
    fig_pendente_data.update_layout(margin={"t":20, "b":20, "l":20, "r":20})
    st.plotly_chart(fig_pendente_data, use_container_width=True)

    
else:
    st.info("Nenhum dado válido para exibição no Dashboard. Retorne à página inicial.")