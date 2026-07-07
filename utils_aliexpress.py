from __future__ import annotations

import asyncio
import hashlib
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd


def slugify(texto: str, limite: int = 90) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = texto.lower().strip()
    texto = re.sub(r"[^a-z0-9]+", "_", texto)
    texto = re.sub(r"_+", "_", texto).strip("_")
    return (texto[:limite] or "produto")


def hash_curto(texto: str, tamanho: int = 8) -> str:
    return hashlib.sha1(str(texto or "").encode("utf-8", errors="ignore")).hexdigest()[:tamanho]


def garantir_pastas(base: Path) -> None:
    """Cria somente as pastas realmente usadas pelo crawler.

    Saída atual:
    - products.parquet
    - resumo.txt
    - prints/irregulares/...

    Esta versão não cria JSON, CSV, comentários nem pasta de descartados.
    """
    pastas = [
        base,
        base / "prints",
        base / "prints" / "irregulares" / "mini_celulares",
        base / "prints" / "irregulares" / "sem_medidas",
        base / "prints" / "irregulares" / "revisar_medidas",
    ]
    for pasta in pastas:
        pasta.mkdir(parents=True, exist_ok=True)


def limpar_saidas_legadas(base: Path) -> None:
    """Remove arquivos/pastas antigos que não fazem mais parte da saída.

    Isso limpa execuções anteriores da versão que gerava CSV, JSON,
    comentários e prints/descartados.
    """
    if not base.exists():
        return

    # Remove todos os CSV existentes dentro da pasta de saída.
    for csv_file in base.rglob("*.csv"):
        try:
            csv_file.unlink()
        except Exception:
            pass

    arquivos_antigos = [
        base / "comments.parquet",
        base / "comments.csv",
        base / "resumo.csv",
        base / "resumo.json",
    ]
    for arquivo in arquivos_antigos:
        if arquivo.exists() and arquivo.is_file():
            try:
                arquivo.unlink()
            except Exception:
                pass

    pastas_antigas = [
        base / "json",
        base / "prints" / "descartados",
    ]
    for pasta in pastas_antigas:
        if pasta.exists() and pasta.is_dir():
            try:
                shutil.rmtree(pasta)
            except Exception:
                pass


# Compatibilidade com versões anteriores que importavam este nome.
def limpar_json_legado(base: Path) -> None:
    limpar_saidas_legadas(base)


def _candidatos_txt(caminho_txt: str | None) -> List[Path]:
    """Monta caminhos possíveis para o TXT.

    Resolve o problema mais comum no VS Code/terminal: o comando é executado
    de outra pasta e o arquivo existe ao lado do main_aliexpress.py.
    """
    script_dir = Path(__file__).resolve().parent
    cwd = Path.cwd()

    nomes_padrao = ["buscar_aliexpress.txt", "buscas_aliexpress.txt"]
    nomes: List[str] = []

    if caminho_txt:
        nomes.append(str(caminho_txt))
    nomes.extend(n for n in nomes_padrao if n not in nomes)

    candidatos: List[Path] = []
    for nome in nomes:
        p = Path(nome).expanduser()
        if p.is_absolute():
            candidatos.append(p)
        else:
            candidatos.extend([
                cwd / p,
                script_dir / p,
                script_dir.parent / p,
            ])

    # Remove duplicados preservando ordem.
    saida: List[Path] = []
    vistos = set()
    for p in candidatos:
        chave = str(p.resolve()) if p.exists() else str(p)
        if chave not in vistos:
            vistos.add(chave)
            saida.append(p)
    return saida


def ler_buscas(caminho_txt: str | None, queries_cli: Iterable[str] | None = None) -> List[str]:
    buscas: List[str] = []
    arquivo_usado: Path | None = None

    for candidato in _candidatos_txt(caminho_txt):
        if candidato.exists() and candidato.is_file():
            arquivo_usado = candidato
            for linha in candidato.read_text(encoding="utf-8").splitlines():
                linha = linha.strip()
                if linha and not linha.startswith("#"):
                    buscas.append(linha)
            break

    if arquivo_usado:
        print(f"[busca] TXT usado: {arquivo_usado}")
    elif caminho_txt:
        print(f"[busca] TXT não encontrado: {caminho_txt}")
        print("[busca] Também tentei: buscar_aliexpress.txt e buscas_aliexpress.txt ao lado do main_aliexpress.py")

    if queries_cli:
        for q in queries_cli:
            q = str(q).strip()
            if q:
                buscas.append(q)

    # Remove duplicadas preservando ordem.
    saida: List[str] = []
    vistos = set()
    for q in buscas:
        chave = q.lower()
        if chave not in vistos:
            vistos.add(chave)
            saida.append(q)
    return saida


async def espera_curta(segundos: float = 0.8) -> None:
    await asyncio.sleep(segundos)


async def rolar_pagina(page, passos: int = 5, pausa: float = 0.6) -> None:
    for _ in range(passos):
        await page.mouse.wheel(0, 900)
        await asyncio.sleep(pausa)


def salvar_tabelas(base: Path, produtos: List[Dict[str, Any]]) -> None:
    """Salva apenas products.parquet.

    Não gera CSV e não gera arquivo de comentários.
    """
    base.mkdir(parents=True, exist_ok=True)
    df_produtos = pd.DataFrame(produtos)

    try:
        df_produtos.to_parquet(base / "products.parquet", index=False)
    except Exception as exc:
        print(f"[saida] Não foi possível salvar products.parquet: {exc}")


def salvar_resumo(base: Path, resumo: Dict[str, Any]) -> None:
    """Salva o resumo somente em TXT."""
    base.mkdir(parents=True, exist_ok=True)
    linhas = [f"{chave}: {valor}" for chave, valor in resumo.items()]
    (base / "resumo.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")
