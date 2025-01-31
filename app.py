import streamlit as st
import pandas as pd
import requests
from io import BytesIO, StringIO
import numpy as np
from scipy.interpolate import interp1d
from scipy.spatial import cKDTree
import matplotlib.pyplot as plt

# Criar a imagem com a fórmula da Inflação Implícita
def generate_formula_image():
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.text(0.5, 0.5, 
            r"$\mathrm{Inflação\ Implícita} = \left(\frac{1 + \mathrm{Taxa\ Prefixada}}{1 + \mathrm{Taxa\ IPCA}}\right) - 1$",
            fontsize=18, ha='center', va='center')

    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_frame_on(False)

    # Salvar a imagem em um buffer
    img_path = "/mnt/data/inflacao_implicita_formula.png"
    plt.savefig(img_path, dpi=300, bbox_inches='tight', transparent=True)
    plt.close(fig)
    return img_path

# Gerar a imagem da fórmula
formula_image_path = generate_formula_image()

# URL do CSV original do Tesouro Nacional
CSV_URL = "https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/PrecoTaxaTesouroDireto.csv"

# Função para carregar os dados do Tesouro Direto
@st.cache_data
def load_treasury_data():
    response = requests.get(CSV_URL)
    csv_data = StringIO(response.text)
    df = pd.read_csv(csv_data, sep=';', decimal=',', parse_dates=['Data Base', 'Data Vencimento'], dayfirst=True)
    return df

# Carregar os dados
df = load_treasury_data()

# Interface no Streamlit
st.title("📊 Cálculo da Inflação Implícita - Tesouro Direto")

# Exibir a imagem da fórmula
st.image(formula_image_path, caption="Fórmula do Cálculo da Inflação Implícita", use_column_width=True)

# Botão para baixar o CSV original do Tesouro
st.download_button(
    label="📥 Baixar CSV Original do Tesouro",
    data=requests.get(CSV_URL).content,
    file_name="PrecoTaxaTesouroDireto.csv",
    mime="text/csv"
)

# Seleção da data base
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

# Verificar se há títulos disponíveis
if df_filtered.empty:
    st.warning("⚠️ Nenhum título disponível para essa Data Base. Escolha outra data.")
    st.stop()

# Separar títulos prefixados e IPCA+
df_prefixado = df_filtered[df_filtered["Tipo Titulo"].str.contains("Prefixado", case=False, na=False) & 
                           ~df_filtered["Tipo Titulo"].str.contains("Juros Semestrais", case=False, na=False)].copy()

df_ipca = df_filtered[df_filtered["Tipo Titulo"].str.contains("Tesouro IPCA\\+$", regex=True, case=False, na=False)].copy()  

# Verificar títulos disponíveis
if df_prefixado.empty:
    st.warning("⚠️ Nenhum título Prefixado disponível para essa Data Base.")
    st.stop()

if df_ipca.empty:
    st.warning("⚠️ Nenhum título Tesouro IPCA+ disponível para essa Data Base.")
    st.stop()

# Converter colunas de data para datetime
df_ipca["Data Vencimento"] = pd.to_datetime(df_ipca["Data Vencimento"], errors='coerce')
df_prefixado["Data Vencimento"] = pd.to_datetime(df_prefixado["Data Vencimento"], errors='coerce')

# Converter datas para números para interpolação
df_ipca["Vencimento_Num"] = df_ipca["Data Vencimento"].dt.strftime("%Y%m%d").astype(int)
df_prefixado["Vencimento_Num"] = df_prefixado["Data Vencimento"].dt.strftime("%Y%m%d").astype(int)

# Criar índice para busca eficiente do título IPCA+ mais próximo
df_ipca_sorted = df_ipca.sort_values("Vencimento_Num")
vencimentos_ipca = df_ipca_sorted["Vencimento_Num"].values.reshape(-1, 1)
tree = cKDTree(vencimentos_ipca)

# Função para encontrar o título IPCA+ mais próximo
def find_nearest_vencimento(vencimento_num):
    if len(df_ipca_sorted) == 0:
        return np.nan, np.nan  
    _, idx = tree.query([[vencimento_num]])
    return df_ipca_sorted.iloc[idx[0]]["Data Vencimento"], df_ipca_sorted.iloc[idx[0]]["Taxa Compra Manha"]

# Aplicar busca do título IPCA+ mais próximo
df_prefixado["Vencimento Mais Próximo"], df_prefixado["Taxa IPCA Correspondente"] = zip(
    *df_prefixado["Vencimento_Num"].apply(find_nearest_vencimento)
)

# Calcular a inflação implícita
df_prefixado["Inflação Implícita"] = ((1 + df_prefixado["Taxa Compra Manha"] / 100) /
                                      (1 + df_prefixado["Taxa IPCA Correspondente"] / 100) - 1) * 100

# Criar DataFrame final
df_resultado = df_prefixado[[
    "Data Base", "Tipo Titulo", "Data Vencimento", "Taxa Compra Manha", 
    "Vencimento Mais Próximo", "Taxa IPCA Correspondente", "Inflação Implícita"
]].copy()

df_resultado.rename(columns={
    "Tipo Titulo": "Tipo Título",
    "Taxa Compra Manha": "Taxa Prefixada Correspondente"
}, inplace=True)

# Criar arquivo Excel para download
def convert_df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Resultado")
    output.seek(0)  
    return output

# Criar arquivo Excel para download
excel_data = convert_df_to_excel(df_resultado)

# Exibir tabela no Streamlit
st.subheader("📊 Resultado do Cálculo")
st.dataframe(df_resultado)

# Botão para download do Excel
st.download_button(
    label="📥 Baixar Resultado (Excel)",
    data=excel_data,
    file_name="resultado_inflacao.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
