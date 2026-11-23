import io
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from processador.transformacao import (
    MAPA_COLUNAS,
    chave_saida,
    dividir_por_mes,
    para_parquet,
    transformar,
)
from processador.validacao import ler_csv

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def df_bruto() -> pd.DataFrame:
    return ler_csv((FIXTURES / "anp_valido.csv").read_bytes())


@pytest.fixture
def df_transformado(df_bruto: pd.DataFrame) -> pd.DataFrame:
    return transformar(df_bruto)


def test_transformar_renomeia_colunas_para_snake_case(df_transformado: pd.DataFrame):
    assert list(df_transformado.columns) == list(MAPA_COLUNAS.values())


def test_transformar_converte_primeira_linha(df_transformado: pd.DataFrame):
    linha = df_transformado.iloc[0]
    assert linha["uf"] == "BA"
    assert linha["revenda"] == "DT COMBUSTIVEIS LTDA EM RECUPERACAO JUDICIAL"
    assert linha["cnpj"] == "08546610000105"
    assert linha["produto"] == "GASOLINA ADITIVADA"
    assert linha["data_coleta"] == date(2026, 10, 1)
    assert linha["valor_venda"] == pytest.approx(6.89)
    assert linha["bandeira"] == "VIBRA"


def test_transformar_cnpj_fica_so_com_14_digitos(df_transformado: pd.DataFrame):
    assert df_transformado["cnpj"].str.fullmatch(r"\d{14}").all()


def test_transformar_valor_de_venda_e_float(df_transformado: pd.DataFrame):
    assert pd.api.types.is_float_dtype(df_transformado["valor_venda"])
    assert (df_transformado["valor_venda"] > 0).all()


def test_transformar_valor_de_compra_vazio_vira_nulo(df_transformado: pd.DataFrame):
    assert pd.api.types.is_float_dtype(df_transformado["valor_compra"])
    assert df_transformado["valor_compra"].isna().all()


def test_transformar_texto_vazio_vira_nulo(df_bruto: pd.DataFrame):
    vazios = df_bruto["Complemento"].str.strip() == ""
    df = transformar(df_bruto)
    assert vazios.any()
    assert df.loc[vazios.to_numpy(), "complemento"].isna().all()


def test_transformar_preserva_ponto_e_virgula_e_acentos(df_transformado: pd.DataFrame):
    textos = df_transformado.select_dtypes(exclude="number").astype(str)
    assert textos.apply(lambda col: col.str.contains(";", regex=False)).any(axis=None)
    assert textos.apply(lambda col: col.str.contains(r"[^\x00-\x7f]", regex=True)).any(axis=None)


def test_transformar_nao_altera_o_dataframe_de_entrada(df_bruto: pd.DataFrame):
    copia = df_bruto.copy()
    transformar(df_bruto)
    pd.testing.assert_frame_equal(df_bruto, copia)


def test_dividir_por_mes_separa_cada_mes(df_transformado: pd.DataFrame):
    df = df_transformado.copy()
    df.loc[df.index[:4], "data_coleta"] = date(2026, 9, 30)
    partes = dividir_por_mes(df)
    assert sorted(partes) == [(2026, 9), (2026, 10)]
    assert len(partes[(2026, 9)]) == 4
    assert len(partes[(2026, 10)]) == len(df) - 4


def test_para_parquet_grava_tipos_corretos(df_transformado: pd.DataFrame):
    tabela = pq.read_table(io.BytesIO(para_parquet(df_transformado)))
    assert tabela.num_rows == len(df_transformado)
    assert tabela.column_names == list(MAPA_COLUNAS.values())
    assert tabela.schema.field("data_coleta").type == pa.date32()
    assert tabela.schema.field("valor_venda").type == pa.float64()
    assert tabela.schema.field("valor_compra").type == pa.float64()
    assert tabela.schema.field("cnpj").type == pa.string()


def test_para_parquet_ida_e_volta_preserva_valores(df_transformado: pd.DataFrame):
    tabela = pq.read_table(io.BytesIO(para_parquet(df_transformado)))
    primeira = tabela.slice(0, 1).to_pylist()[0]
    assert primeira["cnpj"] == "08546610000105"
    assert primeira["data_coleta"] == date(2026, 10, 1)
    assert primeira["valor_venda"] == pytest.approx(6.89)
    assert primeira["valor_compra"] is None


@pytest.mark.parametrize(
    ("entrada", "ano", "mes", "esperado"),
    [
        (
            "entrada/precos-gasolina-etanol-2026-10.csv",
            2026,
            10,
            "processado/ano=2026/mes=10/precos-gasolina-etanol-2026-10.parquet",
        ),
        ("entrada/sub/arquivo.csv", 2026, 3, "processado/ano=2026/mes=03/arquivo.parquet"),
    ],
)
def test_chave_saida_deriva_do_nome_de_entrada(entrada: str, ano: int, mes: int, esperado: str):
    assert chave_saida(entrada, ano, mes) == esperado
