import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- Configuração da Página ---
st.set_page_config(page_title="Painel Quant - Multi-Indicadores", layout="wide")

st.title("📊 Painel Quant: Z-Score & Estocástico")
st.markdown("""
Este painel analisa a distância do preço em relação a um conjunto de médias móveis.
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
    index=5, # Padrão 15m para testar intraday
    help="Intervalos menores que 1d possuem histórico limitado pelo Yahoo Finance."
)

is_intraday = intervalo not in ["1d", "1wk", "1mo"]

if is_intraday:
    st.sidebar.info(f"Modo Intraday ({intervalo}): O gráfico removerá os gaps da noite/fim de semana.")
    # Opções fixas para evitar erros do Yahoo
    periodo_yfinance = st.sidebar.selectbox(
        "Período de Dados", 
        ["1d", "5d", "1mo", "60d"] if intervalo not in ['1h'] else ["1mo", "60d", "1y", "2y"],
        index=1
    )
    start_date, end_date = None, None
else:
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
st.sidebar.header("2. Parâmetros")

# Input de Médias
medias_input = st.sidebar.text_input(
    "Médias Móveis (separadas por vírgula)", 
    value="21, 50, 200"
)

try:
    medias_selecionadas = [int(x.strip()) for x in medias_input.split(',') if x.strip().isdigit()]
    if not medias_selecionadas: raise ValueError
except:
    st.error("Erro nas médias. Use formato: 50, 100")
    st.stop()

# Parâmetros Específicos
c_zscore, c_stoch = st.sidebar.columns(2)
janela_zscore = st.sidebar.number_input("Lookback Z-Score", value=20, min_value=5) # Reduzi o padrão para testar intraday
janela_stoch = st.sidebar.number_input("Lookback Estocástico", value=14, min_value=3)

# ==============================================================================
# FUNÇÕES DE CÁLCULO E PLOTAGEM
# ==============================================================================
def carregar_dados(ticker, intervalo, period=None, start=None, end=None):
    try:
        if period:
            df = yf.download(ticker, period=period, interval=intervalo, progress=False)
        else:
            df = yf.download(ticker, start=start, end=end, interval=intervalo, progress=False)
        
        if isinstance(df.columns, pd.MultiIndex):
            try: df.columns = df.columns.get_level_values(0)
            except: pass
            
        col_price = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
        if col_price not in df.columns: return None
            
        df = df[[col_price]].copy()
        df.columns = ['Close']
        df.dropna(inplace=True)
        return df
    except Exception:
        return None

def formatar_grafico(fig, titulo, y_title, is_stoch=False):
    """Aplica formatação padrão para melhorar usabilidade"""
    
    # Configurações do Eixo X (Gaps e Zoom)
    fig.update_xaxes(
        rangeslider_visible=True,  # Habilita o slider inferior
        type='category',           # REMOVE OS GAPS (Trata datas como texto sequencial)
        nticks=10,                 # Evita poluição de datas no eixo X
        showgrid=False
    )
    
    # Configurações Gerais
    fig.update_layout(
        title=titulo,
        template="plotly_white",
        height=500,
        hovermode="x unified",     # Crosshair que mostra todos os valores
        margin=dict(l=50, r=50, t=50, b=50),
        yaxis_title=y_title
    )

    # Travamento do Eixo Y para o Estocástico
    if is_stoch:
        fig.update_yaxes(
            range=[-5, 105], # Trava entre 0 e 100 com margem
            fixedrange=True, # IMPEDE o usuário de dar zoom vertical e perder a escala
            showgrid=True,
            gridcolor='lightgray'
        )
    else:
        # Para Z-Score, permite zoom vertical, mas adiciona linha zero
        fig.add_hline(y=0, line_color="black", opacity=0.3)

    return fig

# ==============================================================================
# PROCESSAMENTO PRINCIPAL
# ==============================================================================
dados = carregar_dados(ticker, intervalo, periodo_yfinance, start_date, end_date)

if dados is not None and not dados.empty:
    
    # Cálculos
    dados['Soma_Distancias'] = 0
    maior_media = max(medias_selecionadas)
    
    if len(dados) < maior_media:
        st.error(f"Dados insuficientes ({len(dados)} candles) para média de {maior_media}.")
        st.stop()

    for media in medias_selecionadas:
        col_ma = f'MA_{media}'
        dados[col_ma] = dados['Close'].rolling(window=media).mean()
        dados[f'Dist_{media}'] = (dados['Close'] - dados[col_ma]) / dados[col_ma]
        dados['Soma_Distancias'] += dados[f'Dist_{media}']

    # Z-Score
    dados['Media_Hist_Soma'] = dados['Soma_Distancias'].rolling(window=janela_zscore).mean()
    dados['Std_Hist_Soma'] = dados['Soma_Distancias'].rolling(window=janela_zscore).std()
    dados['Z_Score'] = (dados['Soma_Distancias'] - dados['Media_Hist_Soma']) / dados['Std_Hist_Soma']

    # Estocástico
    min_rolling = dados['Soma_Distancias'].rolling(window=janela_stoch).min()
    max_rolling = dados['Soma_Distancias'].rolling(window=janela_stoch).max()
    divisor = (max_rolling - min_rolling).replace(0, 1)
    dados['Stoch_Dist'] = ((dados['Soma_Distancias'] - min_rolling) / divisor) * 100

    dados_clean = dados.dropna()

    if dados_clean.empty:
        st.warning("Dados insuficientes após cálculos.")
    else:
        # --- EXIBIÇÃO ---
        ultimo_preco = dados_clean['Close'].iloc[-1]
        ultimo_z = dados_clean['Z_Score'].iloc[-1]
        ultimo_stoch = dados_clean['Stoch_Dist'].iloc[-1]

        m1, m2, m3 = st.columns(3)
        m1.metric("Preço Atual", f"{ultimo_preco:.2f}")
        m2.metric("Z-Score", f"{ultimo_z:.2f}", delta_color="inverse")
        m3.metric("Estocástico", f"{ultimo_stoch:.0f}")

        tab1, tab2, tab3 = st.tabs(["📉 Z-Score", "🌊 Estocástico", "📋 Dados"])

        # --- GRÁFICO Z-SCORE ---
        with tab1:
            fig_z = go.Figure()
            # Usamos o índice formatado como string para garantir o tipo 'category' sem bugar
            x_axis = dados_clean.index.strftime('%Y-%m-%d %H:%M') if is_intraday else dados_clean.index.strftime('%Y-%m-%d')
            
            fig_z.add_trace(go.Scatter(x=x_axis, y=dados_clean['Z_Score'], mode='lines', name='Z-Score', line=dict(color='#2962FF')))
            fig_z.add_hline(y=2, line_dash="dash", line_color="red", annotation_text="Venda")
            fig_z.add_hline(y=-2, line_dash="dash", line_color="green", annotation_text="Compra")
            
            fig_z = formatar_grafico(fig_z, "Z-Score (Desvios Padrão)", "Desvios")
            st.plotly_chart(fig_z, use_container_width=True)

        # --- GRÁFICO ESTOCÁSTICO ---
        with tab2:
            fig_stoch = go.Figure()
            x_axis = dados_clean.index.strftime('%Y-%m-%d %H:%M') if is_intraday else dados_clean.index.strftime('%Y-%m-%d')

            fig_stoch.add_trace(go.Scatter(x=x_axis, y=dados_clean['Stoch_Dist'], mode='lines', name='Stoch', line=dict(color='#FF6D00', width=2)))
            
            # Zonas
            fig_stoch.add_hrect(y0=80, y1=100, fillcolor="red", opacity=0.1, line_width=0)
            fig_stoch.add_hrect(y0=0, y1=20, fillcolor="green", opacity=0.1, line_width=0)
            fig_stoch.add_hline(y=50, line_dash="dot", line_color="gray")
            
            fig_stoch = formatar_grafico(fig_stoch, "Estocástico da Distância (0-100)", "Oscilador", is_stoch=True)
            st.plotly_chart(fig_stoch, use_container_width=True)

        with tab3:
            st.dataframe(dados_clean.tail(50))

else:
    st.info("Aguardando carregamento...")
