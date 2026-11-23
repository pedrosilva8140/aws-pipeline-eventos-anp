"""Transformação do CSV da ANP (já validado) em Parquet particionado por ano/mês.

Funções puras: recebem DataFrame e devolvem DataFrame, bytes ou texto. Sem boto3.
"""

import io
from pathlib import PurePosixPath

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from processador.validacao import converter_data, converter_decimal

MAPA_COLUNAS: dict[str, str] = {
    "Regiao - Sigla": "regiao",
    "Estado - Sigla": "uf",
    "Municipio": "municipio",
    "Revenda": "revenda",
    "CNPJ da Revenda": "cnpj",
    "Nome da Rua": "nome_rua",
    "Numero Rua": "numero_rua",
    "Complemento": "complemento",
    "Bairro": "bairro",
    "Cep": "cep",
    "Produto": "produto",
    "Data da Coleta": "data_coleta",
    "Valor de Venda": "valor_venda",
    "Valor de Compra": "valor_compra",
    "Unidade de Medida": "unidade_medida",
    "Bandeira": "bandeira",
}
COLUNAS_DECIMAIS = ("valor_venda", "valor_compra")


def tipo_parquet(coluna: str) -> pa.DataType:
    if coluna == "data_coleta":
        return pa.date32()
    if coluna in COLUNAS_DECIMAIS:
        return pa.float64()
    return pa.string()


ESQUEMA_PARQUET = pa.schema([(c, tipo_parquet(c)) for c in MAPA_COLUNAS.values()])


def transformar(df: pd.DataFrame) -> pd.DataFrame:
    """Renomeia colunas, limpa texto e converte tipos. Não altera o DataFrame recebido."""
    saida = pd.DataFrame(index=df.index)
    for original, nova in MAPA_COLUNAS.items():
        texto = df[original].astype(str).str.strip()
        if nova == "data_coleta":
            saida[nova] = converter_data(texto).dt.date
        elif nova in COLUNAS_DECIMAIS:
            saida[nova] = converter_decimal(texto).astype("float64")
        elif nova == "cnpj":
            saida[nova] = texto.str.replace(r"\D", "", regex=True)
        else:
            saida[nova] = texto.astype(object).where(texto != "", None)
    return saida.reset_index(drop=True)


def dividir_por_mes(df: pd.DataFrame) -> dict[tuple[int, int], pd.DataFrame]:
    """Separa o DataFrame transformado por (ano, mes) da data de coleta."""
    datas = pd.to_datetime(df["data_coleta"])
    grupos = df.groupby([datas.dt.year, datas.dt.month])
    return {(int(ano), int(mes)): parte.reset_index(drop=True) for (ano, mes), parte in grupos}


def para_parquet(df: pd.DataFrame) -> bytes:
    tabela = pa.Table.from_pandas(df, schema=ESQUEMA_PARQUET, preserve_index=False)
    buffer = io.BytesIO()
    pq.write_table(tabela, buffer)
    return buffer.getvalue()


def chave_saida(chave_entrada: str, ano: int, mes: int) -> str:
    """Nome de saída derivado do de entrada: reprocessar sobrescreve, não duplica."""
    nome = PurePosixPath(chave_entrada).stem
    return f"processado/ano={ano:04d}/mes={mes:02d}/{nome}.parquet"
