import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Configuração da Página
st.set_page_config(page_title="Painel Quant - Z-Score", layout="wide")

st.title("📊 Painel de Reversão à Média (Z-Score)")
st.markdown("""
Este painel calcula o afastamento do preço em relação às médias de **50, 100 e 200 períodos**.
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
        index=0  # Começa selecionando 1y
    )
else:
    col_data1, col_data2 = st.sidebar.columns(2)
    start_date = col_data1.date_input("Início", value=datetime.today() - timedelta(days=365))
    end_date = col_data2.date_input("Fim", value=datetime.today())

st.sidebar.markdown("---")
st.sidebar.markdown("### Parâmetros do Indicador")
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

        # CORREÇÃO DO ERRO (MultiIndex):
        # Se as colunas tiverem dois níveis (ex: Price, Ticker), pegamos apenas o nível do preço
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Ajuste para garantir que estamos usando apenas uma coluna de Preço
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
dados = carregar_dados(ticker, periodo_yfinance, start_date, end_date)

if dados is not None and not dados.empty:
    # Verifica se temos dados suficientes para o calculo
    if len(dados) < 200:
        st.warning("⚠️ Atenção: O período selecionado tem menos de 200 dias. As médias móveis longas não serão calculadas corretamente. Selecione um período maior.")
    
    # 1. Calcular as Médias Móveis
    dados['MA50'] = dados['Close'].rolling(window=50).mean()
    dados['MA100'] = dados['Close'].rolling(window=100).mean()
    dados['MA200'] = dados['Close'].rolling(window=200).mean()

    # 2. Calcular Distância Percentual
    dados['Dist_50'] = (dados['Close'] - dados['MA50']) / dados['MA50']
    dados['Dist_100'] = (dados['Close'] - dados['MA100']) / dados['MA100']
    dados['Dist_200'] = (dados['Close'] - dados['MA200']) / dados['MA200']

    # 3. Somar as Distâncias (Indicador Bruto)
    dados['Soma_Distancias'] = dados['Dist_50'] + dados['Dist_100'] + dados['Dist_200']

    # 4. Calcular Z-Score
    dados['Media_Hist_Indicador'] = dados['Soma_Distancias'].rolling(window=janela_zscore).mean()
    dados['Std_Hist_Indicador'] = dados['Soma_Distancias'].rolling(window=janela_zscore).std()
    
    dados['Z_Score'] = (dados['Soma_Distancias'] - dados['Media_Hist_Indicador']) / dados['Std_Hist_Indicador']

    # Remover NaN inicial
    dados_clean = dados.dropna()

    if dados_clean.empty:
        st.error("Não há dados suficientes para gerar o gráfico com essa janela de Z-Score. Tente diminuir o Lookback ou aumentar o período de dados.")
    else:
        # Último valor para exibir
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
        st.markdown("Este gráfico mostra a frequência dos valores. O objetivo é comprar quando o ponto vermelho (atual) estiver nas pontas da esquerda e vender quando estiver na direita.")

        fig_hist = go.Figure()

        fig_hist.add_trace(go.Histogram(x=dados_clean['Z_Score'], nbinsx=100, 
                                        name='Histórico', marker_color='lightgray', opacity=0.7))

        fig_hist.add_vline(x=ultimo_z, line_width=4, line_color="red", 
                           annotation_text="VOCÊ ESTÁ AQUI", annotation_position="top")

        fig_hist.update_layout(height=400, template="plotly_white", xaxis_title="Valor do Z-Score", yaxis_title="Frequência")
        st.plotly_chart(fig_hist, use_container_width=True)

        with st.expander("Ver dados brutos recentes"):
            st.dataframe(dados_clean[['Close', 'MA50', 'MA200', 'Soma_Distancias', 'Z_Score']].tail(10))

else:
    st.info("Aguardando carregamento dos dados...")
