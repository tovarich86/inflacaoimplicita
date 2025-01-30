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
    
    # Carregar CSV garantindo que as datas sejam interpretadas corretamente
    df = pd.read_csv(csv_data, sep=';', decimal=',', parse_dates=['Data Base', 'Data Vencimento'], dayfirst=True)
    return df

# Carregar os dados
df = load_treasury_data()

# Interface no Streamlit
st.title("📊 Cálculo da Inflação Implícita - Tesouro Direto")

# Seleção da data base com calendário até a última data disponível
min_date = df["Data Base"].min()
max_date = df["Data Base"].max()

data_base_input = st.date_input("📅 Selecione a Data Base:", max_value=max_date, min_value=min_date, value=max_date)
vencimento_input = st.date_input("📅 Escolha o vencimento desejado:")

# Converter entrada para datetime
data_base_input = pd.to_datetime(data_base_input)
vencimento_input_num = int(vencimento_input.strftime("%Y%m%d"))

# Filtrar os títulos apenas para a data base inserida
df_filtered = df[df["Data Base"] == data_base_input]

# Separar títulos prefixados e IPCA+
df_prefixado = df_filtered[df_filtered["Tipo Titulo"].str.contains("Prefixado") & ~df_filtered["Tipo Titulo"].str.contains("Juros Semestrais")].copy()
df_ipca = df_filtered[df_filtered["Tipo Titulo"].str.contains("IPCA")].copy()

# Converter colunas de data para datetime para evitar erros
df_ipca["Data Vencimento"] = pd.to_datetime(df_ipca["Data Vencimento"], errors='coerce')
df_prefixado["Data Vencimento"] = pd.to_datetime(df_prefixado["Data Vencimento"], errors='coerce')

# Converter datas de vencimento para números para facilitar interpolação
df_ipca["Vencimento_Num"] = df_ipca["Data Vencimento"].dt.strftime("%Y%m%d").astype(int)
df_prefixado["Vencimento_Num"] = df_prefixado["Data Vencimento"].dt.strftime("%Y%m%d").astype(int)

# Criar índice para busca eficiente do título IPCA+ mais próximo
df_ipca_sorted = df_ipca.sort_values("Vencimento_Num")
vencimentos_ipca = df_ipca_sorted["Vencimento_Num"].values.reshape(-1, 1)
tree = cKDTree(vencimentos_ipca)

# Função para encontrar o título IPCA+ mais próximo
def find_nearest_vencimento(vencimento_num):
    _, idx = tree.query([[vencimento_num]])
    return df_ipca_sorted.iloc[idx[0]]["Data Vencimento"], df_ipca_sorted.iloc[idx[0]]["Taxa Compra Manha"]

# Aplicar busca do título IPCA+ mais próximo
df_prefixado["Vencimento Mais Próximo"], df_prefixado["Taxa IPCA Correspondente"] = zip(
    *df_prefixado["Vencimento_Num"].apply(find_nearest_vencimento)
)

# Calcular a inflação implícita original
df_prefixado["Inflação Implícita"] = ((1 + df_prefixado["Taxa Compra Manha"] / 100) /
                                      (1 + df_prefixado["Taxa IPCA Correspondente"] / 100) - 1) * 100

# Interpolação para o vencimento escolhido pelo usuário
if len(df_ipca_sorted) >= 2:
    f_interp = interp1d(df_ipca_sorted["Vencimento_Num"], df_ipca_sorted["Taxa Compra Manha"], kind="linear", fill_value="extrapolate")
    taxa_ipca_interpolada = f_interp(vencimento_input_num)
else:
    taxa_ipca_interpolada = np.nan  # Se não houver dados suficientes, não interpolamos

# Calcular a inflação implícita interpolada
df_prefixado["Inflação Implícita Interpolada"] = ((1 + df_prefixado["Taxa Compra Manha"] / 100) /
                                                  (1 + taxa_ipca_interpolada / 100) - 1) * 100

# Adicionar colunas descritivas
df_prefixado["Título Prefixado"] = df_prefixado["Tipo Titulo"]
df_prefixado["Taxa Prefixado"] = df_prefixado["Taxa Compra Manha"]
df_prefixado["Título IPCA"] = "Tesouro IPCA+"
df_prefixado["Taxa IPCA Interpolada"] = taxa_ipca_interpolada

# Ajustar formato de datas para DD/MM/YYYY e números para PT-BR
df_prefixado["Data Base"] = df_prefixado["Data Base"].dt.strftime("%d/%m/%Y")
df_prefixado["Data Vencimento"] = df_prefixado["Data Vencimento"].dt.strftime("%d/%m/%Y")
df_prefixado["Vencimento Mais Próximo"] = df_prefixado["Vencimento Mais Próximo"].dt.strftime("%d/%m/%Y")

# Formatar números PT-BR
df_resultado = df_prefixado[[
    'Data Base', 'Título Prefixado', 'Data Vencimento', 'Taxa Prefixado',
    'Título IPCA', 'Vencimento Mais Próximo', 'Taxa IPCA Correspondente', 'Inflação Implícita',
    'Taxa IPCA Interpolada', 'Inflação Implícita Interpolada'
]].copy()
df_resultado = df_resultado.style.format({
    "Taxa Prefixado": "{:.2f}",
    "Taxa IPCA Correspondente": "{:.2f}",
    "Inflação Implícita": "{:.2f}",
    "Taxa IPCA Interpolada": "{:.2f}",
    "Inflação Implícita Interpolada": "{:.2f}"
}, decimal=",", thousands=".")

# Exibir tabela no Streamlit
st.subheader("📊 Resultado do Cálculo")
st.dataframe(df_resultado)

# Criar CSV para download contendo apenas os títulos utilizados
csv_auditoria = df_filtered[df_filtered["Data Vencimento"].isin(df_prefixado["Data Vencimento"])]
csv_auditoria = csv_auditoria.to_csv(index=False, sep=";", decimal=".")

# Botão para download do CSV final
st.download_button(
    label="📥 Baixar Resultado",
    data=df_prefixado.to_csv(index=False, sep=";", decimal="."),
    file_name="resultado_inflacao.csv",
    mime="text/csv"
)

# Botão para download do CSV de auditoria
st.download_button(
    label="📥 Baixar CSV Auditoria",
    data=csv_auditoria,
    file_name="dados_auditoria.csv",
    mime="text/csv"
)
