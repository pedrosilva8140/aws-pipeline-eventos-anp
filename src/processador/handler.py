"""Lambda acionada pelo S3: valida o CSV da ANP e grava Parquet em processado/.

Só orquestra: lê o evento, acessa S3/SNS e chama as funções puras.
- Falha de dados: move o arquivo para rejeitado/, grava o JSON com os motivos e avisa no SNS.
  Não lança exceção.
- Falha de infra (S3/SNS): a exceção sobe para a Lambda tentar de novo e, depois, ir para a DLQ.
- Nunca grava em entrada/ (evita loop de eventos).
"""

import json
import logging
import os
from datetime import UTC, datetime
from functools import cache
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote_plus

from processador.transformacao import chave_saida, dividir_por_mes, para_parquet, transformar
from processador.validacao import CsvMalFormado, ler_csv, validar

PREFIXO_ENTRADA = "entrada/"
PREFIXO_REJEITADO = "rejeitado/"
LIMITE_ASSUNTO_SNS = 100

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@cache
def criar_clientes() -> tuple[Any, Any]:
    import boto3

    return boto3.client("s3"), boto3.client("sns")


def lambda_handler(event: dict, context: object) -> dict:
    s3, sns = criar_clientes()
    resultados = processar_evento(event, s3, sns, os.environ["TOPICO_ALERTAS_ARN"])
    return {"resultados": resultados}


def processar_evento(evento: dict, s3: Any, sns: Any, topico_arn: str) -> list[dict]:
    resultados = []
    for registro in evento["Records"]:
        bucket = registro["s3"]["bucket"]["name"]
        chave = unquote_plus(registro["s3"]["object"]["key"])
        resultado = processar_arquivo(bucket, chave, s3, sns, topico_arn)
        logger.info(json.dumps(resultado, ensure_ascii=False))
        resultados.append(resultado)
    return resultados


def processar_arquivo(bucket: str, chave: str, s3: Any, sns: Any, topico_arn: str) -> dict:
    if not chave.startswith(PREFIXO_ENTRADA) or not chave.lower().endswith(".csv"):
        return {"arquivo": chave, "status": "ignorado"}

    conteudo = s3.get_object(Bucket=bucket, Key=chave)["Body"].read()

    try:
        df = ler_csv(conteudo)
    except CsvMalFormado as erro:
        motivos = [f"CSV mal formado: {erro}"]
        return rejeitar(bucket, chave, motivos, s3, sns, topico_arn)

    resultado = validar(df)
    if not resultado.valido:
        return rejeitar(bucket, chave, resultado.motivos, s3, sns, topico_arn)

    df_final = transformar(df)
    saidas = []
    for (ano, mes), parte in dividir_por_mes(df_final).items():
        destino = chave_saida(chave, ano, mes)
        s3.put_object(Bucket=bucket, Key=destino, Body=para_parquet(parte))
        saidas.append(destino)
    return {"arquivo": chave, "status": "processado", "linhas": len(df_final), "saidas": saidas}


def rejeitar(
    bucket: str, chave: str, motivos: list[str], s3: Any, sns: Any, topico_arn: str
) -> dict:
    nome = PurePosixPath(chave)
    destino = f"{PREFIXO_REJEITADO}{nome.name}"
    relatorio = {
        "arquivo_original": chave,
        "arquivo_rejeitado": destino,
        "motivos": motivos,
        "data_rejeicao": datetime.now(UTC).isoformat(),
    }
    corpo = json.dumps(relatorio, ensure_ascii=False, indent=2)

    s3.copy_object(Bucket=bucket, Key=destino, CopySource={"Bucket": bucket, "Key": chave})
    s3.delete_object(Bucket=bucket, Key=chave)
    s3.put_object(
        Bucket=bucket,
        Key=f"{PREFIXO_REJEITADO}{nome.stem}.json",
        Body=corpo.encode("utf-8"),
        ContentType="application/json",
    )
    sns.publish(
        TopicArn=topico_arn,
        Subject=f"Arquivo rejeitado: {nome.name}"[:LIMITE_ASSUNTO_SNS],
        Message=corpo,
    )
    return {"arquivo": chave, "status": "rejeitado", "motivos": motivos}
