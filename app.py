import streamlit as st
import pandas as pd
import requests
from io import StringIO
import numpy as np
from scipy.interpolate import interp1d
from scipy.spatial import cKDTree

# Função para carregar os dados do Tesouro Direto
@st.cache_data
def load_treasury_data():
    url = "https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/PrecoTaxaTesouroDireto.csv"
    response = requests.get(url)
    csv_data = StringIO(response.text)
    
    # Carregar o CSV garantindo que as datas sejam interpretadas corretamente
    df = pd.read_csv(csv_data, sep=';', decimal=',', parse_dates=['Data Base', 'Data Vencimento'], dayfirst=True)
    
    return df

# Carregar os dados
df = load_treasury_data()

# Interface no Streamlit
st.title("Cálculo da Inflação Implícita - Tesouro Direto")

# Seleção da data base e vencimento
data_base_options = df["Data Base"].dt.strftime("%d/%m/%Y").unique()
data_base_input = st.selectbox("Selecione a Data Base:", data_base_options)

vencimento_input = st.date_input("Escolha o vencimento desejado:")

# Converter a entrada para datetime
data_base_input = pd.to_datetime(data_base_input, format="%d/%m/%Y")
vencimento_input_num = int(vencimento_input.strftime("%Y%m%d"))

# Filtrar os títulos apenas para a data base inserida
df_filtered = df[df["Data Base"] == data_base_input]

# Separar títulos prefixados e IPCA+
df_prefixado = df_filtered[df_filtered["Tipo Titulo"].str.contains("Prefixado") & ~df_filtered["Tipo Titulo"].str.contains("Juros Semestrais")].copy()
df_ipca = df_filtered[df_filtered["Tipo Titulo"].str.contains("IPCA")].copy()

# Converter colunas de data para datetime para evitar erros
df_ipca["Data Vencimento"] = pd.to_datetime(df_ipca["Data Vencimento"], errors='coerce')
df_prefixado["Data Vencimento"] = pd.to_datetime(df_prefixado["Data Vencimento"], errors='coerce')

# Criar botão para download do CSV original apenas com os títulos do resultado
csv_auditoria = df_filtered[df_filtered["Data Vencimento"].isin(df_prefixado["Data Vencimento"])]
csv_auditoria = csv_auditoria.to_csv(index=False, sep=";", decimal=",")

st.download_button(
    label="📥 Baixar CSV Completo (Auditoria)",
    data=csv_auditoria,
    file_name="dados_auditoria.csv",
    mime="text/csv"
)
