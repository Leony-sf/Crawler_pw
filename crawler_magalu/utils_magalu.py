# -*- coding: utf-8 -*-
"""Funções utilitárias do crawler Magalu."""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable, List
from urllib.parse import quote_plus, urljoin, urlsplit, urlunsplit


BASE_URL_MAGALU = "https://www.magazineluiza.com.br"


def agora_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def slugify(texto: str, max_len: int = 90) -> str:
    texto = (texto or "").strip().lower()
    texto = re.sub(r"https?://", "", texto)
    texto = re.sub(r"[^a-z0-9áéíóúâêôãõç]+", "-", texto, flags=re.IGNORECASE)
    texto = re.sub(r"-+", "-", texto).strip("-")
    if not texto:
        texto = "produto"
    return texto[:max_len].strip("-") or "produto"


def limpar_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    if url.startswith("/"):
        url = urljoin(BASE_URL_MAGALU, url)
    partes = urlsplit(url)
    return urlunsplit((partes.scheme or "https", partes.netloc, partes.path, "", ""))


def montar_url_busca(termo: str, pagina: int = 1) -> str:
    termo_q = quote_plus(termo.strip())
    # O Magalu aceita buscas nesse formato: /busca/<termo>/.
    # O parâmetro page é mantido para paginação quando a plataforma retornar mais de uma página.
    return f"{BASE_URL_MAGALU}/busca/{termo_q}/?page={pagina}"


def resolver_arquivo_txt(caminho_txt: str) -> Path:
    entrada = Path(caminho_txt)
    candidatos = []

    if entrada.is_absolute():
        candidatos.append(entrada)
    else:
        cwd = Path.cwd()
        pasta_script = Path(__file__).resolve().parent
        candidatos.extend([cwd / entrada, pasta_script / entrada])

    aliases = ["buscar_magalu.txt", "buscas_magalu.txt"]
    cwd = Path.cwd()
    pasta_script = Path(__file__).resolve().parent
    for nome in aliases:
        candidatos.extend([cwd / nome, pasta_script / nome])

    vistos = []
    for candidato in candidatos:
        candidato = candidato.resolve()
        if candidato in vistos:
            continue
        vistos.append(candidato)
        if candidato.exists() and candidato.is_file():
            return candidato

    lista = "\n".join(f"- {p}" for p in vistos)
    raise FileNotFoundError("Arquivo TXT de buscas não encontrado. Caminhos verificados:\n" + lista)


def carregar_termos_busca(caminho_txt: str) -> List[str]:
    path = resolver_arquivo_txt(caminho_txt)
    termos: List[str] = []
    for linha in path.read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        termos.append(linha)
    if not termos:
        raise ValueError(f"O arquivo {path} não possui termos de busca válidos.")
    return termos


def preparar_saida(saida: Path, limpar_prints: bool = False) -> None:
    """Mantém a saída limpa: parquet + resumo + prints, sem CSV/JSON/comentários."""
    saida.mkdir(parents=True, exist_ok=True)

    if limpar_prints:
        prints = saida / "prints"
        if prints.exists():
            shutil.rmtree(prints, ignore_errors=True)

    (saida / "prints" / "irregulares" / "menor_80mm").mkdir(parents=True, exist_ok=True)
    (saida / "prints" / "suspeitos").mkdir(parents=True, exist_ok=True)
    (saida / "suspeitos").mkdir(parents=True, exist_ok=True)

    arquivos_antigos = [
        "products.csv", "comments.csv", "comments.parquet", "resumo.csv", "resumo.json",
        "suspeitos_sem_medidas.parquet",
    ]
    for nome in arquivos_antigos:
        alvo = saida / nome
        if alvo.exists():
            alvo.unlink()

    pastas_antigas = [
        saida / "json",
        saida / "prints" / "descartados",
        saida / "prints" / "irregulares" / "mini_celulares",
        saida / "prints" / "irregulares" / "tela_ate_5_polegadas",
        saida / "prints" / "irregulares" / "tela_ate_3_polegadas",
        saida / "prints" / "irregulares" / "sem_medidas",
        saida / "prints" / "irregulares" / "revisar_medidas",
        saida / "prints" / "irregulares" / "sem_anatel",
        saida / "suspeitos_sem_medidas",
        saida / "suspeitos_tela_proxima_3",
        saida / "suspeitos_sem_tela",
        saida / "prints" / "suspeitos" / "tela_proxima_3_polegadas",
        saida / "prints" / "suspeitos" / "sem_tela",
    ]
    for pasta in pastas_antigas:
        if pasta.exists():
            shutil.rmtree(pasta, ignore_errors=True)


def escrever_resumo_txt(saida: Path, linhas: Iterable[str]) -> Path:
    path = saida / "resumo.txt"
    conteudo = "\n".join(str(linha) for linha in linhas)
    path.write_text(conteudo, encoding="utf-8")
    return path
