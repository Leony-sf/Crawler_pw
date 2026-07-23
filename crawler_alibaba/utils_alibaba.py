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
    if not url: return ""
    url = url.strip()
    if url.startswith("//"): url = "https:" + url
    if url.startswith("/"): url = urljoin(BASE_URL_ALIBABA, url)
    partes = urlsplit(url)
    return urlunsplit((partes.scheme or "https", partes.netloc, partes.path, "", ""))

def montar_url_busca(termo: str, pagina: int = 1) -> str:
    termo_q = quote_plus(termo)
    return f"{BASE_URL_ALIBABA}/trade/search?fsb=y&IndexArea=product_en&SearchText={termo_q}&page={pagina}"

def resolver_arquivo_txt(caminho_txt: str) -> Path:
    entrada = Path(caminho_txt)
    candidatos = []
    if entrada.is_absolute():
        candidatos.append(entrada)
    else:
        cwd = Path.cwd()
        pasta_script = Path(__file__).resolve().parent
        candidatos.extend([cwd / entrada, pasta_script / entrada])

    aliases = ["buscar_alibaba.txt", "buscas_alibaba.txt"]
    for nome in aliases:
        candidatos.extend([Path.cwd() / nome, Path(__file__).resolve().parent / nome])

    vistos = set()
    for candidato in candidatos:
        candidato = candidato.resolve()
        if candidato in vistos: continue
        vistos.add(candidato)
        if candidato.exists() and candidato.is_file(): return candidato

    raise FileNotFoundError("Arquivo TXT de buscas não encontrado.")

def carregar_termos_busca(caminho_txt: str) -> List[str]:
    path = resolver_arquivo_txt(caminho_txt)
    termos = [linha.strip() for linha in path.read_text(encoding="utf-8-sig").splitlines() if linha.strip() and not linha.startswith("#")]
    if not termos: raise ValueError(f"O arquivo {path} não possui termos válidos.")
    return termos

def preparar_saida(saida: Path, limpar_prints: bool = False) -> None:
    saida.mkdir(parents=True, exist_ok=True)
    if limpar_prints and (saida / "prints").exists():
        shutil.rmtree(saida / "prints", ignore_errors=True)

    # Criação das novas pastas para a regra de medidas
    (saida / "prints" / "irregulares" / "medidas_ate_12x5_5").mkdir(parents=True, exist_ok=True)
    (saida / "prints" / "suspeitos" / "medida_mista").mkdir(parents=True, exist_ok=True)
    (saida / "prints" / "suspeitos" / "sem_medidas").mkdir(parents=True, exist_ok=True)
    (saida / "suspeitos_medidas_mistas").mkdir(parents=True, exist_ok=True)
    (saida / "suspeitos_sem_medidas").mkdir(parents=True, exist_ok=True)

    arquivos_antigos = ["products.csv", "comments.csv", "comments.parquet", "resumo.csv", "resumo.json", "suspeitos_sem_tela.parquet"]
    for nome in arquivos_antigos:
        alvo = saida / nome
        if alvo.exists(): alvo.unlink()

    # Remove pastas antigas de lógica de tela
    pastas_antigas = [
        saida / "json",
        saida / "prints" / "irregulares" / "tela_ate_3_polegadas",
        saida / "prints" / "suspeitos" / "tela_proxima_3_polegadas",
        saida / "prints" / "suspeitos" / "sem_tela",
        saida / "suspeitos_tela_proxima_3",
        saida / "suspeitos_sem_tela",
    ]
    for pasta in pastas_antigas:
        if pasta.exists():
            shutil.rmtree(pasta, ignore_errors=True)

def escrever_resumo_txt(saida: Path, linhas: Iterable[str]) -> Path:
    path = saida / "resumo.txt"
    path.write_text("\n".join(str(linha) for linha in linhas), encoding="utf-8")
    return path