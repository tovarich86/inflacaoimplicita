import streamlit as st
import pandas as pd
import requests
from io import StringIO
import numpy as np
from scipy.interpolate import interp1d
from scipy.spatial import cKDTree

# Explicação do cálculo
st.title("📊 Cálculo da Inflação Implícita - Tesouro Direto")
st.markdown("""
### Como a Inflação Implícita é Calculada?
A **Inflação Implícita** representa a expectativa de inflação embutida na diferença entre as taxas de juros do **Tesouro Prefixado** e do **Tesouro IPCA+**.

A fórmula utilizada é:

\[
\text{Inflação Implícita} = \left(\frac{1 + \text{Taxa Prefixada}}{1 + \text{Taxa IPCA}}\right) - 1
\]

Essa inflação reflete a **expectativa de inflação futura** entre a **data base** e a **data de vencimento do título**.

A **Inflação Interpolada** é calculada para estimar a inflação implícita **até o vencimento desejado pelo usuário**.
""")

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

# Seleção da data base com calendário até a última data disponível
min_date = df["Data Base"].min()
max_date = df["Data Base"].max()

data_base_input = st.date_input("📅 Selecione a Data Base:", max_value=max_date, min_value=min_date, value=max_date)
vencimento_input = st.date_input("📅 Escolha o vencimento desejado:")

# Converter entrada para datetime
data_base_input = pd.to_datetime(data_base_input)
vencimento_input_num = int(vencimento_input.strftime("%Y%m%d"))

# 🔄 Atualizar os dados dinamicamente
@st.cache_data(ttl=0)
def filter_data(df, data_base_input):
    return df[df["Data Base"] == data_base_input].copy()

df_filtered = filter_data(df, data_base_input)

# Verificar se há títulos disponíveis para a data selecionada
if df_filtered.empty:
    st.warning("⚠️ Nenhum título disponível para essa Data Base. Escolha outra data.")
    st.stop()

# Separar títulos prefixados e IPCA+
df_prefixado = df_filtered[df_filtered["Tipo Titulo"].str.contains("Prefixado", case=False, na=False) & 
                           ~df_filtered["Tipo Titulo"].str.contains("Juros Semestrais", case=False, na=False)].copy()

df_ipca = df_filtered[df_filtered["Tipo Titulo"].str.contains("Tesouro IPCA\\+$", regex=True, case=False, na=False)].copy()  # Apenas Tesouro IPCA+ sem juros semestrais

# Verificar se há títulos prefixados disponíveis
if df_prefixado.empty:
    st.warning("⚠️ Nenhum título Prefixado disponível para essa Data Base.")
    st.stop()

# Verificar se há títulos IPCA disponíveis corretamente
if df_ipca.empty:
    st.warning("⚠️ Nenhum título Tesouro IPCA+ disponível para essa Data Base.")
    st.stop()

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
    if len(df_ipca_sorted) == 0:
        return np.nan, np.nan  # Evita erro caso não haja títulos IPCA+
    _, idx = tree.query([[vencimento_num]])
    return df_ipca_sorted.iloc[idx[0]]["Data Vencimento"], df_ipca_sorted.iloc[idx[0]]["Taxa Compra Manha"]

# Aplicar busca do título IPCA+ mais próximo
df_prefixado["Vencimento Mais Próximo"], df_prefixado["Taxa IPCA Correspondente"] = zip(
    *df_prefixado["Vencimento_Num"].apply(find_nearest_vencimento)
)

# Calcular a inflação implícita original
df_prefixado["Inflação Implícita"] = ((1 + df_prefixado["Taxa Compra Manha"] / 100) /
                                      (1 + df_prefixado["Taxa IPCA Correspondente"] / 100) - 1) * 100

# Interpolação para a inflação até o vencimento desejado
if len(df_ipca_sorted) >= 2:
    f_interp = interp1d(df_ipca_sorted["Vencimento_Num"], df_ipca_sorted["Taxa Compra Manha"], kind="linear", fill_value="extrapolate")
    taxa_ipca_interpolada = f_interp(vencimento_input_num)
    df_prefixado["Inflação Interpolada"] = ((1 + df_prefixado["Taxa Compra Manha"] / 100) /
                                            (1 + taxa_ipca_interpolada / 100) - 1) * 100
else:
    df_prefixado["Inflação Interpolada"] = np.nan

# Criar DataFrame final
df_resultado = df_prefixado[[
    "Data Base", "Tipo Titulo", "Data Vencimento", "Taxa Compra Manha", 
    "Vencimento Mais Próximo", "Taxa IPCA Correspondente", "Inflação Implícita", "Inflação Interpolada"
]].copy()

df_resultado.rename(columns={
    "Tipo Titulo": "Tipo Título",
    "Taxa Compra Manha": "Taxa Prefixada Correspondente"
}, inplace=True)

# Criar arquivo Excel para download
@st.cache_data(ttl=0)
def convert_df_to_excel(df):
    output = StringIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Resultado")
    return output.getvalue()

excel_data = convert_df_to_excel(df_resultado)

# Exibir tabela no Streamlit
st.subheader("📊 Resultado do Cálculo")
st.dataframe(df_resultado)

# Botão para download do Excel final
st.download_button(
    label="📥 Baixar Resultado (Excel)",
    data=excel_data,
    file_name="resultado_inflacao.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
