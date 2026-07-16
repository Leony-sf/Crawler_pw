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

        # Ordem correta de leitura do TXT:
        # página 1 do termo 1 -> página 1 do termo 2 -> página 1 do termo 3...
        # depois, se --max-paginas for maior que 1, página 2 de todos os termos, e assim por diante.
        for pagina in range(1, config.max_paginas + 1):
            if len(resultados) >= config.limit:
                break

            _imprimir_secao(f"RODADA DE BUSCA | PÁGINA {pagina}/{config.max_paginas}")

            for idx_termo, termo in enumerate(termos, start=1):
                if len(resultados) >= config.limit:
                    break

                url_busca = montar_url_busca(termo, pagina)
                print(f"\n[BUSCA] Linha {idx_termo}/{len(termos)} do TXT | Página {pagina}/{config.max_paginas}")
                print(f"        Termo: {termo}")
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
                    if len(resultados) >= config.limit:
                        break

                    url_produto = card.get("url", "")
                    if not url_produto or url_produto in visitados:
                        continue
                    visitados.add(url_produto)

                    registro = await _processar_produto(
                        contexto=contexto,
                        url_produto=url_produto,
                        card=card,
                        config=config,
                        termo=termo,
                        pagina=pagina,
                        indice_item=indice,
                        total_itens=len(cards),
                        numero_processado=len(visitados),
                    )
                    if not registro:
                        total_erros += 1
                        continue

                    if registro.get("status") == "DESCARTADO":
                        total_descartados += 1
                        if not config.salvar_descartados:
                            continue

                    resultados.append(registro)
                    _salvar_parquets_incrementais(resultados, config.saida)

        await contexto.close()

    _salvar_parquets_incrementais(resultados, config.saida)
    _salvar_resumo(resultados, config, termos, total_cards, total_descartados, total_erros)
    _imprimir_final(resultados, config, total_descartados, total_erros)
    return resultados


async def _obter_pagina_principal(contexto: BrowserContext) -> Page:
    """
    Reaproveita a página aberta pelo contexto persistente.

    O Chromium criado com launch_persistent_context costuma iniciar com uma aba
    about:blank. Se chamarmos new_page() imediatamente, aparecem duas abas em
    branco. Por isso usamos a primeira aba existente e fechamos abas extras
    vazias.
    """
    if contexto.pages:
        page = contexto.pages[0]
        for extra in contexto.pages[1:]:
            try:
                if extra.url == "about:blank":
                    await extra.close()
            except Exception:
                pass
        return page
    return await contexto.new_page()


async def _abrir_pagina_para_pausa(page: Page, config: ConfigAlibaba, primeiro_termo: str) -> None:
    """Abre o Alibaba antes da pausa manual, evitando tela about:blank."""
    url_inicial = montar_url_busca(primeiro_termo, 1)
    print(f"[INÍCIO] Abrindo Alibaba para verificação inicial...")
    try:
        await page.goto(url_inicial, wait_until="domcontentloaded", timeout=config.timeout_ms)
        await esperar_carregamento(page, timeout_ms=config.timeout_ms)
        await fechar_popups_basicos(page)
    except PlaywrightTimeoutError:
        print("        Aviso: timeout ao abrir Alibaba antes da pausa. A página pode ainda estar carregando.")
    except Exception as exc:
        print(f"        Aviso: não foi possível abrir a página inicial: {_texto_curto(str(exc), 120)}")
        print("        Acesse manualmente https://www.alibaba.com nessa janela e depois pressione ENTER.")


async def _criar_contexto(p: Any, config: ConfigAlibaba) -> BrowserContext:
    perfil = Path("perfil_alibaba").resolve()
    perfil.mkdir(parents=True, exist_ok=True)
    contexto = await p.chromium.launch_persistent_context(
        user_data_dir=str(perfil),
        headless=config.headless,
        slow_mo=config.slow_mo,
        viewport={"width": 1366, "height": 900},
        locale="en-US",
        args=[
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
        ],
    )
    return contexto


async def _processar_produto(
    contexto: BrowserContext,
    url_produto: str,
    card: Dict[str, Any],
    config: ConfigAlibaba,
    termo: str,
    pagina: int,
    indice_item: int,
    total_itens: int,
    numero_processado: int,
) -> Optional[Dict[str, Any]]:
    page: Optional[Page] = None
    try:
        page = await contexto.new_page()
        page.set_default_timeout(config.timeout_ms)
        await page.goto(url_produto, wait_until="domcontentloaded", timeout=config.timeout_ms)
        produto = await extrair_produto(page, url_produto, card)
        classificacao = classificar_produto(produto)

        registro: Dict[str, Any] = {
            "data_coleta": agora_iso(),
            "marketplace": "Alibaba.com",
            "termo_busca": termo,
            "pagina_busca": pagina,
            "item_busca": indice_item,
            "status": classificacao.status,
            **classificacao.as_dict(),
            "titulo": produto.get("titulo", ""),
            "preco": produto.get("preco", ""),
            "fornecedor": produto.get("fornecedor", ""),
            "moq": produto.get("moq", ""),
            "vendidos_pedidos": produto.get("vendidos_pedidos", ""),
            "url": produto.get("url", url_produto),
            "url_canonica": produto.get("url_canonica", url_produto),
            "imagem": produto.get("imagem", ""),
            "detalhes": produto.get("detalhes", "")[:6000],
            "texto_card": produto.get("texto_card", "")[:2000],
            "print_comprovante": "",
        }

        if classificacao.status != "DESCARTADO" and classificacao.categoria_print:
            registro["print_comprovante"] = await _tirar_print_produto(
                page, config.saida, registro, classificacao.categoria_print
            )

        _imprimir_produto(registro, numero_processado, config.limit, indice_item, total_itens)
        return registro
    except PlaywrightTimeoutError:
        registro_erro = {
            "data_coleta": agora_iso(),
            "marketplace": "Alibaba.com",
            "termo_busca": termo,
            "pagina_busca": pagina,
            "item_busca": indice_item,
            "status": "ERRO",
            "categoria_print": "",
            "motivo": "Timeout ao abrir/coletar produto.",
            "evidencias": "",
            "codigo_anatel": "",
            "medidas_extraidas": "",
            "altura_cm": None,
            "largura_cm": None,
            "medida_proxima_ou_menor": False,
            "sem_medidas": False,
            "sem_tela": False,
            "tela_extraida": "",
            "tela_polegadas": None,
            "tela_mini": False,
            "tela_suspeita": False,
            "tela_grande": False,
            "eh_mini_celular": False,
            "eh_acessorio": False,
            "regra_classificacao": "timeout",
            "titulo": card.get("titulo_busca", ""),
            "preco": "",
            "fornecedor": "",
            "moq": "",
            "vendidos_pedidos": "",
            "url": url_produto,
            "url_canonica": url_produto,
            "imagem": "",
            "detalhes": "",
            "texto_card": card.get("texto_card", ""),
            "print_comprovante": "",
        }
        _imprimir_produto(registro_erro, numero_processado, config.limit, indice_item, total_itens)
        return registro_erro
    except Exception as exc:
        print(f"[{numero_processado:03d}] ERRO | {_texto_curto(str(exc), 110)}")
        return None
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass


async def _tirar_print_produto(page: Page, saida: Path, registro: Dict[str, Any], categoria: str) -> str:
    pasta = saida / "prints" / categoria
    pasta.mkdir(parents=True, exist_ok=True)
    titulo = slugify(registro.get("titulo") or registro.get("url_canonica", "produto"), max_len=70)
    indice = abs(hash(registro.get("url_canonica", ""))) % 10_000_000
    caminho = pasta / f"{indice}_{titulo}.png"
    try:
        await page.screenshot(path=str(caminho), full_page=True)
        return str(caminho)
    except Exception as exc:
        print(f"        Aviso: não foi possível tirar print: {_texto_curto(str(exc), 100)}")
        return ""


async def _salvar_print_debug(page: Page, saida: Path, termo: str, pagina: int) -> None:
    pasta = saida / "prints" / "debug_busca_sem_links"
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"{slugify(termo)}_pagina_{pagina}.png"
    try:
        await page.screenshot(path=str(caminho), full_page=True)
        print(f"        Debug: busca sem links. Print salvo em {caminho}")
    except Exception:
        pass


def _salvar_parquets_incrementais(resultados: List[Dict[str, Any]], saida: Path) -> None:
    if not resultados:
        return

    df = pd.DataFrame(resultados)
    df.to_parquet(saida / "products.parquet", index=False)

    if "sem_tela" in df.columns:
        sem_tela = df[
            (df["sem_tela"] == True)  # noqa: E712
            & (df["status"].isin(["REVISAR"]))
        ].copy()
    elif "sem_medidas" in df.columns:
        sem_tela = df[
            (df["sem_medidas"] == True)  # noqa: E712
            & (df["status"].isin(["REVISAR"]))
        ].copy()
    else:
        sem_tela = pd.DataFrame()

    if "tela_suspeita" in df.columns:
        tela_proxima = df[
            (df["tela_suspeita"] == True)  # noqa: E712
            & (df["status"].isin(["SUSPEITO"]))
        ].copy()
    else:
        tela_proxima = pd.DataFrame()

    pasta_sem_tela = saida / "suspeitos_sem_tela"
    pasta_sem_tela.mkdir(parents=True, exist_ok=True)
    caminho_sem_tela = pasta_sem_tela / "suspeitos_sem_tela.parquet"
    if not sem_tela.empty:
        sem_tela.to_parquet(caminho_sem_tela, index=False)
    elif caminho_sem_tela.exists():
        caminho_sem_tela.unlink()

    pasta_tela_proxima = saida / "suspeitos_tela_proxima_3"
    pasta_tela_proxima.mkdir(parents=True, exist_ok=True)
    caminho_tela_proxima = pasta_tela_proxima / "suspeitos_tela_proxima_3.parquet"
    if not tela_proxima.empty:
        tela_proxima.to_parquet(caminho_tela_proxima, index=False)
    elif caminho_tela_proxima.exists():
        caminho_tela_proxima.unlink()

def _salvar_resumo(
    resultados: List[Dict[str, Any]],
    config: ConfigAlibaba,
    termos: List[str],
    total_cards: int,
    total_descartados: int,
    total_erros: int,
) -> None:
    df = pd.DataFrame(resultados)
    qtd_sem_tela = 0
    qtd_irregulares_tela = 0
    qtd_suspeitos_tela = 0
    if not df.empty:
        if "sem_tela" in df.columns:
            qtd_sem_tela = int(((df["sem_tela"] == True) & (df["status"] == "REVISAR")).sum())  # noqa: E712
        if "status" in df.columns:
            qtd_irregulares_tela = int((df["status"] == "IRREGULAR").sum())
            qtd_suspeitos_tela = int((df["status"] == "SUSPEITO").sum())

    linhas = [
        "Resumo da coleta Alibaba.com",
        "================================",
        f"Data/hora: {agora_iso()}",
        f"Regra aplicada: celular com tela <= 3 polegadas = IRREGULAR; acima de 3 até 3,5 = SUSPEITO",
        f"Termos de busca: {', '.join(termos)}",
        f"Páginas por termo: {config.max_paginas}",
        f"Limite configurado: {config.limit}",
        f"Links candidatos em páginas de busca: {total_cards}",
        f"Registros salvos no products.parquet: {len(resultados)}",
        f"Irregulares por tela <= 3 polegadas: {qtd_irregulares_tela}",
        f"Suspeitos por tela próxima de 3 polegadas (>3 até 3,5): {qtd_suspeitos_tela}",
        f"Celulares sem tela capturada salvos em suspeitos_sem_tela/suspeitos_sem_tela.parquet: {qtd_sem_tela}",
        f"Descartados não salvos: {total_descartados if not config.salvar_descartados else 0}",
        f"Erros/timeout: {total_erros}",
        "",
        "Contagem por status:",
    ]
    if df.empty:
        linhas.append("- Nenhum registro salvo.")
    else:
        for status, qtd in df["status"].value_counts(dropna=False).items():
            linhas.append(f"- {status}: {qtd}")
        if "categoria_print" in df.columns:
            linhas.extend(["", "Contagem por categoria de print:"])
            for cat, qtd in df["categoria_print"].fillna("").value_counts().items():
                if not cat:
                    continue
                linhas.append(f"- {cat}: {qtd}")

    linhas.extend(
        [
            "",
            "Arquivos gerados:",
            "- products.parquet",
            "- suspeitos_tela_proxima_3/suspeitos_tela_proxima_3.parquet, quando houver tela acima de 3 até 3,5 polegadas",
            "- suspeitos_sem_tela/suspeitos_sem_tela.parquet, quando houver celular sem tela capturada",
            "- resumo.txt",
            "- prints/irregulares/tela_ate_3_polegadas/",
            "- prints/suspeitos/tela_proxima_3_polegadas/",
            "- prints/suspeitos/sem_tela/",
            "",
            "Observação:",
            "- CSV, JSON e comentários não são gerados nesta versão.",
            "- Celulares com tela maior que 3,5 polegadas são descartados.",
            "- Termo 'mini' sozinho não classifica mais como irregular; a decisão principal é a polegada da tela.",
        ]
    )
    escrever_resumo_txt(config.saida, linhas)

def _imprimir_cabecalho(config: ConfigAlibaba, termos: List[str]) -> None:
    _imprimir_secao("CRAWLER ALIBABA.COM | MINI CELULARES")
    print(f"Termos: {len(termos)} | Páginas/termo: {config.max_paginas} | Limite: {config.limit}")
    print(f"Saída: {config.saida.resolve()}")
    print("Arquivos: products.parquet + suspeitos_tela_proxima_3.parquet + suspeitos_sem_tela.parquet")
    print('Filtro : tela <= 3" = IRREGULAR; > 3" até 3,5" = SUSPEITO; > 3,5" = DESCARTADO')


def _imprimir_secao(titulo: str) -> None:
    print("\n" + "=" * 72)
    print(titulo)
    print("=" * 72)


def _imprimir_produto(registro: Dict[str, Any], numero: int, limite: int, item: int, total_itens: int) -> None:
    status = registro.get("status", "")
    categoria = registro.get("categoria_print", "") or "sem_print"
    categoria_curta = categoria.split("/")[-1] if categoria else "sem_print"
    titulo = _texto_curto(registro.get("titulo") or registro.get("url_canonica", ""), 86)
    motivo = _texto_curto(registro.get("motivo", ""), 110)
    tela = registro.get("tela_polegadas", None)
    medida = registro.get("medidas_extraidas", "")

    print(f"[{numero:03d}/{limite}] {status:<10} | {categoria_curta:<14} | item {item}/{total_itens}")
    if titulo:
        print(f"        Título : {titulo}")
    if tela not in (None, ""):
        print(f"        Tela   : {tela}\"")
    elif medida:
        print(f"        Medida : {_texto_curto(medida, 80)}")
    else:
        print("        Tamanho: não localizado")
    if motivo and status != "DESCARTADO":
        print(f"        Motivo : {motivo}")


def _imprimir_final(resultados: List[Dict[str, Any]], config: ConfigAlibaba, total_descartados: int, total_erros: int) -> None:
    df = pd.DataFrame(resultados)
    qtd_sem_tela = 0
    qtd_irregulares = 0
    qtd_suspeitos = 0
    if not df.empty:
        if "sem_tela" in df.columns:
            qtd_sem_tela = int(((df["sem_tela"] == True) & (df["status"] == "REVISAR")).sum())  # noqa: E712
        if "status" in df.columns:
            qtd_irregulares = int((df["status"] == "IRREGULAR").sum())
            qtd_suspeitos = int((df["status"] == "SUSPEITO").sum())

    _imprimir_secao("FINALIZADO")
    print(f"Registros no products.parquet: {len(resultados)}")
    print(f"Irregulares por tela <= 3\": {qtd_irregulares}")
    print(f"Suspeitos por tela > 3 e <= 3,5\": {qtd_suspeitos}")
    print(f"Celulares sem tela capturada: {qtd_sem_tela}")
    print(f"Descartados não salvos: {total_descartados if not config.salvar_descartados else 0}")
    print(f"Erros/timeout: {total_erros}")
    print(f"Pasta de saída: {config.saida.resolve()}")

def _texto_curto(texto: Any, limite: int = 100) -> str:
    texto = " ".join(str(texto or "").split())
    if len(texto) <= limite:
        return texto
    return texto[: limite - 3].rstrip() + "..."


def run(config: ConfigAlibaba) -> List[Dict[str, Any]]:
    return asyncio.run(executar_crawler_alibaba(config))
