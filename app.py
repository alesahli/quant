import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- Configuração da Página ---
st.set_page_config(page_title="Painel Quant - Multi-Indicadores", layout="wide")

st.title("📊 Painel Quant: Z-Score & Estocástico de Médias")
st.markdown("""
Este painel analisa a distância do preço em relação a um conjunto de médias móveis.
Ele oferece duas visões: **Estatística (Z-Score)** para extremos e **Cíclica (Estocástico)** para timing.
""")

# ==============================================================================
# SIDEBAR - CONFIGURAÇÕES
# ==============================================================================
st.sidebar.header("1. Ativo e Dados")
ticker = st.sidebar.text_input("Ativo (Yahoo Finance)", value="PETR4.SA").upper()

# Seletor de Intervalo (Timeframe)
intervalo = st.sidebar.selectbox(
    "Timeframe (Intervalo)", 
    options=["1d", "1wk", "1mo", "1h", "30m", "15m", "5m", "1m"],
    index=0, # Padrão 1d
    help="Intervalos menores que 1d possuem histórico limitado pelo Yahoo Finance."
)

# Lógica de Período baseada no Intervalo (Limitação do Yahoo)
is_intraday = intervalo not in ["1d", "1wk", "1mo"]

if is_intraday:
    st.sidebar.warning(f"⚠️ Dados Intraday ({intervalo}) têm histórico curto no Yahoo.")
    # Para intraday, forçamos opções de período fixo que funcionem
    periodo_yfinance = st.sidebar.selectbox(
        "Período de Dados", 
        ["1d", "5d", "1mo", "60d"] if intervalo not in ['1h'] else ["1mo", "60d", "1y", "2y"],
        index=2
    )
    start_date, end_date = None, None
else:
    # Para Diário/Semanal, mantemos a flexibilidade total
    tipo_data = st.sidebar.radio("Tipo de Período:", ["Período Fixo", "Data Personalizada"])
    
    if tipo_data == "Período Fixo":
        periodo_yfinance = st.sidebar.selectbox(
            "Janela de Tempo", ["1y", "2y", "5y", "10y", "max"], index=2
        )
        start_date, end_date = None, None
    else:
        periodo_yfinance = None
        c1, c2 = st.sidebar.columns(2)
        start_date = c1.date_input("Início", value=datetime.today() - timedelta(days=365*5))
        end_date = c2.date_input("Fim", value=datetime.today())

st.sidebar.markdown("---")
st.sidebar.header("2. Parâmetros dos Indicadores")

# Input de Médias Flexíveis
medias_input = st.sidebar.text_input(
    "Médias Móveis (separadas por vírgula)", 
    value="50, 100, 200",
    help="Exemplo: 20, 50 ou 9, 21, 200. O sistema somará a distância para todas essas médias."
)

# Processar o input de texto para virar uma lista de números
try:
    medias_selecionadas = [int(x.strip()) for x in medias_input.split(',') if x.strip().isdigit()]
    if not medias_selecionadas:
        st.error("Por favor, insira pelo menos um número válido para as médias.")
        st.stop()
except:
    st.error("Erro ao ler as médias. Use formato: 50, 100, 200")
    st.stop()

# Parâmetros Específicos
c_zscore, c_stoch = st.sidebar.columns(2) # Layout visual na sidebar
janela_zscore = st.sidebar.number_input("Lookback Z-Score", value=252, min_value=10)
janela_stoch = st.sidebar.number_input("Lookback Estocástico", value=20, min_value=5, help="O 'X' da fórmula do estocástico.")

# ==============================================================================
# FUNÇÕES DE CÁLCULO
# ==============================================================================
def carregar_dados(ticker, intervalo, period=None, start=None, end=None):
    try:
        if period:
            df = yf.download(ticker, period=period, interval=intervalo, progress=False)
        else:
            df = yf.download(ticker, start=start, end=end, interval=intervalo, progress=False)
        
        # Tratamento MultiIndex (Yahoo Atualizado)
        if isinstance(df.columns, pd.MultiIndex):
            try:
                df.columns = df.columns.get_level_values(0)
            except: pass
            
        # Seleção de Coluna de Preço
        col_price = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
        if col_price not in df.columns:
            return None
            
        df = df[[col_price]].copy()
        df.columns = ['Close']
        df.dropna(inplace=True)
        return df
    except Exception as e:
        return None

# ==============================================================================
# PROCESSAMENTO PRINCIPAL
# ==============================================================================
dados = carregar_dados(ticker, intervalo, periodo_yfinance, start_date, end_date)

if dados is not None and not dados.empty:
    
    # 1. Calcular Médias e Distâncias
    dados['Soma_Distancias'] = 0
    maior_media = max(medias_selecionadas)
    
    # Verifica se tem dados suficientes para a maior média
    if len(dados) < maior_media:
        st.error(f"Erro: O período selecionado retornou apenas {len(dados)} candles, mas você pediu uma média de {maior_media}. Aumente o período ou diminua a média.")
        st.stop()

    for media in medias_selecionadas:
        col_ma = f'MA_{media}'
        dados[col_ma] = dados['Close'].rolling(window=media).mean()
        # Distância %
        dados[f'Dist_{media}'] = (dados['Close'] - dados[col_ma]) / dados[col_ma]
        dados['Soma_Distancias'] += dados[f'Dist_{media}']

    # 2. Calcular Z-Score (Estatístico)
    dados['Media_Hist_Soma'] = dados['Soma_Distancias'].rolling(window=janela_zscore).mean()
    dados['Std_Hist_Soma'] = dados['Soma_Distancias'].rolling(window=janela_zscore).std()
    dados['Z_Score'] = (dados['Soma_Distancias'] - dados['Media_Hist_Soma']) / dados['Std_Hist_Soma']

    # 3. Calcular Estocástico da Distância (Oscilador)
    # Fórmula: (Atual - Min_X) / (Max_X - Min_X) * 100
    min_rolling = dados['Soma_Distancias'].rolling(window=janela_stoch).min()
    max_rolling = dados['Soma_Distancias'].rolling(window=janela_stoch).max()
    
    # Evitar divisão por zero se max == min
    divisor = max_rolling - min_rolling
    divisor = divisor.replace(0, 1) # Substitui 0 por 1 para não quebrar, embora raro
    
    dados['Stoch_Dist'] = ((dados['Soma_Distancias'] - min_rolling) / divisor) * 100

    # Limpeza final (remove NaN gerados pelos lookbacks)
    dados_clean = dados.dropna()

    if dados_clean.empty:
        st.warning("Dados insuficientes após os cálculos. Tente aumentar o período de dados ou reduzir os lookbacks.")
    else:
        # Pega valores atuais
        ultimo_preco = dados_clean['Close'].iloc[-1]
        ultimo_z = dados_clean['Z_Score'].iloc[-1]
        ultimo_stoch = dados_clean['Stoch_Dist'].iloc[-1]

        # --- EXIBIÇÃO ---
        
        # Métricas de Topo
        m1, m2, m3 = st.columns(3)
        m1.metric("Preço Atual", f"{ultimo_preco:.2f}")
        m2.metric("Z-Score Atual", f"{ultimo_z:.2f}", delta_color="inverse")
        m3.metric("Estocástico Atual", f"{ultimo_stoch:.1f}", help="Escala de 0 a 100")

        # Abas para separar as análises
        tab1, tab2, tab3 = st.tabs(["📉 Análise Z-Score (Extremos)", "🌊 Análise Estocástico (Ciclos)", "📋 Dados Brutos"])

        # --- ABA 1: Z-SCORE ---
        with tab1:
            st.markdown(f"**Interpretação:** Mede o quão raro é o movimento atual comparado aos últimos **{janela_zscore} períodos**.")
            
            # Gráfico de Linha Z-Score
            fig_z = go.Figure()
            fig_z.add_trace(go.Scatter(x=dados_clean.index, y=dados_clean['Z_Score'], mode='lines', name='Z-Score', line=dict(color='#2962FF')))
            fig_z.add_hline(y=2, line_dash="dash", line_color="red", annotation_text="Venda (+2)")
            fig_z.add_hline(y=-2, line_dash="dash", line_color="green", annotation_text="Compra (-2)")
            fig_z.add_hline(y=0, line_color="gray", opacity=0.3)
            fig_z.update_layout(title="Evolução do Z-Score", height=400, template="plotly_white")
            st.plotly_chart(fig_z, use_container_width=True)

            # Histograma
            fig_hist = go.Figure()
            fig_hist.add_trace(go.Histogram(x=dados_clean['Z_Score'], nbinsx=100, marker_color='lightgray', name='Histórico'))
            fig_hist.add_vline(x=ultimo_z, line_width=3, line_color="red", annotation_text="AGORA")
            fig_hist.update_layout(title="Distribuição Normal (Curva de Sino)", height=350, template="plotly_white")
            st.plotly_chart(fig_hist, use_container_width=True)

        # --- ABA 2: ESTOCÁSTICO ---
        with tab2:
            st.markdown(f"**Interpretação:** Mostra a posição atual relativa ao range dos últimos **{janela_stoch} períodos**. (0 = Fundo do Canal, 100 = Topo do Canal).")
            
            fig_stoch = go.Figure()
            fig_stoch.add_trace(go.Scatter(x=dados_clean.index, y=dados_clean['Stoch_Dist'], mode='lines', name='Stoch', line=dict(color='#FF6D00', width=2)))
            
            # Zonas de Sobrecompra/Sobrevenda do Estocástico
            fig_stoch.add_hrect(y0=80, y1=100, fillcolor="red", opacity=0.1, line_width=0, annotation_text="Zona de Venda")
            fig_stoch.add_hrect(y0=0, y1=20, fillcolor="green", opacity=0.1, line_width=0, annotation_text="Zona de Compra")
            fig_stoch.add_hline(y=50, line_dash="dot", line_color="gray")
            
            fig_stoch.update_layout(title="Oscilador Estocástico da Distância", height=450, template="plotly_white", yaxis_range=[0, 100])
            st.plotly_chart(fig_stoch, use_container_width=True)

        # --- ABA 3: DADOS ---
        with tab3:
            st.dataframe(dados_clean.tail(50))

else:
    st.info("Aguardando carregamento... Se estiver usando Intraday, verifique se o ativo possui liquidez no horário atual.")
