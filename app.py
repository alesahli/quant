import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Configuração da Página
st.set_page_config(page_title="Painel Quant - Z-Score", layout="wide")

st.title("📊 Painel de Reversão à Média (Z-Score)")
st.markdown("""
Este painel calcula o afastamento do preço em relação às médias móveis selecionadas.
A soma desses afastamentos é normalizada (Z-Score) para identificar extremos estatísticos.
""")

# --- Sidebar (Configurações) ---
st.sidebar.header("Configurações")
ticker = st.sidebar.text_input("Ativo (Yahoo Finance)", value="PETR4.SA").upper()

# Seletor de Tipo de Data
tipo_data = st.sidebar.radio("Selecione o Periodo:", ["Período Fixo", "Data Personalizada"])

start_date = None
end_date = None
periodo_yfinance = None

if tipo_data == "Período Fixo":
    periodo_yfinance = st.sidebar.selectbox(
        "Janela de Tempo", 
        ["1y", "2y", "5y", "10y", "max"], 
        index=2  # Começa selecionando 5y para evitar erro de falta de dados
    )
else:
    col_data1, col_data2 = st.sidebar.columns(2)
    start_date = col_data1.date_input("Início", value=datetime.today() - timedelta(days=365*5))
    end_date = col_data2.date_input("Fim", value=datetime.today())

st.sidebar.markdown("---")
st.sidebar.markdown("### Parâmetros do Indicador")

# NOVO: Seletor de Médias
medias_disponiveis = [50, 100, 200]
medias_selecionadas = st.sidebar.multiselect(
    "Médias para o Cálculo:",
    options=medias_disponiveis,
    default=[50, 100, 200],
    help="Escolha quais médias móveis entrarão na soma do indicador."
)

janela_zscore = st.sidebar.number_input(
    "Janela de Lookback (Z-Score)", 
    value=252, 
    help="Quantos dias olhar para trás para calcular a média e desvio padrão históricos."
)

# --- Função de Cálculo ---
def carregar_dados(ticker, periodo=None, inicio=None, fim=None):
    try:
        # Baixa dados do Yahoo Finance
        if periodo:
            df = yf.download(ticker, period=periodo, progress=False)
        else:
            df = yf.download(ticker, start=inicio, end=fim, progress=False)
        
        if df.empty:
            st.error("Nenhum dado encontrado para este ativo ou período.")
            return None

        # Tratamento de MultiIndex (Correção do Yahoo Finance)
        if isinstance(df.columns, pd.MultiIndex):
            try:
                # Tenta pegar apenas o nível do ticker se existir, senão pega o nível 0
                df.columns = df.columns.get_level_values(0)
            except:
                pass

        # Prioriza 'Adj Close', se não tiver, usa 'Close'
        if 'Adj Close' in df.columns:
            df = df[['Adj Close']].copy()
            df.columns = ['Close'] 
        elif 'Close' in df.columns:
            df = df[['Close']].copy()
        else:
            st.error("Erro: Coluna de preço não encontrada nos dados retornados.")
            return None

        # Remove linhas vazias
        df.dropna(inplace=True)
        return df
    except Exception as e:
        st.error(f"Erro ao processar dados: {e}")
        return None

# --- Processamento ---
# Se não tiver média selecionada, avisa o usuário
if not medias_selecionadas:
    st.warning("⚠️ Por favor, selecione pelo menos uma média móvel na barra lateral.")
else:
    dados = carregar_dados(ticker, periodo_yfinance, start_date, end_date)

    if dados is not None and not dados.empty:
        # Verifica dados suficientes (Maior média + Janela Z-Score)
        maior_media = max(medias_selecionadas)
        dias_necessarios = maior_media + janela_zscore
        
        if len(dados) < dias_necessarios:
            st.warning(f"⚠️ Atenção: Você tem {len(dados)} dias de dados, mas precisa de aprox. {dias_necessarios} para o cálculo preciso (Média {maior_media} + Z-Score {janela_zscore}). Considere aumentar o período para '5y' ou 'max'.")
        
        # 1. Calcular as Médias e Distâncias (Loop dinâmico)
        dados['Soma_Distancias'] = 0
        colunas_para_exibir = ['Close'] # Lista para montar a tabela final

        for media in medias_selecionadas:
            nome_ma = f'MA{media}'
            nome_dist = f'Dist_{media}'
            
            # Cria a coluna da Média
            dados[nome_ma] = dados['Close'].rolling(window=media).mean()
            
            # Cria a coluna da Distância
            dados[nome_dist] = (dados['Close'] - dados[nome_ma]) / dados[nome_ma]
            
            # Adiciona na soma total
            dados['Soma_Distancias'] += dados[nome_dist]
            
            # Adiciona na lista para exibir na tabela depois
            colunas_para_exibir.append(nome_ma)

        # 2. Calcular Z-Score
        dados['Media_Hist_Indicador'] = dados['Soma_Distancias'].rolling(window=janela_zscore).mean()
        dados['Std_Hist_Indicador'] = dados['Soma_Distancias'].rolling(window=janela_zscore).std()
        
        dados['Z_Score'] = (dados['Soma_Distancias'] - dados['Media_Hist_Indicador']) / dados['Std_Hist_Indicador']

        # Remover NaN inicial
        dados_clean = dados.dropna()

        if dados_clean.empty:
            st.error("Não há dados suficientes para gerar o gráfico. Aumente o período de dados ou diminua os parâmetros.")
        else:
            ultimo_z = dados_clean['Z_Score'].iloc[-1]
            ultimo_preco = dados_clean['Close'].iloc[-1]

            # --- Exibição de Métricas ---
            col1, col2, col3 = st.columns(3)
            col1.metric("Preço Atual", f"R$ {ultimo_preco:.2f}")
            col2.metric("Z-Score Atual", f"{ultimo_z:.2f}", delta_color="inverse")
            
            status = "Neutro"
            if ultimo_z > 2: status = "⚠️ Sobrecompra (Caro)"
            elif ultimo_z < -2: status = "⚠️ Sobrevenda (Barato)"
            col3.metric("Status Estatístico", status)

            # --- Gráfico 1: O Indicador ao Longo do Tempo ---
            st.subheader("1. Evolução do Indicador (Z-Score)")
            
            fig_line = go.Figure()
            
            fig_line.add_trace(go.Scatter(x=dados_clean.index, y=dados_clean['Z_Score'], 
                                          mode='lines', name='Z-Score', line=dict(color='blue', width=2)))
            
            fig_line.add_hline(y=2, line_dash="dash", line_color="red", annotation_text="+2 Desvios (Venda)")
            fig_line.add_hline(y=-2, line_dash="dash", line_color="green", annotation_text="-2 Desvios (Compra)")
            fig_line.add_hline(y=0, line_color="gray", opacity=0.5)

            fig_line.update_layout(height=500, template="plotly_white", xaxis_title="Data", yaxis_title="Desvios Padrão")
            st.plotly_chart(fig_line, use_container_width=True)

            # --- Gráfico 2: A Curva de Sino (Histograma) ---
            st.subheader("2. Distribuição Estatística (Curva de Sino)")
            st.markdown("Este gráfico mostra a frequência dos valores. Compre nas pontas da esquerda, venda nas pontas da direita.")

            fig_hist = go.Figure()

            fig_hist.add_trace(go.Histogram(x=dados_clean['Z_Score'], nbinsx=100, 
                                            name='Histórico', marker_color='lightgray', opacity=0.7))

            fig_hist.add_vline(x=ultimo_z, line_width=4, line_color="red", 
                               annotation_text="VOCÊ ESTÁ AQUI", annotation_position="top")

            fig_hist.update_layout(height=400, template="plotly_white", xaxis_title="Valor do Z-Score", yaxis_title="Frequência")
            st.plotly_chart(fig_hist, use_container_width=True)

            with st.expander("Ver dados brutos recentes"):
                # Adiciona as colunas finais na lista
                colunas_finais = colunas_para_exibir + ['Soma_Distancias', 'Z_Score']
                st.dataframe(dados_clean[colunas_finais].tail(10))

    else:
        st.info("Aguardando carregamento dos dados...")
