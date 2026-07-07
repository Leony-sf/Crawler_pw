from __future__ import annotations

import argparse

from crawler_playwright_aliexpress import executar_sync
from utils_aliexpress import ler_buscas


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crawler AliExpress para captura de mini celulares/celulares pequenos com Playwright."
    )
    parser.add_argument(
        "--txt",
        default="buscar_aliexpress.txt",
        help="Arquivo .txt com uma busca por linha. Padrão: buscar_aliexpress.txt",
    )
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="Busca adicional via terminal. Pode repetir: --query 'mini celular' --query 'bluetooth dialer'",
    )
    parser.add_argument("--limit", type=int, default=50, help="Quantidade máxima de produtos visitados.")
    parser.add_argument("--max-paginas", type=int, default=1, help="Quantidade máxima de páginas por busca.")
    parser.add_argument("--saida", default="saidas_aliexpress", help="Pasta de saída.")
    parser.add_argument("--headless", action="store_true", help="Rodar sem abrir janela do navegador.")
    parser.add_argument(
        "--sem-pausa-login",
        action="store_true",
        help="Não pausar para login/captcha/cookies antes de iniciar.",
    )
    parser.add_argument(
        "--perfil",
        default="perfil_aliexpress",
        help="Pasta de perfil persistente do navegador. Ajuda a manter cookies/login.",
    )
    parser.add_argument(
        "--manter-brinquedos",
        action="store_true",
        help="Mantém brinquedos/miniaturas na análise quando aparecerem nas buscas.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    queries = ler_buscas(args.txt, args.query)

    if not queries:
        queries = [
            "mini celular dual sim",
            "mini phone sim card",
            "bluetooth dialer mini phone",
            "small mobile phone gsm",
            "card phone dual sim",
        ]
        print("[busca] Nenhum TXT/query encontrado. Usando buscas padrão de mini celulares.")

    executar_sync(
        queries=queries,
        saida=args.saida,
        limit=args.limit,
        max_paginas=args.max_paginas,
        headless=args.headless,
        pausa_login=not args.sem_pausa_login,
        user_data_dir=args.perfil,
        manter_brinquedos=args.manter_brinquedos,
    )


if __name__ == "__main__":
    main()
