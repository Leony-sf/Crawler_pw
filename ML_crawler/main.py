from __future__ import annotations

import argparse
from pathlib import Path
from pprint import pprint

from mercadolivre_crawler.base_anatel import carregar_base_anatel
from mercadolivre_crawler.crawler_playwright_ml import rodar_playwright_mercadolivre
from mercadolivre_crawler.utils import log, secao


def parse_args():
    parser = argparse.ArgumentParser(
        description="Crawler Mercado Livre Playwright com validação ANATEL"
    )

    parser.add_argument(
        "--engine",
        choices=["playwright"],
        default="playwright",
        help="Motor de navegador a usar. Esta versão está focada no Playwright.",
    )

    parser.add_argument(
        "--query",
        default="smartphone",
        help="Termo de busca no Mercado Livre. Usado quando --queries-file não for informado.",
    )

    parser.add_argument(
        "--queries-file",
        default=None,
        help="Arquivo .txt com uma busca por linha. Linhas vazias e iniciadas por # são ignoradas.",
    )

    parser.add_argument(
        "--url",
        default=None,
        help="URL direta de listagem. Se informada, ignora --query.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Quantidade máxima de produtos a analisar. Use 0 para não limitar por produto.",
    )

    parser.add_argument(
        "--base",
        default=None,
        help="Caminho do CSV Produtos_Homologados_Anatel.csv.",
    )

    parser.add_argument(
        "--headless",
        action="store_true",
        help="Roda o navegador sem interface visual.",
    )

    parser.add_argument(
        "--saida",
        default=None,
        help="Pasta de saída. Se omitida, cria uma pasta com data/hora em saidas/.",
    )

    parser.add_argument(
        "--max-paginas",
        type=int,
        default=0,
        help="Máximo de páginas da listagem. Use 0 para rodar até não existir próxima página.",
    )

    parser.add_argument(
        "--mini-celulares",
        action="store_true",
        help="Ativa filtro para mini celulares com limite de tamanho.",
    )

    parser.add_argument(
        "--mini-maior-cm",
        "--mini-maior-eixo-cm",
        dest="mini_maior_cm",
        type=float,
        default=8.5,
        help="Maior dimensão/eixo permitido para mini celular em centímetros. Padrão: 8,5 cm.",
    )

    parser.add_argument(
        "--mini-largura-cm",
        type=float,
        default=5.5,
        help="Largura máxima permitida para mini celular em centímetros. Padrão: 5,5 cm.",
    )

    parser.add_argument(
        "--mini-manter-sem-medida",
        action="store_true",
        help="Mantém na planilha principal anúncios que parecem mini celular, mas não informam medida explícita.",
    )

    return parser.parse_args()


def carregar_queries_txt(caminho: str | None) -> list[str]:
    """Lê um arquivo de buscas: uma query por linha.

    Regras:
    - ignora linhas vazias;
    - ignora linhas iniciadas por #;
    - remove comentários inline depois de #;
    - remove duplicadas mantendo a ordem.
    """
    if not caminho:
        return []

    path = Path(caminho)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de buscas não encontrado: {path}")

    queries: list[str] = []
    vistos: set[str] = set()

    for linha in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        txt = linha.strip()
        if not txt or txt.startswith("#"):
            continue
        if "#" in txt:
            txt = txt.split("#", 1)[0].strip()
        if not txt:
            continue
        chave = txt.lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        queries.append(txt)

    return queries


def main():
    args = parse_args()

    secao("Início do crawler")
    queries_arquivo = carregar_queries_txt(args.queries_file)

    log("main", f"Engine: {args.engine}")
    if queries_arquivo:
        log("main", f"Arquivo de buscas: {args.queries_file}")
        log("main", f"Buscas carregadas: {len(queries_arquivo)}")
        for i, q in enumerate(queries_arquivo[:12], start=1):
            log("main", f"Busca {i}: {q}")
        if len(queries_arquivo) > 12:
            log("main", f"... +{len(queries_arquivo) - 12} buscas")
    else:
        log("main", f"Busca: {args.query}")
    log("main", f"Limite: {'sem limite' if args.limit <= 0 else args.limit}")
    log("main", f"Máximo de páginas: {'sem limite' if args.max_paginas <= 0 else args.max_paginas}")
    log("main", f"Base: {args.base or 'não informada'}")
    if args.mini_celulares:
        log("main", "Modo mini celulares: ativado")
        log("main", f"Limites mini: maior eixo <= {args.mini_maior_cm} cm | largura <= {args.mini_largura_cm} cm")

    secao("Base ANATEL")
    base = carregar_base_anatel(args.base, prefix_len=5)

    resumo = rodar_playwright_mercadolivre(
        query=args.query,
        queries=queries_arquivo or None,
        limite=args.limit,
        base_anatel=base,
        headless=args.headless,
        url=args.url,
        saida=args.saida,
        max_paginas=args.max_paginas,
        mini_celulares=args.mini_celulares,
        mini_maior_cm=args.mini_maior_cm,
        mini_largura_cm=args.mini_largura_cm,
        mini_manter_sem_medida=args.mini_manter_sem_medida,
    )

    secao("Resumo final")
    pprint(resumo)


if __name__ == "__main__":
    main()
