"""Gera o pacote da Lambda (código + dependências) em infra/build/lambda.zip.

Uso (Windows ou CI):
    python scripts/empacotar.py

Não usamos layer: a SCP da organização pode negar lambda:GetLayerVersion, então
pandas/numpy/pyarrow vão dentro do pacote. As wheels são de Linux x86_64 / Python 3.12,
independente do sistema onde o script roda.

O zip é reproduzível (ordem fixa e datas zeradas): o mesmo conteúdo gera o mesmo hash,
então o Terraform só reenvia o pacote quando algo muda de verdade.
"""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_BUILD = RAIZ / "infra" / "build"
PASTA_PACOTE = PASTA_BUILD / "pacote"
ARQUIVO_ZIP = PASTA_BUILD / "lambda.zip"
REQUIREMENTS = RAIZ / "requirements.txt"
CODIGO = RAIZ / "src" / "processador"

# A Lambda aceita até 250 MB descompactado; 245 deixa margem para o próprio código crescer.
LIMITE_DESCOMPACTADO_MB = 245
PASTAS_REMOVIDAS = {"__pycache__", "tests"}
DATA_FIXA = (1980, 1, 1, 0, 0, 0)


def instalar_dependencias() -> None:
    comando = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--requirement",
        str(REQUIREMENTS),
        # numpy >= 2.3 só publica wheels manylinux_2_28; o runtime python3.12 da Lambda
        # (Amazon Linux 2023, glibc 2.34) aceita as duas plataformas.
        "--platform",
        "manylinux2014_x86_64",
        "--platform",
        "manylinux_2_28_x86_64",
        "--only-binary=:all:",
        "--python-version",
        "3.12",
        "--implementation",
        "cp",
        "--target",
        str(PASTA_PACOTE),
        "--no-compile",
        "--quiet",
    ]
    subprocess.run(comando, check=True)


def copiar_codigo() -> None:
    shutil.copytree(CODIGO, PASTA_PACOTE / CODIGO.name)


def remover_desnecessarios() -> None:
    for pasta in sorted(PASTA_PACOTE.rglob("*"), reverse=True):
        if pasta.is_dir() and pasta.name in PASTAS_REMOVIDAS:
            shutil.rmtree(pasta)
    # bin/ tem os executáveis de linha de comando que o pip gera para o sistema local
    # (.exe no Windows): inúteis na Lambda e diferentes a cada execução. O RECORD lista
    # o hash deles e só serve para o pip desinstalar, então também sai.
    shutil.rmtree(PASTA_PACOTE / "bin", ignore_errors=True)
    for record in PASTA_PACOTE.glob("*.dist-info/RECORD"):
        record.unlink()


def gerar_zip() -> None:
    arquivos = sorted(p for p in PASTA_PACOTE.rglob("*") if p.is_file())
    with zipfile.ZipFile(ARQUIVO_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zip_:
        for arquivo in arquivos:
            info = zipfile.ZipInfo(arquivo.relative_to(PASTA_PACOTE).as_posix(), DATA_FIXA)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zip_.writestr(info, arquivo.read_bytes())


def tamanho_mb(caminhos: list[Path]) -> float:
    return sum(p.stat().st_size for p in caminhos) / 1024 / 1024


def relatorio() -> float:
    arquivos = [p for p in PASTA_PACOTE.rglob("*") if p.is_file()]
    descompactado = tamanho_mb(arquivos)
    print(f"Arquivos no pacote: {len(arquivos)}")
    print(
        f"Descompactado: {descompactado:.1f} MB (limite do projeto: {LIMITE_DESCOMPACTADO_MB} MB)"
    )
    print(f"Zipado: {tamanho_mb([ARQUIVO_ZIP]):.1f} MB -> {ARQUIVO_ZIP.relative_to(RAIZ)}")
    print("Maiores pastas de primeiro nivel:")
    pastas = [p for p in PASTA_PACOTE.iterdir() if p.is_dir()]
    tamanhos = {p.name: tamanho_mb([a for a in p.rglob("*") if a.is_file()]) for p in pastas}
    for nome, mb in sorted(tamanhos.items(), key=lambda item: item[1], reverse=True)[:6]:
        print(f"  {nome}: {mb:.1f} MB")
    return descompactado


def main() -> None:
    shutil.rmtree(PASTA_BUILD, ignore_errors=True)
    PASTA_PACOTE.mkdir(parents=True)
    instalar_dependencias()
    copiar_codigo()
    remover_desnecessarios()
    gerar_zip()
    if relatorio() > LIMITE_DESCOMPACTADO_MB:
        sys.exit(f"ERRO: pacote passa de {LIMITE_DESCOMPACTADO_MB} MB descompactado.")


if __name__ == "__main__":
    main()
