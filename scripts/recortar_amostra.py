"""Gera as fixtures de teste a partir de uma amostra real da ANP.

Uso:
    python scripts/recortar_amostra.py dados/amostras/precos-gasolina-etanol-2026-10.csv

Seleciona poucas linhas de forma determinística (sempre as mesmas para a mesma amostra)
e grava os arquivos em tests/fixtures/.
"""

import csv
import io
import sys
from pathlib import Path

PASTA_FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
LINHAS_POR_PRODUTO = 5
LINHAS_COM_PONTO_E_VIRGULA = 3
LINHAS_COM_ACENTO = 3


def ler_amostra(caminho: Path) -> tuple[list[str], list[list[str]]]:
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.reader(arquivo, delimiter=";")
        cabecalho = next(leitor)
        return cabecalho, list(leitor)


def selecionar_linhas(cabecalho: list[str], linhas: list[list[str]]) -> list[list[str]]:
    idx_produto = cabecalho.index("Produto")
    escolhidas: set[int] = set()

    por_produto: dict[str, int] = {}
    for i, linha in enumerate(linhas):
        produto = linha[idx_produto]
        if por_produto.get(produto, 0) < LINHAS_POR_PRODUTO:
            por_produto[produto] = por_produto.get(produto, 0) + 1
            escolhidas.add(i)

    com_ponto_e_virgula = [i for i, linha in enumerate(linhas) if any(";" in c for c in linha)]
    escolhidas.update(com_ponto_e_virgula[:LINHAS_COM_PONTO_E_VIRGULA])

    com_acento = [
        i for i, linha in enumerate(linhas) if any(ord(ch) > 127 for c in linha for ch in c)
    ]
    escolhidas.update(com_acento[:LINHAS_COM_ACENTO])

    return [linhas[i] for i in sorted(escolhidas)]


def para_csv(cabecalho: list[str], linhas: list[list[str]]) -> str:
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(cabecalho)
    escritor.writerows(linhas)
    return saida.getvalue()


def gravar(nome: str, conteudo: bytes) -> None:
    caminho = PASTA_FIXTURES / nome
    caminho.write_bytes(conteudo)
    print(f"{caminho.relative_to(PASTA_FIXTURES.parent.parent)}: {len(conteudo)} bytes")


def main(caminho_amostra: str) -> None:
    cabecalho, linhas = ler_amostra(Path(caminho_amostra))
    selecionadas = selecionar_linhas(cabecalho, linhas)
    texto_valido = para_csv(cabecalho, selecionadas)

    gravar("anp_valido.csv", texto_valido.encode("utf-8-sig"))
    gravar("anp_valido_latin1.csv", texto_valido.encode("latin-1"))

    idx_bandeira = cabecalho.index("Bandeira")
    sem_bandeira = [[c for j, c in enumerate(linha) if j != idx_bandeira] for linha in selecionadas]
    cabecalho_sem_bandeira = [c for c in cabecalho if c != "Bandeira"]
    gravar(
        "anp_schema_invalido.csv",
        para_csv(cabecalho_sem_bandeira, sem_bandeira).encode("utf-8-sig"),
    )

    invalidas = [list(linha) for linha in selecionadas[:5]]
    invalidas[0][cabecalho.index("Valor de Venda")] = "abc"
    invalidas[1][cabecalho.index("Data da Coleta")] = "31/02/2026"
    invalidas[2][cabecalho.index("Produto")] = ""
    gravar("anp_tipos_invalidos.csv", para_csv(cabecalho, invalidas).encode("utf-8-sig"))

    gravar("anp_so_cabecalho.csv", para_csv(cabecalho, []).encode("utf-8-sig"))
    gravar("anp_vazio.csv", b"")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Uso: python scripts/recortar_amostra.py <caminho_da_amostra.csv>")
    main(sys.argv[1])
