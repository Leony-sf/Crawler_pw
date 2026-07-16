# -*- coding: utf-8 -*-
"""Utilitários do crawler Casas Bahia."""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, quote_plus


def agora_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def slugify(texto: str, max_len: int = 80) -> str:
    texto = str(texto or "").lower()
    texto = re.sub(r"https?://", "", texto)
    texto = re.sub(r"[^a-z0-9áéíóúàâêôãõç]+", "-", texto, flags=re.IGNORECASE)
    texto = texto.strip("-")
    texto = re.sub(r"-+", "-", texto)
    return texto[:max_len].strip("-") or "item"


def carregar_termos_busca(caminho_txt: str) -> list[str]:
    caminho = Path(caminho_txt)
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo TXT não encontrado: {caminho.resolve()}")

    termos: list[str] = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        termos.append(linha)

    if not termos:
        raise ValueError(f"Nenhum termo de busca encontrado em: {caminho.resolve()}")

    return termos


def montar_urls_busca(termo: str, pagina: int = 1) -> list[str]:
    """
    Fluxo limpo: apenas abre URLs de busca.
    Não usa barra de busca, autocomplete, topterms ou cliques.

    Mantemos alguns formatos porque o site pode aceitar um e recusar outro.
    O crawler testa em ordem e usa o primeiro que retornar links.
    """
    termo_limpo = re.sub(r"\s+", " ", termo.strip())
    termo_plus = quote_plus(termo_limpo)
    termo_slug = quote(re.sub(r"\s+", "-", termo_limpo.lower()), safe="-")

    urls = [
        f"https://www.casasbahia.com.br/busca?termo={termo_plus}",
        f"https://www.casasbahia.com.br/busca/{termo_slug}",
        f"https://www.casasbahia.com.br/s?termo={termo_plus}",
        f"https://www.casasbahia.com.br/search?term={termo_plus}",
    ]

    if pagina > 1:
        urls = [
            url + ("&" if "?" in url else "?") + f"page={pagina}"
            for url in urls
        ]

    return urls


def montar_url_busca(termo: str, pagina: int = 1, modo: str = "busca") -> str:
    """
    Compatibilidade com versões antigas.
    """
    urls = montar_urls_busca(termo, pagina=pagina)
    mapa = {
        "busca": 0,
        "slug": 1,
        "query": 0,
        "search": 3,
        "s": 2,
    }
    return urls[mapa.get(modo, 0)]


def preparar_saida(saida: Path, limpar_prints: bool = False) -> None:
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "prints" / "irregulares" / "menor_80mm").mkdir(parents=True, exist_ok=True)
    (saida / "prints" / "suspeitos").mkdir(parents=True, exist_ok=True)
    (saida / "suspeitos").mkdir(parents=True, exist_ok=True)

    # Remove estruturas antigas que não fazem parte do padrão atual.
    pastas_antigas = [
        saida / "prints" / "descartados",
        saida / "prints" / "debug_busca_sem_links",
        saida / "prints" / "irregulares" / "tela_ate_3_polegadas",
        saida / "prints" / "irregulares" / "sem_medidas",
        saida / "suspeitos_tela_proxima_3",
        saida / "suspeitos_sem_tela",
    ]

    for pasta in pastas_antigas:
        if pasta.exists():
            shutil.rmtree(pasta, ignore_errors=True)

    # Sem CSV e sem JSON nos resultados.
    for padrao in ["*.csv", "*.json"]:
        for arquivo in saida.glob(padrao):
            try:
                arquivo.unlink()
            except Exception:
                pass

    if limpar_prints:
        prints = saida / "prints"
        if prints.exists():
            shutil.rmtree(prints, ignore_errors=True)
        (saida / "prints" / "irregulares" / "menor_80mm").mkdir(parents=True, exist_ok=True)
        (saida / "prints" / "suspeitos").mkdir(parents=True, exist_ok=True)


def escrever_resumo_txt(saida: Path, linhas: list[str]) -> None:
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "resumo.txt").write_text("\n".join(linhas), encoding="utf-8")
