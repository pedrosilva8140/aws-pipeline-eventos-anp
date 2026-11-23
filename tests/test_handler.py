import io
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from processador import handler

FIXTURES = Path(__file__).parent / "fixtures"
BUCKET = "bucket-teste"
TOPICO = "arn:aws:sns:us-east-1:000000000000:alertas-teste"


class S3Falso:
    """Imita só as chamadas do cliente S3 que o handler usa, guardando tudo em memória."""

    def __init__(self) -> None:
        self.objetos: dict[tuple[str, str], bytes] = {}
        self.escritas: list[str] = []
        self.leituras: list[str] = []

    def get_object(self, Bucket: str, Key: str) -> dict:
        self.leituras.append(Key)
        return {"Body": io.BytesIO(self.objetos[(Bucket, Key)])}

    def put_object(self, Bucket: str, Key: str, Body: bytes, **_: object) -> dict:
        self.escritas.append(Key)
        self.objetos[(Bucket, Key)] = Body
        return {}

    def copy_object(self, Bucket: str, Key: str, CopySource: dict) -> dict:
        self.escritas.append(Key)
        self.objetos[(Bucket, Key)] = self.objetos[(CopySource["Bucket"], CopySource["Key"])]
        return {}

    def delete_object(self, Bucket: str, Key: str) -> dict:
        self.objetos.pop((Bucket, Key), None)
        return {}

    def chaves(self) -> list[str]:
        return sorted(chave for _, chave in self.objetos)


class SNSFalso:
    def __init__(self) -> None:
        self.publicacoes: list[dict] = []

    def publish(self, **kwargs: object) -> dict:
        self.publicacoes.append(kwargs)
        return {"MessageId": "1"}


def evento(*chaves: str) -> dict:
    return {
        "Records": [
            {"s3": {"bucket": {"name": BUCKET}, "object": {"key": chave}}} for chave in chaves
        ]
    }


@pytest.fixture
def s3() -> S3Falso:
    return S3Falso()


@pytest.fixture
def sns() -> SNSFalso:
    return SNSFalso()


def colocar(s3: S3Falso, chave: str, fixture: str) -> bytes:
    conteudo = (FIXTURES / fixture).read_bytes()
    s3.objetos[(BUCKET, chave)] = conteudo
    return conteudo


def processar(s3: S3Falso, sns: SNSFalso, *chaves: str) -> list[dict]:
    return handler.processar_evento(evento(*chaves), s3, sns, TOPICO)


def test_arquivo_valido_vira_parquet_particionado(s3: S3Falso, sns: SNSFalso):
    colocar(s3, "entrada/precos-2026-10.csv", "anp_valido.csv")

    [resultado] = processar(s3, sns, "entrada/precos-2026-10.csv")

    saida = "processado/ano=2026/mes=10/precos-2026-10.parquet"
    assert resultado == {
        "arquivo": "entrada/precos-2026-10.csv",
        "status": "processado",
        "linhas": 19,
        "saidas": [saida],
    }
    tabela = pq.read_table(io.BytesIO(s3.objetos[(BUCKET, saida)]))
    assert tabela.num_rows == 19
    assert (BUCKET, "entrada/precos-2026-10.csv") in s3.objetos
    assert sns.publicacoes == []


def test_reprocessar_sobrescreve_e_nao_duplica(s3: S3Falso, sns: SNSFalso):
    colocar(s3, "entrada/precos-2026-10.csv", "anp_valido.csv")

    processar(s3, sns, "entrada/precos-2026-10.csv")
    chaves_primeira_vez = s3.chaves()
    processar(s3, sns, "entrada/precos-2026-10.csv")

    assert s3.chaves() == chaves_primeira_vez


@pytest.mark.parametrize(
    ("fixture", "trecho_do_motivo"),
    [
        ("anp_schema_invalido.csv", "Bandeira"),
        ("anp_tipos_invalidos.csv", "Valor de Venda"),
        ("anp_so_cabecalho.csv", "sem linhas de dados"),
        ("anp_vazio.csv", "arquivo vazio"),
    ],
)
def test_arquivo_invalido_vai_para_rejeitado(
    s3: S3Falso, sns: SNSFalso, fixture: str, trecho_do_motivo: str
):
    original = colocar(s3, "entrada/ruim.csv", fixture)

    [resultado] = processar(s3, sns, "entrada/ruim.csv")

    assert resultado["status"] == "rejeitado"
    assert (BUCKET, "entrada/ruim.csv") not in s3.objetos
    assert s3.objetos[(BUCKET, "rejeitado/ruim.csv")] == original

    relatorio = json.loads(s3.objetos[(BUCKET, "rejeitado/ruim.json")])
    assert relatorio["arquivo_original"] == "entrada/ruim.csv"
    assert relatorio["arquivo_rejeitado"] == "rejeitado/ruim.csv"
    assert trecho_do_motivo in " | ".join(relatorio["motivos"])

    [publicacao] = sns.publicacoes
    assert publicacao["TopicArn"] == TOPICO
    assert publicacao["Subject"] == "Arquivo rejeitado: ruim.csv"
    assert json.loads(publicacao["Message"]) == relatorio
    assert not any(chave.startswith("processado/") for chave in s3.chaves())


def test_csv_mal_formado_vai_para_rejeitado(s3: S3Falso, sns: SNSFalso):
    s3.objetos[(BUCKET, "entrada/torto.csv")] = b"a;b\r\n1;2;3;4\r\n"

    [resultado] = processar(s3, sns, "entrada/torto.csv")

    assert resultado["status"] == "rejeitado"
    assert "CSV mal formado" in resultado["motivos"][0]
    assert len(sns.publicacoes) == 1


def test_assunto_do_sns_respeita_limite_de_100_caracteres(s3: S3Falso, sns: SNSFalso):
    chave = "entrada/" + "x" * 150 + ".csv"
    colocar(s3, chave, "anp_vazio.csv")

    processar(s3, sns, chave)

    assert len(sns.publicacoes[0]["Subject"]) <= 100


def test_chave_codificada_na_url_e_decodificada(s3: S3Falso, sns: SNSFalso):
    colocar(s3, "entrada/meu arquivo (1).csv", "anp_valido.csv")

    [resultado] = processar(s3, sns, "entrada/meu+arquivo+%281%29.csv")

    assert resultado["status"] == "processado"
    assert resultado["saidas"] == ["processado/ano=2026/mes=10/meu arquivo (1).parquet"]


@pytest.mark.parametrize("chave", ["processado/x.csv", "entrada/x.txt", "rejeitado/x.csv"])
def test_arquivo_fora_de_entrada_ou_nao_csv_e_ignorado(s3: S3Falso, sns: SNSFalso, chave: str):
    [resultado] = processar(s3, sns, chave)

    assert resultado == {"arquivo": chave, "status": "ignorado"}
    assert s3.leituras == []
    assert s3.escritas == []


def test_nunca_grava_em_entrada(s3: S3Falso, sns: SNSFalso):
    colocar(s3, "entrada/bom.csv", "anp_valido.csv")
    colocar(s3, "entrada/ruim.csv", "anp_schema_invalido.csv")

    resultados = processar(s3, sns, "entrada/bom.csv", "entrada/ruim.csv")

    assert [r["status"] for r in resultados] == ["processado", "rejeitado"]
    assert s3.escritas
    assert not any(chave.startswith("entrada/") for chave in s3.escritas)


def test_erro_de_infra_propaga_excecao(s3: S3Falso, sns: SNSFalso):
    with pytest.raises(KeyError):
        processar(s3, sns, "entrada/nao-existe.csv")


def test_lambda_handler_usa_clientes_e_topico_do_ambiente(
    s3: S3Falso, sns: SNSFalso, monkeypatch: pytest.MonkeyPatch
):
    colocar(s3, "entrada/ruim.csv", "anp_vazio.csv")
    monkeypatch.setenv("TOPICO_ALERTAS_ARN", TOPICO)
    monkeypatch.setattr(handler, "criar_clientes", lambda: (s3, sns))

    resposta = handler.lambda_handler(evento("entrada/ruim.csv"), None)

    assert resposta["resultados"][0]["status"] == "rejeitado"
    assert sns.publicacoes[0]["TopicArn"] == TOPICO
