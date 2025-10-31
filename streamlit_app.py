# streamlit_app.py (Página Principal: Login, Inclusão, Edição, Tabela)

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta 
from io import BytesIO
import numpy as np 
import gspread
from gspread_dataframe import set_with_dataframe, get_as_dataframe

# Importa as configurações do novo arquivo config.py
from config import COLUNAS_ESPERADAS, PRAZO_SLA, LISTA_PROJETOS, SENHA_ACESSO 

# ----------------------------------------------------------------------
# --- FUNÇÕES CORE: CONEXÃO, CARGA E SALVAMENTO ---
# ----------------------------------------------------------------------

USAR_GSHEETS = True

@st.cache_resource(ttl=3600)
def conectar_google_sheets():
    """Estabelece a conexão real com o Google Sheets."""
    if not USAR_GSHEETS:
        return None
    
    try:
        creds = st.secrets["gcp_service_account"]
        client = gspread.service_account_from_dict(creds)
        
        spreadsheet_id = st.secrets["spreadsheet_id"]
        worksheet_name = st.secrets["worksheet_name"]
        
        sheet = client.open_by_key(spreadsheet_id)
        return sheet.worksheet(worksheet_name)
    except Exception as e:
        st.error(f"Erro CRÍTICO ao conectar com Google Sheets. Verifique o ID/Secrets. Erro: {e}")
        return None

def carregar_dados_do_sheets():
    """Lê todos os dados da planilha e os carrega como um DataFrame."""
    if not USAR_GSHEETS:
        return pd.DataFrame(columns=COLUNAS_ESPERADAS)

    worksheet = conectar_google_sheets()
    if worksheet is None:
        return pd.DataFrame(columns=COLUNAS_ESPERADAS)
    
    try:
        df = get_as_dataframe(worksheet, header=0, evaluate_formulas=True, dtype=str, index_col=None)
    except Exception as e:
        st.error(f"Erro ao tentar ler o DataFrame. Erro: {e}")
        return pd.DataFrame(columns=COLUNAS_ESPERADAS)
    
    for col in COLUNAS_ESPERADAS:
        if col not in df.columns:
            df[col] = '' 

    df = df[COLUNAS_ESPERADAS].copy() 
    df = df.dropna(subset=['ID Chamado']).reset_index(drop=True) 
    
    if not df.empty:
          df['ID Chamado'] = df['ID Chamado'].astype(str).str.replace(r'\.0$', '', regex=True)
          df = df.replace(r'^\s*$', np.nan, regex=True).fillna('') 

    return df

def salvar_dataframe_no_sheets(df_completo_original):
    """Escreve o DataFrame de volta no Google Sheets."""
    
    df_para_sheets = df_completo_original[COLUNAS_ESPERADAS] 

    if not USAR_GSHEETS:
        st.session_state.dados_chamados = df_completo_original.copy()
        st.success("Tabela atualizada e salva no sistema local (Simulação).")
        return
        
    worksheet = conectar_google_sheets()
    if worksheet is None:
        return

    try:
        set_with_dataframe(worksheet, df_para_sheets.fillna(''), row=1, col=1)
        st.session_state.dados_chamados = df_completo_original.copy()
        # st.session_state.last_saved_id é setado pelo callback/função handle_successful_edit
        st.success("Tabela atualizada e salva no Google Sheets com sucesso!")
    except Exception as e:
        st.error(f"Erro ao salvar no Sheets. Verifique as permissões. Erro: {e}")

# ----------------------------------------------------------------------
# --- FUNÇÕES DE CÁLCULO E AUXILIARES ---
# ----------------------------------------------------------------------

@st.cache_data
def carregar_dados_e_calcular(df_entrada):
    """Calcula SLA, Duração e define o Status Visual."""
    
    if df_entrada.empty:
        return pd.DataFrame(columns=COLUNAS_ESPERADAS + ['Duração Total', 'Total de Horas', 'Exige Compl.?', 'Status Visual'])

    df = df_entrada.copy()
    
    df['Data'] = df['Data'].astype(str).str.strip()
    for col in ['Hora Agendamento', 'Hora Chegada', 'Hora Final']:
        df[col] = df[col].astype(str).str.strip().replace('', '00:00', regex=False)

    data_hora_chegada_str = df['Data'] + ' ' + df['Hora Chegada']
    data_hora_final_str = df['Data'] + ' ' + df['Hora Final']
    
    df['Data/Hora Chegada'] = pd.to_datetime(data_hora_chegada_str, format='%d/%m/%Y %H:%M', errors='coerce')
    df['Data/Hora Final'] = pd.to_datetime(data_hora_final_str, format='%d/%m/%Y %H:%M', errors='coerce')
    
    df['Duração Total'] = df['Data/Hora Final'] - df['Data/Hora Chegada']
    
    df.loc[df['Duração Total'] < timedelta(0), 'Duração Total'] = timedelta(0) 
    df.loc[df['Duração Total'].isna(), 'Duração Total'] = timedelta(0)

    df['Total de Horas'] = df['Duração Total'].apply(
        lambda x: str(x).split('days')[-1].split('.')[0].strip() if x != timedelta(0) else '00:00:00'
    )
    
    df['Exige Compl.?'] = (df['Duração Total'] > PRAZO_SLA).map({True: 'SIM', False: 'NÃO'})

    df['Status Visual'] = 'OK' 
    
    condicao_alerta = (df['Exige Compl.?'] == 'SIM') & (df['Compl. Aberto?'] == 'NÃO')
    df.loc[condicao_alerta, 'Status Visual'] = 'ALERTA'
    
    condicao_concluido = (df['Exige Compl.?'] == 'SIM') & (df['Compl. Aberto?'] == 'SIM')
    df.loc[condicao_concluido, 'Status Visual'] = 'CONCLUÍDO'

    colunas_finais = COLUNAS_ESPERADAS + ['Total de Horas', 'Exige Compl.?', 'Status Visual']
    
    return df[colunas_finais].copy()

def colorir_tabela(df_calculado):
    """Aplica formatação condicional."""
    if 'Status Visual' not in df_calculado.columns:
        return df_calculado

    df_para_exibir = df_calculado.drop(columns=['Status Visual'], errors='ignore')

    def estilo_linha(row):
        status = df_calculado.loc[row.name, 'Status Visual']
        
        base_style = [''] * len(row)
        
        if status == 'ALERTA':
            base_style = ['background-color: #FFCCCC'] * len(row) 
        elif status == 'CONCLUÍDO':
            base_style = ['background-color: #CCFFCC'] * len(row) 

        return base_style

    df_estilizado = df_para_exibir.style.apply(estilo_linha, axis=1)
    return df_estilizado

@st.cache_data
def para_excel(df_completo):
    """Converte o DataFrame em um arquivo Excel (bytes) para download."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        colunas_download = [col for col in df_completo.columns if col not in ['Status Visual', 'Data/Hora Chegada', 'Data/Hora Final', 'Duração Total']]
        df_completo[colunas_download].to_excel(writer, sheet_name='Controle_Chamados', index=False)
    
    return output.getvalue()

def reset_form_defaults():
    """Remove as chaves de sessão dos widgets para forçar o reset no próximo rerun."""
    keys_to_delete = ['new_id', 'new_analista', 'new_id_compl_aberto', 'new_obs', 'new_date', 
                      'new_compl_aberto', 'new_hora_agendamento', 'new_hora_chegada', 'new_hora_final',
                      'default_time', 'new_projeto'] 
    
    for key in keys_to_delete:
        if key in st.session_state:
            del st.session_state[key] 
            
# 🟢 FUNÇÃO CORRIGIDA: Manipula session_state de forma segura
def handle_successful_save(id_do_registro):
    """
    Função de callback para ser chamada APÓS um salvamento bem-sucedido.
    Manipula st.session_state de forma segura para evitar StreamlitAPIException.
    """
    # 1. Configura o ID para a confirmação visual
    st.session_state.last_saved_id = str(id_do_registro)
    
    # 2. Limpeza segura do estado de edição (cria/atribui sem deletar)
    # Garante que a chave exista antes de alterar — evita condições de corrida com reruns.
    st.session_state.setdefault("search_input_edit", "")
    st.session_state.search_input_edit = ""
    
    st.session_state.setdefault("filtered_id_to_edit", "Selecione...")
    st.session_state.filtered_id_to_edit = "Selecione..."
    
    if "multi_filtered_ids" in st.session_state:
        del st.session_state["multi_filtered_ids"]
    
    st.session_state.setdefault("search_input_register", "")
    st.session_state.search_input_register = ""
    
    # O st.rerun() no final do form fará o resto.


def buscar_id_para_edicao():
    """Filtra o DataFrame com base no texto de busca e define o ID encontrado."""
    search_term = st.session_state.search_input_edit.strip()
    
    if 'multi_filtered_ids' in st.session_state:
        del st.session_state['multi_filtered_ids']
    
    if not search_term:
        st.session_state.filtered_id_to_edit = 'Selecione...'
        st.warning("Digite o ID do Chamado na caixa de texto ao lado da lupa.")
        return
    
    df = st.session_state.dados_chamados
    
    df_temp = df.copy()
    df_temp['ID Chamado'] = df_temp['ID Chamado'].astype(str).fillna('').str.strip()
    
    filtered_ids = df_temp['ID Chamado'][df_temp['ID Chamado'].str.contains(search_term, case=False, na=False)].tolist()
    
    if not filtered_ids:
        st.session_state.filtered_id_to_edit = 'Selecione...'
        st.error(f"Nenhum chamado encontrado com ID contendo '{search_term}'.")
    elif len(filtered_ids) == 1:
        st.session_state.filtered_id_to_edit = filtered_ids[0]
        st.success(f"ID '{filtered_ids[0]}' encontrado. Pronto para edição abaixo.")
    else:
        st.session_state.filtered_id_to_edit = 'Selecione...' 
        st.session_state.multi_filtered_ids = filtered_ids 
        st.warning(f"{len(filtered_ids)} IDs encontrados. Por favor, selecione um abaixo.")

def inicializar_session_state():
    """Inicializa os estados necessários para a aplicação."""
    if 'dados_chamados' not in st.session_state:
        st.session_state.dados_chamados = carregar_dados_do_sheets()

    if 'filtered_id_to_edit' not in st.session_state:
        st.session_state.filtered_id_to_edit = 'Selecione...'

    if 'search_input_edit' not in st.session_state:
        st.session_state.search_input_edit = ""
        
    if 'last_saved_id' not in st.session_state: # Estado para confirmação visual
        st.session_state.last_saved_id = None 

    if 'default_time' not in st.session_state or st.session_state.default_time is None:
        st.session_state.default_time = datetime.now().time()
    
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

# ----------------------------------------------------------------------
# --- LÓGICA DE LOGIN ---
# ----------------------------------------------------------------------

def show_login_page():
    """Exibe a tela de login."""
    st.title("🔒 Login do Sistema")
    st.markdown("Insira a senha para acessar o controle de chamados.")
    
    with st.form("login_form"):
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")
        
        if submitted:
            if password == SENHA_ACESSO:
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("Senha incorreta.")

def show_main_content(df_calculado):
    """Exibe o conteúdo principal (Formulários e Tabela)."""
    
    st.title("Sistema de Controle de Chamados Complementares")
    
    # --- SEÇÃO 1: FORMULÁRIO DE INCLUSÃO ---
    st.header("➕ Registrar Novo Chamado")

    with st.form("novo_chamado"):
        col1, col2, col3 = st.columns(3)
        
        initial_time = st.session_state.default_time if st.session_state.default_time is not None else datetime.now().time()
        
        with col1:
            id_chamado = st.text_input("ID Chamado (Obrigatório)", value="", key="new_id")
            data = st.date_input("Data (Obrigatório)", datetime.now().date(), key="new_date")
            analista_bo = st.text_input("Analista BO", value="", key="new_analista")
        
        with col2:
            hora_agendamento = st.time_input("Hora Agendamento", value=initial_time, key="new_hora_agendamento")
            hora_chegada = st.time_input("Hora Chegada (Obrigatório)", value=initial_time, key="new_hora_chegada")
            hora_final = st.time_input("Hora Final (Obrigatório)", value=initial_time, key="new_hora_final")
            
        with col3:
            projeto = st.selectbox("Projeto (Obrigatório)", options=LISTA_PROJETOS, key="new_projeto")
            
            compl_aberto = st.selectbox("Complementar Aberto?", ["NÃO", "SIM"], key="new_compl_aberto")
            id_compl_aberto = st.text_input("ID Compl. Aberto", value="", key="new_id_compl_aberto")

        observacoes = st.text_area("Observações", value="", key="new_obs")

        submetido = st.form_submit_button("Salvar Chamado")

        if submetido:
            validado = True
            
            if not id_chamado or not hora_chegada or not hora_final or not projeto:
                st.error("Por favor, preencha todos os campos obrigatórios (ID Chamado, Hora Chegada, Hora Final, Projeto).")
                validado = False
            
            id_list = st.session_state.dados_chamados['ID Chamado'].astype(str).str.strip().tolist()
            if validado and id_chamado.strip() in id_list:
                st.error(f"Erro: O ID de Chamado '{id_chamado}' já existe na base de dados. Por favor, verifique.")
                validado = False
            
            if compl_aberto == "SIM" and not id_compl_aberto:
                st.error("Regra de Negócio: Se 'Complementar Aberto?' é SIM, o campo 'ID Compl. Aberto' é obrigatório.")
                validado = False

            if validado:
                dados_novo_chamado = {
                    'ID Chamado': id_chamado,
                    'Data': data.strftime('%d/%m/%Y'),
                    'Hora Agendamento': hora_agendamento.strftime('%H:%M'),
                    'Hora Chegada': hora_chegada.strftime('%H:%M'),
                    'Hora Final': hora_final.strftime('%H:%M'),
                    'Compl. Aberto?': compl_aberto,
                    'ID Compl. Aberto': id_compl_aberto,
                    'Analista BO': analista_bo,
                    'Observações': observacoes,
                    'Projeto': projeto,
                }
                
                novo_df = pd.DataFrame([dados_novo_chamado], columns=COLUNAS_ESPERADAS)
                df_atualizado = pd.concat([st.session_state.dados_chamados, novo_df], ignore_index=True)
                
                salvar_dataframe_no_sheets(df_atualizado)
                
                reset_form_defaults() 
                del st.session_state['dados_chamados']
                
                # 🟢 Chama a função de callback e reinicia
                handle_successful_save(id_chamado) 
                st.rerun()

    st.markdown("---")
    
    # --- CONFIRMAÇÃO VISUAL PÓS-EDIÇÃO/INCLUSÃO ---
    if st.session_state.last_saved_id:
        confirm_id = st.session_state.last_saved_id
        
        # Filtra o registro recém-salvo
        df_confirm = df_calculado[df_calculado['ID Chamado'] == confirm_id]
        
        if not df_confirm.empty:
            st.subheader(f"✅ Registro Atualizado/Incluso: ID {confirm_id}")
            
            # Aplica a coloração e exibe apenas a linha relevante
            st.dataframe(
                colorir_tabela(df_confirm), 
                use_container_width=True, 
                hide_index=True
            )
        
        # Limpa o estado após exibir
        st.session_state.last_saved_id = None
    # ----------------------------------------------------------------------

    # --- SEÇÃO 3: TABELA DE CONTROLE ---

    st.header("📋 Tabela de Controle de Chamados")
    
    if df_calculado.empty:
        st.info("Nenhum chamado para exibir. Adicione um novo registro no formulário acima.")
    else:
        with st.expander("Visualizar Tabela de Dados", expanded=True):
            
            col_t1, col_t2 = st.columns([4, 1])
            
            with col_t1:
                st.markdown("##### Dados Calculados e Formatados por SLA:")
            
            with col_t2:
                filtro_alerta = st.checkbox("Apenas ALERTA", value=False)
            
            df_filtrado = df_calculado
            if filtro_alerta:
                df_filtrado = df_calculado[df_filtrado['Status Visual'] == 'ALERTA']
            
            st.dataframe(colorir_tabela(df_filtrado), use_container_width=True, height=500)

            # Download
            st.download_button(
                label="📥 Download da Tabela (Excel)",
                data=para_excel(df_filtrado),
                file_name="Controle_Chamados_SLA.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key='download_excel'
            )


    # --- SEÇÃO 4: EDIÇÃO DE DADOS ---

    st.header("✏️ Editar Chamado Existente")

    col_search_input, col_search_button = st.columns([0.7, 0.3]) # Colunas ajustadas para 2 botões

    with col_search_input:
        search_id = st.text_input(
            "ID do Chamado", 
            value=st.session_state.search_input_edit, 
            key="search_input_edit",
        )

    with col_search_button:
        # 🟢 Botão de Busca
        st.button(
            "Buscar ID 🔍", 
            on_click=buscar_id_para_edicao, 
            type="primary", 
            use_container_width=True
        )
        # 🟢 Botão para limpar a busca (usando on_click para resetar estados)
        # Define a função lambda para limpar o estado
        def reset_search_state():
            if 'search_input_edit' in st.session_state:
                del st.session_state.search_input_edit
            st.session_state.filtered_id_to_edit = 'Selecione...'

        st.button(
            "Limpar Busca", 
            on_click=reset_search_state,
            use_container_width=True
        )


    chamado_selecionado_id = st.session_state.filtered_id_to_edit


    if chamado_selecionado_id != 'Selecione...':
        
        if 'multi_filtered_ids' in st.session_state and st.session_state.multi_filtered_ids:
            
            chamado_selecionado_id = st.selectbox(
                "Chamado Selecionado para Edição", 
                options=['Selecione...'] + st.session_state.multi_filtered_ids, 
                key="select_multi_edit_id"
            )
            if chamado_selecionado_id == 'Selecione...':
                st.stop()
            
            st.session_state.filtered_id_to_edit = chamado_selecionado_id
        
        
        df_chamado = st.session_state.dados_chamados[
            st.session_state.dados_chamados['ID Chamado'] == chamado_selecionado_id
        ].iloc[0]

        hora_final_str = df_chamado['Hora Final']
        try:
            hora_final_inicial = datetime.strptime(hora_final_str, '%H:%M').time()
        except ValueError:
            hora_final_inicial = datetime.now().time() 
            
        compl_aberto_inicial = df_chamado['Compl. Aberto?']
        observacoes_inicial = df_chamado['Observações']
        id_compl_aberto_inicial = df_chamado['ID Compl. Aberto']
        projeto_inicial = df_chamado.get('Projeto', 'Outros') 

        st.subheader(f"Editando Chamado ID: {chamado_selecionado_id}")
        
        with st.form("form_edicao"):
            col_edit1, col_edit2 = st.columns(2)
            
            with col_edit1:
                nova_hora_final = st.time_input(
                    "Nova Hora Final (Obrigatório)", 
                    value=hora_final_inicial,
                    key="edit_hora_final"
                )
                
                novo_projeto = st.selectbox(
                    "Novo Projeto", 
                    options=LISTA_PROJETOS, 
                    index=LISTA_PROJETOS.index(projeto_inicial) if projeto_inicial in LISTA_PROJETOS else 4,
                    key="edit_projeto"
                )
                
                novo_compl_aberto = st.selectbox(
                    "Complementar Aberto?", 
                    ["NÃO", "SIM"], 
                    index=["NÃO", "SIM"].index(compl_aberto_inicial) if compl_aberto_inicial in ["NÃO", "SIM"] else 0,
                    key="edit_compl_aberto"
                )

            with col_edit2:
                novo_id_compl_aberto = st.text_input(
                    "Novo ID Compl. Aberto", 
                    value=id_compl_aberto_inicial,
                    key="edit_id_compl_aberto"
                )
                
                nova_observacoes = st.text_area(
                    "Nova Observações", 
                    value=observacoes_inicial,
                    key="edit_obs"
                )
                
            submetido_edicao = st.form_submit_button("Salvar Edição")

            if submetido_edicao:
                df_completo = st.session_state.dados_chamados.copy()
                idx = df_completo[df_completo['ID Chamado'].astype(str) == str(chamado_selecionado_id)].index[0]
                validado_edicao = True
                
                if not nova_hora_final:
                    st.error("Hora Final é um campo obrigatório para edição.")
                    validado_edicao = False
                
                if novo_compl_aberto == "SIM" and not novo_id_compl_aberto:
                    st.error("Regra de Negócio: Se 'Complementar Aberto?' é SIM, o campo 'ID Compl. Aberto' é obrigatório.")
                    validado_edicao = False

                if validado_edicao:
                    df_completo.loc[idx, 'Hora Final'] = nova_hora_final.strftime('%H:%M')
                    df_completo.loc[idx, 'Compl. Aberto?'] = novo_compl_aberto
                    df_completo.loc[idx, 'ID Compl. Aberto'] = novo_id_compl_aberto
                    df_completo.loc[idx, 'Observações'] = nova_observacoes
                    df_completo.loc[idx, 'Projeto'] = novo_projeto
                    
                    salvar_dataframe_no_sheets(df_completo)
                    
                    del st.session_state['dados_chamados']
                    
                    # 🟢 Chama a função de callback e reinicia
                    handle_successful_save(chamado_selecionado_id) 
                    st.rerun()

# ----------------------------------------------------------------------
# --- EXECUÇÃO PRINCIPAL ---
# ----------------------------------------------------------------------

if __name__ == "__main__":
    st.set_page_config(layout="wide", page_title="Controle de Chamados (Home)")
    inicializar_session_state()

    if st.session_state.logged_in:
        df_calculado = carregar_dados_e_calcular(st.session_state.dados_chamados)
        show_main_content(df_calculado)
        
        if st.sidebar.button("Sair (Logoff)"):
            st.session_state.logged_in = False
            st.rerun()
            
    else:
        show_login_page()
