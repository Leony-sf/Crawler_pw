from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compara Parquets gerados por Playwright"
    )

    parser.add_argument(
        "--playwright",
        required=True,
        help="Arquivo resultados.parquet gerado pelo crawler Playwright",
    )

    parser.add_argument(
        "--selenium",
        required=True,
        help="Arquivo resultados.parquet gerado pelo crawler Selenium",
    )

    parser.add_argument(
        "--saida",
        default="comparativo_playwright_selenium.parquet",
        help="Arquivo Parquet de saída",
    )

    return parser.parse_args()


def ler_parquet(path: str) -> pd.DataFrame:
    return pd.read_parquet(path).fillna("")


def main():
    args = parse_args()

    df_pw = ler_parquet(args.playwright)
    df_se = ler_parquet(args.selenium)

    colunas_base = [
        "url",
        "titulo",
        "codigo_anatel_principal",
        "marca",
        "modelo",
        "versao",
        "fabricante",
        "status_validacao",
        "motivo_validacao",
    ]

    for col in colunas_base:
        if col not in df_pw.columns:
            df_pw[col] = ""

        if col not in df_se.columns:
            df_se[col] = ""

    pw = df_pw[colunas_base].add_suffix("_playwright")
    se = df_se[colunas_base].add_suffix("_selenium")

    comparado = pd.merge(
        pw,
        se,
        left_on="url_playwright",
        right_on="url_selenium",
        how="outer",
    )

    comparado["mesmo_codigo"] = (
        comparado["codigo_anatel_principal_playwright"].fillna("")
        == comparado["codigo_anatel_principal_selenium"].fillna("")
    )

    comparado["mesmo_status"] = (
        comparado["status_validacao_playwright"].fillna("")
        == comparado["status_validacao_selenium"].fillna("")
    )

    saida = Path(args.saida)
    comparado.to_parquet(saida, index=False)

    print("Comparação gerada:", saida.resolve())
    print("Total Playwright:", len(df_pw))
    print("Total Selenium:", len(df_se))
    print("Linhas comparadas:", len(comparado))
    print("Mesmo código:", int(comparado["mesmo_codigo"].sum()))
    print("Mesmo status:", int(comparado["mesmo_status"].sum()))


if __name__ == "__main__":
    main()