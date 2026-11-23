"""Leitura e validação do CSV de preços da ANP.

Funções puras: recebem bytes ou DataFrame e devolvem DataFrame ou ResultadoValidacao.
Falha de dados nunca lança exceção; vira um ResultadoValidacao com os motivos.
"""

import csv
import io
from dataclasses import dataclass, field

import pandas as pd

COLUNAS_ESPERADAS: tuple[str, ...] = (
    "Regiao - Sigla",
    "Estado - Sigla",
    "Municipio",
    "Revenda",
    "CNPJ da Revenda",
    "Nome da Rua",
    "Numero Rua",
    "Complemento",
    "Bairro",
    "Cep",
    "Produto",
    "Data da Coleta",
    "Valor de Venda",
    "Valor de Compra",
    "Unidade de Medida",
    "Bandeira",
)
MAX_EXEMPLOS = 5
FORMATO_DATA = "%d/%m/%Y"


class CsvMalFormado(ValueError):
    """CSV inconsistente: alguma linha tem quantidade de campos diferente do cabeçalho."""


@dataclass(frozen=True)
class ResultadoValidacao:
    valido: bool
    motivos: list[str] = field(default_factory=list)


def decodificar(conteudo: bytes) -> str:
    """Decodifica UTF-8 (com ou sem BOM) e, se falhar, Latin-1 (arquivos antigos da ANP)."""
    try:
        return conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        return conteudo.decode("latin-1")


def ler_csv(conteudo: bytes) -> pd.DataFrame:
    """Lê o CSV mantendo todas as colunas como texto. Arquivo vazio vira DataFrame vazio.

    Usa o módulo csv em vez de pd.read_csv porque o pandas, quando uma linha tem mais campos
    que o cabeçalho, transforma os excedentes em índice e desloca as colunas sem avisar.
    Levanta CsvMalFormado se alguma linha tiver quantidade de campos diferente do cabeçalho.
    """
    texto = decodificar(conteudo)
    if not texto.strip():
        return pd.DataFrame()

    leitor = csv.reader(io.StringIO(texto, newline=""), delimiter=";")
    cabecalho = next(leitor)
    linhas = []
    for linha in leitor:
        if not linha:
            continue
        if len(linha) != len(cabecalho):
            raise CsvMalFormado(
                f"linha {leitor.line_num}: esperados {len(cabecalho)} campos, "
                f"encontrados {len(linha)}"
            )
        linhas.append(linha)
    return pd.DataFrame(linhas, columns=cabecalho, dtype=str)


def validar_schema(df: pd.DataFrame) -> ResultadoValidacao:
    if len(df.columns) == 0:
        return ResultadoValidacao(False, ["arquivo vazio"])

    motivos = []
    colunas = list(df.columns)
    ausentes = [c for c in COLUNAS_ESPERADAS if c not in colunas]
    inesperadas = [c for c in colunas if c not in COLUNAS_ESPERADAS]
    if ausentes:
        motivos.append("colunas ausentes: " + ", ".join(ausentes))
    if inesperadas:
        motivos.append("colunas inesperadas: " + ", ".join(inesperadas))
    if not motivos and df.empty:
        motivos.append("arquivo sem linhas de dados")
    return ResultadoValidacao(not motivos, motivos)


def converter_decimal(serie: pd.Series) -> pd.Series:
    """Converte texto com vírgula decimal ('6,89') em float. Inválido ou vazio vira NaN."""
    return pd.to_numeric(serie.str.strip().str.replace(",", ".", regex=False), errors="coerce")


def converter_data(serie: pd.Series) -> pd.Series:
    """Converte 'dd/mm/aaaa' em datetime. Inválido vira NaT."""
    return pd.to_datetime(serie.str.strip(), format=FORMATO_DATA, errors="coerce")


def descrever_invalidas(coluna: str, df: pd.DataFrame, invalidas: pd.Series) -> str:
    posicoes = [i for i, ruim in enumerate(invalidas.to_numpy()) if ruim]
    # Linha no arquivo = posição + 2, porque o cabeçalho é a linha 1.
    exemplos = [f"linha {p + 2} ({df[coluna].iloc[p]!r})" for p in posicoes[:MAX_EXEMPLOS]]
    return f'valor invalido em "{coluna}" ({len(posicoes)} linha(s)): ' + ", ".join(exemplos)


def validar_tipos(df: pd.DataFrame) -> ResultadoValidacao:
    checagens = {
        "Valor de Venda": ~(converter_decimal(df["Valor de Venda"]) > 0),
        "Data da Coleta": converter_data(df["Data da Coleta"]).isna(),
        "Produto": df["Produto"].str.strip() == "",
    }
    motivos = [
        descrever_invalidas(coluna, df, invalidas)
        for coluna, invalidas in checagens.items()
        if invalidas.any()
    ]
    return ResultadoValidacao(not motivos, motivos)


def validar(df: pd.DataFrame) -> ResultadoValidacao:
    """Valida o schema e, só se ele estiver certo, os tipos."""
    resultado = validar_schema(df)
    if not resultado.valido:
        return resultado
    return validar_tipos(df)
