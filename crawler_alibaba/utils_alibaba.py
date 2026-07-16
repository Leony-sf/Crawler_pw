# -*- coding: utf-8 -*-
"""Funções utilitárias do crawler Alibaba.com."""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable, List
from urllib.parse import quote_plus, urljoin, urlsplit, urlunsplit


BASE_URL_ALIBABA = "https://www.alibaba.com"


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
    """Remove parâmetros longos de rastreamento e padroniza links relativos."""
    if not url:
        return ""
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    if url.startswith("/"):
        url = urljoin(BASE_URL_ALIBABA, url)
    partes = urlsplit(url)
    # Mantém apenas URL limpa, sem query/fragment.
    return urlunsplit((partes.scheme or "https", partes.netloc, partes.path, "", ""))


def montar_url_busca(termo: str, pagina: int = 1) -> str:
    termo_q = quote_plus(termo)
    return f"{BASE_URL_ALIBABA}/trade/search?fsb=y&IndexArea=product_en&SearchText={termo_q}&page={pagina}"


def resolver_arquivo_txt(caminho_txt: str) -> Path:
    """
    Resolve o .txt mesmo quando o terminal está em outra pasta.
    Procura na pasta atual e na pasta do próprio script.
    Aceita alias buscar_alibaba.txt / buscas_alibaba.txt.
    """
    entrada = Path(caminho_txt)
    candidatos = []

    if entrada.is_absolute():
        candidatos.append(entrada)
    else:
        cwd = Path.cwd()
        pasta_script = Path(__file__).resolve().parent
        candidatos.extend([
            cwd / entrada,
            pasta_script / entrada,
        ])

    aliases = ["buscar_alibaba.txt", "buscas_alibaba.txt"]
    cwd = Path.cwd()
    pasta_script = Path(__file__).resolve().parent
    for nome in aliases:
        candidatos.extend([cwd / nome, pasta_script / nome])

    vistos = set()
    for candidato in candidatos:
        candidato = candidato.resolve()
        if candidato in vistos:
            continue
        vistos.add(candidato)
        if candidato.exists() and candidato.is_file():
            return candidato

    lista = "\n".join(f"- {p}" for p in vistos)
    raise FileNotFoundError(
        "Arquivo TXT de buscas não encontrado. Caminhos verificados:\n" + lista
    )


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
    """
    Mantém a saída limpa:
    - não gera CSV;
    - não gera JSON;
    - remove vestígios antigos de comments/json/descartados;
    - nesta versão, a classificação principal é por tela <= 3 polegadas.
    """
    saida.mkdir(parents=True, exist_ok=True)

    if limpar_prints:
        prints = saida / "prints"
        if prints.exists():
            shutil.rmtree(prints, ignore_errors=True)

    (saida / "prints" / "irregulares" / "tela_ate_3_polegadas").mkdir(parents=True, exist_ok=True)
    (saida / "prints" / "suspeitos" / "tela_proxima_3_polegadas").mkdir(parents=True, exist_ok=True)
    (saida / "prints" / "suspeitos" / "sem_tela").mkdir(parents=True, exist_ok=True)
    (saida / "suspeitos_tela_proxima_3").mkdir(parents=True, exist_ok=True)
    (saida / "suspeitos_sem_tela").mkdir(parents=True, exist_ok=True)

    arquivos_antigos = [
        "products.csv",
        "comments.csv",
        "comments.parquet",
        "resumo.csv",
        "resumo.json",
        "suspeitos_sem_medidas.parquet",
    ]
    for nome in arquivos_antigos:
        alvo = saida / nome
        if alvo.exists():
            alvo.unlink()

    # Remove pastas antigas para não misturar prints da regra anterior
    # baseada em medida física/termo "mini".
    pastas_antigas = [
        saida / "json",
        saida / "prints" / "descartados",
        saida / "prints" / "irregulares" / "mini_celulares",
        saida / "prints" / "irregulares" / "tela_ate_5_polegadas",
        saida / "prints" / "irregulares" / "sem_medidas",
        saida / "prints" / "irregulares" / "revisar_medidas",
        saida / "prints" / "irregulares" / "sem_anatel",
        saida / "suspeitos_sem_medidas",
    ]
    for pasta in pastas_antigas:
        if pasta.exists():
            shutil.rmtree(pasta, ignore_errors=True)

def escrever_resumo_txt(saida: Path, linhas: Iterable[str]) -> Path:
    path = saida / "resumo.txt"
    conteudo = "\n".join(str(linha) for linha in linhas)
    path.write_text(conteudo, encoding="utf-8")
    return path
