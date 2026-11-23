from pathlib import Path

import pandas as pd
import pytest

from processador.validacao import (
    COLUNAS_ESPERADAS,
    CsvMalFormado,
    decodificar,
    ler_csv,
    validar,
    validar_schema,
    validar_tipos,
)

FIXTURES = Path(__file__).parent / "fixtures"


def ler_fixture(nome: str) -> bytes:
    return (FIXTURES / nome).read_bytes()


def texto_dos_motivos(motivos: list[str]) -> str:
    return " | ".join(motivos)


def test_colunas_esperadas_sao_as_16_do_layout_da_anp():
    assert len(COLUNAS_ESPERADAS) == 16
    assert COLUNAS_ESPERADAS[0] == "Regiao - Sigla"
    assert COLUNAS_ESPERADAS[-1] == "Bandeira"


def test_decodificar_remove_bom_do_utf8():
    texto = decodificar(ler_fixture("anp_valido.csv"))
    assert texto.startswith("Regiao - Sigla;")


def test_decodificar_aceita_latin1_quando_nao_e_utf8():
    utf8 = decodificar(ler_fixture("anp_valido.csv"))
    latin1 = decodificar(ler_fixture("anp_valido_latin1.csv"))
    assert latin1 == utf8


def test_ler_csv_valido_mantem_colunas_e_linhas_como_texto():
    df = ler_csv(ler_fixture("anp_valido.csv"))
    assert tuple(df.columns) == COLUNAS_ESPERADAS
    assert len(df) == 19
    assert df["Valor de Venda"].iloc[0] == "6,89"
    assert df["Valor de Compra"].iloc[0] == ""


def test_ler_csv_preserva_ponto_e_virgula_dentro_de_aspas():
    df = ler_csv(ler_fixture("anp_valido.csv"))
    assert df.apply(lambda col: col.str.contains(";", regex=False)).any(axis=None)


def test_ler_csv_latin1_gera_o_mesmo_dataframe():
    utf8 = ler_csv(ler_fixture("anp_valido.csv"))
    latin1 = ler_csv(ler_fixture("anp_valido_latin1.csv"))
    pd.testing.assert_frame_equal(latin1, utf8)


def test_ler_csv_vazio_devolve_dataframe_sem_colunas():
    df = ler_csv(ler_fixture("anp_vazio.csv"))
    assert df.empty
    assert len(df.columns) == 0


@pytest.mark.parametrize(
    ("conteudo", "trecho"),
    [
        (b"a;b\r\n1;2\r\n1;2;3\r\n", "linha 3: esperados 2 campos, encontrados 3"),
        (b"a;b\r\n1;2;3;4\r\n", "linha 2: esperados 2 campos, encontrados 4"),
        (b"a;b;c\r\n1;2;3\r\n1;2\r\n", "linha 3: esperados 3 campos, encontrados 2"),
    ],
)
def test_ler_csv_rejeita_linha_com_quantidade_de_campos_diferente(conteudo: bytes, trecho: str):
    with pytest.raises(CsvMalFormado, match=trecho):
        ler_csv(conteudo)


def test_ler_csv_so_com_cabecalho_devolve_colunas_sem_linhas():
    df = ler_csv(ler_fixture("anp_so_cabecalho.csv"))
    assert tuple(df.columns) == COLUNAS_ESPERADAS
    assert df.empty


def test_validar_arquivo_valido():
    resultado = validar(ler_csv(ler_fixture("anp_valido.csv")))
    assert resultado.valido
    assert resultado.motivos == []


def test_validar_schema_aponta_coluna_ausente():
    resultado = validar_schema(ler_csv(ler_fixture("anp_schema_invalido.csv")))
    assert not resultado.valido
    assert "ausentes" in texto_dos_motivos(resultado.motivos)
    assert "Bandeira" in texto_dos_motivos(resultado.motivos)


def test_validar_schema_aponta_coluna_inesperada():
    df = ler_csv(ler_fixture("anp_valido.csv"))
    df["Coluna Nova"] = "x"
    resultado = validar_schema(df)
    assert not resultado.valido
    assert "inesperadas" in texto_dos_motivos(resultado.motivos)
    assert "Coluna Nova" in texto_dos_motivos(resultado.motivos)


def test_validar_schema_rejeita_arquivo_vazio():
    resultado = validar_schema(ler_csv(ler_fixture("anp_vazio.csv")))
    assert not resultado.valido
    assert "vazio" in texto_dos_motivos(resultado.motivos)


def test_validar_schema_rejeita_arquivo_so_com_cabecalho():
    resultado = validar_schema(ler_csv(ler_fixture("anp_so_cabecalho.csv")))
    assert not resultado.valido
    assert "sem linhas de dados" in texto_dos_motivos(resultado.motivos)


@pytest.mark.parametrize(
    ("coluna", "linha"),
    [("Valor de Venda", "linha 2"), ("Data da Coleta", "linha 3"), ("Produto", "linha 4")],
)
def test_validar_tipos_aponta_coluna_e_linha_invalidas(coluna: str, linha: str):
    resultado = validar_tipos(ler_csv(ler_fixture("anp_tipos_invalidos.csv")))
    assert not resultado.valido
    motivo = motivo_da_coluna(resultado.motivos, coluna)
    assert linha in motivo


def motivo_da_coluna(motivos: list[str], coluna: str) -> str:
    return next(m for m in motivos if f'"{coluna}"' in m)


def test_validar_tipos_usa_formato_neutro_nos_motivos():
    resultado = validar_tipos(ler_csv(ler_fixture("anp_tipos_invalidos.csv")))
    assert resultado.motivos == [
        "valor invalido em \"Valor de Venda\" (1 linha(s)): linha 2 ('abc')",
        "valor invalido em \"Data da Coleta\" (1 linha(s)): linha 3 ('31/02/2026')",
        "valor invalido em \"Produto\" (1 linha(s)): linha 4 ('')",
    ]


def test_validar_tipos_rejeita_valor_de_venda_zero_ou_negativo():
    df = ler_csv(ler_fixture("anp_valido.csv"))
    df.loc[0, "Valor de Venda"] = "0,00"
    df.loc[1, "Valor de Venda"] = "-1,50"
    resultado = validar_tipos(df)
    assert not resultado.valido
    assert "2 linha(s)" in texto_dos_motivos(resultado.motivos)


def test_validar_tipos_limita_exemplos_a_5():
    df = ler_csv(ler_fixture("anp_valido.csv"))
    df["Valor de Venda"] = "abc"
    resultado = validar_tipos(df)
    motivo = motivo_da_coluna(resultado.motivos, "Valor de Venda")
    assert "(19 linha(s))" in motivo
    assert motivo.count("linha ") == 5


def test_validar_com_schema_invalido_nao_tenta_validar_tipos():
    resultado = validar(ler_csv(ler_fixture("anp_schema_invalido.csv")))
    assert not resultado.valido
    assert len(resultado.motivos) == 1
