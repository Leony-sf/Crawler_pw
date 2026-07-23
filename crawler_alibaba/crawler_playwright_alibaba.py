# -*- coding: utf-8 -*-
"""Crawler Alibaba.com com Playwright."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from playwright.async_api import async_playwright, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError

from classificacao_alibaba import classificar_produto
from extracao_alibaba import coletar_links_resultados, esperar_carregamento, extrair_produto, fechar_popups_basicos
from utils_alibaba import agora_iso, carregar_termos_busca, escrever_resumo_txt, montar_url_busca, preparar_saida, slugify

@dataclass
class ConfigAlibaba:
    txt: str = "buscar_alibaba.txt"
    saida: Path = Path("saidas_alibaba")
    limit: int = 100
    max_paginas: int = 2
    headless: bool = False
    slow_mo: int = 0
    timeout_ms: int = 30000
    salvar_descartados: bool = False
    limpar_prints: bool = False
    pausar_inicio: bool = False

async def executar_crawler_alibaba(config: ConfigAlibaba) -> List[Dict[str, Any]]:
    termos = carregar_termos_busca(config.txt)
    preparar_saida(config.saida, limpar_prints=config.limpar_prints)

    resultados: List[Dict[str, Any]] = []
    visitados: set[str] = set()
    total_cards = 0
    total_descartados = 0
    total_erros = 0

    _imprimir_cabecalho(config, termos)

    async with async_playwright() as p:
        contexto = await _criar_contexto(p, config)
        page = await _obter_pagina_principal(contexto)
        page.set_default_timeout(config.timeout_ms)

        if config.pausar_inicio:
            await _abrir_pagina_para_pausa(page, config, termos[0])
            print("\n[LOGIN] Resolva login/captcha/verificação no navegador, se aparecer.")
            input("        Pressione ENTER aqui no terminal para iniciar a coleta...")

        for pagina in range(1, config.max_paginas + 1):
            if len(resultados) >= config.limit: break
            _imprimir_secao(f"RODADA DE BUSCA | PÁGINA {pagina}/{config.max_paginas}")

            for idx_termo, termo in enumerate(termos, start=1):
                if len(resultados) >= config.limit: break
                url_busca = montar_url_busca(termo, pagina)
                print(f"\n[BUSCA] Linha {idx_termo}/{len(termos)} do TXT | Página {pagina}/{config.max_paginas}\n        Termo: {termo}")
                try:
                    await page.goto(url_busca, wait_until="domcontentloaded", timeout=config.timeout_ms)
                    await esperar_carregamento(page, timeout_ms=config.timeout_ms)
                    await fechar_popups_basicos(page)
                except PlaywrightTimeoutError:
                    print("        Aviso: timeout na busca. Tentando aproveitar o que carregou.")
                except Exception as exc:
                    print(f"        Erro ao abrir busca: {_texto_curto(str(exc), 120)}")
                    total_erros += 1
                    continue

                cards = await coletar_links_resultados(page)
                total_cards += len(cards)
                print(f"        Links candidatos: {len(cards)}")

                if not cards:
                    await _salvar_print_debug(page, config.saida, termo, pagina)
                    continue

                for indice, card in enumerate(cards, start=1):
                    if len(resultados) >= config.limit: break
                    url_produto = card.get("url", "")
                    if not url_produto or url_produto in visitados: continue
                    visitados.add(url_produto)

                    registro = await _processar_produto(
                        contexto, url_produto, card, config, termo, pagina, indice, len(cards), len(visitados)
                    )
                    if not registro:
                        total_erros += 1
                        continue

                    if registro.get("status") == "DESCARTADO":
                        total_descartados += 1
                        if not config.salvar_descartados: continue

                    resultados.append(registro)
                    _salvar_parquets_incrementais(resultados, config.saida)

        await contexto.close()

    _salvar_parquets_incrementais(resultados, config.saida)
    _salvar_resumo(resultados, config, termos, total_cards, total_descartados, total_erros)
    _imprimir_final(resultados, config, total_descartados, total_erros)
    return resultados

async def _obter_pagina_principal(contexto: BrowserContext) -> Page:
    if contexto.pages:
        page = contexto.pages[0]
        for extra in contexto.pages[1:]:
            try:
                if extra.url == "about:blank": await extra.close()
            except Exception: pass
        return page
    return await contexto.new_page()

async def _abrir_pagina_para_pausa(page: Page, config: ConfigAlibaba, primeiro_termo: str) -> None:
    url_inicial = montar_url_busca(primeiro_termo, 1)
    print(f"[INÍCIO] Abrindo Alibaba para verificação inicial...")
    try:
        await page.goto(url_inicial, wait_until="domcontentloaded", timeout=config.timeout_ms)
        await esperar_carregamento(page, timeout_ms=config.timeout_ms)
        await fechar_popups_basicos(page)
    except Exception as exc:
        print(f"        Aviso: não foi possível abrir a página inicial: {_texto_curto(str(exc), 120)}")

async def _criar_contexto(p: Any, config: ConfigAlibaba) -> BrowserContext:
    perfil = Path("perfil_alibaba").resolve()
    perfil.mkdir(parents=True, exist_ok=True)
    return await p.chromium.launch_persistent_context(
        user_data_dir=str(perfil), headless=config.headless, slow_mo=config.slow_mo,
        viewport={"width": 1366, "height": 900}, locale="en-US",
        args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
    )

async def _processar_produto(
    contexto: BrowserContext, url_produto: str, card: Dict[str, Any], config: ConfigAlibaba, termo: str,
    pagina: int, indice_item: int, total_itens: int, numero_processado: int
) -> Optional[Dict[str, Any]]:
    page: Optional[Page] = None
    try:
        page = await contexto.new_page()
        page.set_default_timeout(config.timeout_ms)
        await page.goto(url_produto, wait_until="domcontentloaded", timeout=config.timeout_ms)
        produto = await extrair_produto(page, url_produto, card)
        classificacao = classificar_produto(produto)

        registro: Dict[str, Any] = {
            "data_coleta": agora_iso(), "marketplace": "Alibaba.com", "termo_busca": termo,
            "pagina_busca": pagina, "item_busca": indice_item, "status": classificacao.status,
            **classificacao.as_dict(), "titulo": produto.get("titulo", ""), "preco": produto.get("preco", ""),
            "fornecedor": produto.get("fornecedor", ""), "moq": produto.get("moq", ""),
            "vendidos_pedidos": produto.get("vendidos_pedidos", ""), "url": produto.get("url", url_produto),
            "url_canonica": produto.get("url_canonica", url_produto), "imagem": produto.get("imagem", ""),
            "detalhes": produto.get("detalhes", "")[:6000], "texto_card": produto.get("texto_card", "")[:2000],
            "print_comprovante": "",
        }

        if classificacao.status != "DESCARTADO" and classificacao.categoria_print:
            registro["print_comprovante"] = await _tirar_print_produto(page, config.saida, registro, classificacao.categoria_print)

        _imprimir_produto(registro, numero_processado, config.limit, indice_item, total_itens)
        return registro
    except Exception as exc:
        if isinstance(exc, PlaywrightTimeoutError):
            print(f"[{numero_processado:03d}] ERRO | Timeout ao coletar.")
            return None
        print(f"[{numero_processado:03d}] ERRO | {_texto_curto(str(exc), 110)}")
        return None
    finally:
        if page:
            try: await page.close()
            except Exception: pass

async def _tirar_print_produto(page: Page, saida: Path, registro: Dict[str, Any], categoria: str) -> str:
    pasta = saida / "prints" / categoria
    pasta.mkdir(parents=True, exist_ok=True)
    titulo = slugify(registro.get("titulo") or registro.get("url_canonica", "produto"), max_len=70)
    caminho = pasta / f"{abs(hash(registro.get('url_canonica', ''))) % 10_000_000}_{titulo}.png"
    try:
        await page.screenshot(path=str(caminho), full_page=True)
        return str(caminho)
    except Exception: return ""

async def _salvar_print_debug(page: Page, saida: Path, termo: str, pagina: int) -> None:
    pasta = saida / "prints" / "debug_busca_sem_links"
    pasta.mkdir(parents=True, exist_ok=True)
    try:
        await page.screenshot(path=str(pasta / f"{slugify(termo)}_pagina_{pagina}.png"), full_page=True)
    except Exception: pass

def _salvar_parquets_incrementais(resultados: List[Dict[str, Any]], saida: Path) -> None:
    if not resultados: return
    df = pd.DataFrame(resultados)
    df.to_parquet(saida / "products.parquet", index=False)

    sem_medidas = df[(df["sem_medidas"] == True) & (df["status"] == "REVISAR")].copy() if "sem_medidas" in df.columns else pd.DataFrame() # noqa: E712
    medida_mista = df[(df["status"] == "SUSPEITO")].copy() if "status" in df.columns else pd.DataFrame()

    pasta_sem_med = saida / "suspeitos_sem_medidas"
    pasta_sem_med.mkdir(parents=True, exist_ok=True)
    if not sem_medidas.empty: sem_medidas.to_parquet(pasta_sem_med / "suspeitos_sem_medidas.parquet", index=False)

    pasta_mistos = saida / "suspeitos_medidas_mistas"
    pasta_mistos.mkdir(parents=True, exist_ok=True)
    if not medida_mista.empty: medida_mista.to_parquet(pasta_mistos / "suspeitos_medidas_mistas.parquet", index=False)

def _salvar_resumo(resultados: List[Dict[str, Any]], config: ConfigAlibaba, termos: List[str], total_cards: int, total_descartados: int, total_erros: int) -> None:
    df = pd.DataFrame(resultados)
    qtd_sem_medidas, qtd_irregulares, qtd_suspeitos = 0, 0, 0
    if not df.empty:
        if "sem_medidas" in df.columns: qtd_sem_medidas = int(((df["sem_medidas"] == True) & (df["status"] == "REVISAR")).sum()) # noqa: E712
        if "status" in df.columns:
            qtd_irregulares = int((df["status"] == "IRREGULAR").sum())
            qtd_suspeitos = int((df["status"] == "SUSPEITO").sum())

    linhas = [
        "Resumo da coleta Alibaba.com", "================================",
        f"Data/hora: {agora_iso()}",
        f"Regra aplicada: altura <= 12cm e largura <= 5.5cm = IRREGULAR",
        f"Registros salvos no products.parquet: {len(resultados)}",
        f"Irregulares: {qtd_irregulares} | Suspeitos: {qtd_suspeitos} | Sem medidas: {qtd_sem_medidas}",
        f"Descartados não salvos: {total_descartados if not config.salvar_descartados else 0} | Erros: {total_erros}", "",
    ]
    escrever_resumo_txt(config.saida, linhas)

def _imprimir_cabecalho(config: ConfigAlibaba, termos: List[str]) -> None:
    _imprimir_secao("CRAWLER ALIBABA.COM | MINI CELULARES")
    print(f"Termos: {len(termos)} | Limite: {config.limit}")
    print('Filtro : Dimensões <= 12x5.5 cm = IRREGULAR')

def _imprimir_secao(titulo: str) -> None:
    print("\n" + "=" * 72 + f"\n{titulo}\n" + "=" * 72)

def _imprimir_produto(registro: Dict[str, Any], numero: int, limite: int, item: int, total_itens: int) -> None:
    print(f"[{numero:03d}/{limite}] {registro.get('status', ''):<10} | {str(registro.get('categoria_print', '')).split('/')[-1]:<14}")
    if registro.get('altura_cm') is not None:
        print(f"        Medida : {registro.get('altura_cm')}x{registro.get('largura_cm')} cm")
    else:
        print("        Tamanho: não localizado")

def _imprimir_final(resultados: List[Dict[str, Any]], config: ConfigAlibaba, total_descartados: int, total_erros: int) -> None:
    _imprimir_secao("FINALIZADO")
    print(f"Registros salvos: {len(resultados)}")

def _texto_curto(texto: Any, limite: int = 100) -> str:
    texto = " ".join(str(texto or "").split())
    return texto if len(texto) <= limite else texto[: limite - 3].rstrip() + "..."

def run(config: ConfigAlibaba) -> List[Dict[str, Any]]:
    return asyncio.run(executar_crawler_alibaba(config))