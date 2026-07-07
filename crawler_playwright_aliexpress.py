from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from extracao_aliexpress import classificar_produto
from utils_aliexpress import (
    garantir_pastas,
    hash_curto,
    rolar_pagina,
    salvar_tabelas,
    salvar_resumo,
    limpar_saidas_legadas,
    slugify,
)


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


def montar_url_busca(termo: str, pagina: int = 1) -> str:
    termo_url = quote_plus(termo)
    # A URL /wholesale costuma aceitar SearchText e paginação simples.
    return f"https://www.aliexpress.com/wholesale?SearchText={termo_url}&page={pagina}"


async def _fechar_popups_basicos(page) -> None:
    textos = [
        "Accept", "Aceitar", "Concordo", "I agree", "Got it", "Entendi",
        "Não, obrigado", "No thanks", "Continuar", "Continue",
    ]
    for texto in textos:
        try:
            loc = page.get_by_text(texto, exact=False).first
            if await loc.count() > 0 and await loc.is_visible(timeout=800):
                await loc.click(timeout=800)
                await page.wait_for_timeout(500)
        except Exception:
            pass

    # Botões de fechar modais são variáveis; tenta alguns padrões sem quebrar o fluxo.
    seletores = [
        "button[aria-label='Close']",
        "button[aria-label='close']",
        ".pop-close-btn",
        ".close-btn",
        "[class*='close']",
    ]
    for seletor in seletores:
        try:
            loc = page.locator(seletor).first
            if await loc.count() > 0 and await loc.is_visible(timeout=500):
                await loc.click(timeout=700)
                await page.wait_for_timeout(400)
        except Exception:
            pass


async def _coletar_links_resultados(page, limite_restante: int) -> List[Dict[str, str]]:
    await rolar_pagina(page, passos=5, pausa=0.45)

    itens = await page.evaluate(
        """
        () => {
            const anchors = Array.from(document.querySelectorAll('a[href*="/item/"]'));
            const out = [];
            const vistos = new Set();
            for (const a of anchors) {
                let href = a.href || a.getAttribute('href') || '';
                if (!href.includes('/item/')) continue;
                href = href.split('?')[0];
                if (!href.startsWith('http')) href = new URL(href, location.href).href;
                if (vistos.has(href)) continue;
                vistos.add(href);

                const card = a.closest('[class*="search"], [class*="product"], [data-item-id], div') || a;
                const img = card.querySelector('img') || a.querySelector('img');
                const textoCard = (card.innerText || a.innerText || '').trim();
                const alt = img ? (img.alt || img.getAttribute('aria-label') || '') : '';
                const titleAttr = a.getAttribute('title') || '';
                const titulo = (titleAttr || alt || textoCard || '').trim();
                const imagem = img ? (img.src || img.getAttribute('src') || img.getAttribute('data-src') || '') : '';
                out.push({url: href, titulo_card: titulo, texto_card: textoCard, imagem_card: imagem});
            }
            return out;
        }
        """
    )

    filtrados: List[Dict[str, str]] = []
    vistos = set()
    for item in itens:
        url = item.get("url", "")
        if not url or url in vistos:
            continue
        vistos.add(url)
        filtrados.append(item)
        if len(filtrados) >= limite_restante:
            break
    return filtrados


async def _texto_primeiro(page, seletores: List[str], timeout: int = 1500) -> str:
    for seletor in seletores:
        try:
            loc = page.locator(seletor).first
            if await loc.count() > 0:
                texto = await loc.inner_text(timeout=timeout)
                if texto and texto.strip():
                    return texto.strip()
        except Exception:
            pass
    return ""


async def _atributo_primeiro(page, seletores: List[str], atributo: str = "src", timeout: int = 1000) -> str:
    for seletor in seletores:
        try:
            loc = page.locator(seletor).first
            if await loc.count() > 0:
                val = await loc.get_attribute(atributo, timeout=timeout)
                if val:
                    return val
        except Exception:
            pass
    return ""


async def _capturar_detalhes_produto(page) -> Dict[str, Any]:
    await _fechar_popups_basicos(page)
    await page.wait_for_timeout(1200)
    await rolar_pagina(page, passos=4, pausa=0.5)

    titulo = await _texto_primeiro(
        page,
        [
            "h1",
            "[data-pl='product-title']",
            "[class*='title'] h1",
            "[class*='product-title']",
        ],
    )
    if not titulo:
        try:
            titulo = (await page.title()).replace("| AliExpress", "").strip()
        except Exception:
            titulo = ""

    preco = await _texto_primeiro(
        page,
        [
            "[data-pl='product-price']",
            "[class*='price']",
            "[class*='Price']",
        ],
        timeout=1000,
    )

    loja = await _texto_primeiro(
        page,
        [
            "[data-pl='store-name']",
            "a[href*='/store/']",
            "[class*='store-name']",
            "[class*='Store'] a",
        ],
        timeout=1000,
    )

    imagem = await _atributo_primeiro(
        page,
        [
            "img[class*='magnifier']",
            "[data-pl='product-image'] img",
            "img[src*='alicdn']",
        ],
    )

    # Tenta expandir/ver mais detalhes quando existir.
    for texto in ["View More", "Ver mais", "Show more", "Mais", "Specifications", "Especificações"]:
        try:
            loc = page.get_by_text(texto, exact=False).first
            if await loc.count() > 0 and await loc.is_visible(timeout=500):
                await loc.click(timeout=800)
                await page.wait_for_timeout(500)
        except Exception:
            pass

    texto_pagina = ""
    try:
        texto_pagina = await page.locator("body").inner_text(timeout=2500)
    except Exception:
        texto_pagina = ""

    detalhes = ""
    for seletor in [
        "[class*='specification']",
        "[class*='spec']",
        "[data-pl*='spec']",
        "[class*='product-property']",
        "[class*='sku-property']",
    ]:
        try:
            partes = await page.locator(seletor).all_inner_texts(timeout=1200)
            if partes:
                detalhes = "\n".join(p.strip() for p in partes if p.strip())
                if detalhes:
                    break
        except Exception:
            pass

    return {
        "titulo": titulo,
        "preco": preco,
        "loja": loja,
        "imagem": imagem,
        "detalhes": detalhes,
        "texto_pagina": texto_pagina[:15000],
    }


async def _print_produto(page, base_saida: Path, categoria_print: str, titulo: str, url: str) -> str:
    nome = f"{slugify(titulo, 70)}_{hash_curto(url)}.png"
    pasta = base_saida / "prints" / categoria_print
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / nome
    try:
        await page.screenshot(path=str(caminho), full_page=True)
        return str(caminho)
    except Exception as exc:
        print(f"[print] Falha ao capturar print: {exc}")
        return ""


async def rodar_crawler_aliexpress(
    queries: List[str],
    saida: str = "saidas_aliexpress",
    limit: int = 50,
    max_paginas: int = 1,
    headless: bool = False,
    pausa_login: bool = True,
    user_data_dir: str = "perfil_aliexpress",
    manter_brinquedos: bool = False,
) -> List[Dict[str, Any]]:
    base_saida = Path(saida)
    limpar_saidas_legadas(base_saida)
    garantir_pastas(base_saida)

    produtos: List[Dict[str, Any]] = []
    urls_visitadas = set()

    async with async_playwright() as p:
        browser_context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=headless,
            viewport={"width": 1366, "height": 900},
            locale="pt-BR",
            user_agent=DEFAULT_USER_AGENT,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
        )
        page = browser_context.pages[0] if browser_context.pages else await browser_context.new_page()
        page.set_default_timeout(12000)

        if pausa_login:
            print("\n[login] O navegador será aberto. Resolva login/captcha/cookies se aparecer.")
            await page.goto("https://www.aliexpress.com/", wait_until="domcontentloaded", timeout=60000)
            await _fechar_popups_basicos(page)
            input("[login] Quando a página estiver pronta, pressione ENTER aqui para começar... ")

        for query in queries:
            if len(produtos) >= limit:
                break
            print(f"\n[busca] {query}")

            for pagina_num in range(1, max_paginas + 1):
                if len(produtos) >= limit:
                    break

                url_busca = montar_url_busca(query, pagina_num)
                print(f"[pagina] {pagina_num}/{max_paginas} -> {url_busca}")
                try:
                    await page.goto(url_busca, wait_until="domcontentloaded", timeout=60000)
                    await page.wait_for_timeout(2500)
                    await _fechar_popups_basicos(page)
                except PlaywrightTimeoutError:
                    print("[pagina] Timeout ao abrir busca. Pulando página.")
                    continue
                except Exception as exc:
                    print(f"[pagina] Erro ao abrir busca: {exc}")
                    continue

                restante = max(0, limit - len(produtos))
                links = await _coletar_links_resultados(page, restante * 2)
                print(f"[pagina] Links candidatos encontrados: {len(links)}")

                for item in links:
                    if len(produtos) >= limit:
                        break
                    url_produto = item.get("url", "")
                    if not url_produto or url_produto in urls_visitadas:
                        continue
                    urls_visitadas.add(url_produto)

                    produto_page = await browser_context.new_page()
                    produto_page.set_default_timeout(12000)
                    try:
                        print(f"\n[produto] {len(produtos) + 1}/{limit} abrindo: {url_produto}")
                        await produto_page.goto(url_produto, wait_until="domcontentloaded", timeout=60000)
                        detalhes = await _capturar_detalhes_produto(produto_page)

                        produto: Dict[str, Any] = {
                            "plataforma": "AliExpress",
                            "query": query,
                            "pagina_busca": pagina_num,
                            "url": url_produto,
                            "titulo_card": item.get("titulo_card", ""),
                            "texto_card": item.get("texto_card", ""),
                            "imagem_card": item.get("imagem_card", ""),
                            **detalhes,
                        }

                        classificacao = classificar_produto(produto, manter_brinquedos=manter_brinquedos)
                        produto.update(classificacao.to_dict())

                        titulo_log = produto.get("titulo") or produto.get("titulo_card") or "SEM TÍTULO"
                        print(f"[status] {classificacao.status} | {titulo_log[:110]}")
                        print(f"[motivo] {classificacao.motivo}")

                        # Prints somente para produtos mantidos na análise.
                        # Descartados não geram print nem pasta prints/descartados.
                        if classificacao.manter:
                            produto["print"] = await _print_produto(
                                produto_page,
                                base_saida,
                                classificacao.categoria_print,
                                titulo_log,
                                url_produto,
                            )
                        else:
                            produto["print"] = ""


                        # Mantém um resumo do texto, não o body inteiro.
                        texto_pagina = produto.get("texto_pagina") or ""
                        produto["texto_pagina_resumo"] = texto_pagina[:1000]
                        produto.pop("texto_pagina", None)

                        produtos.append(produto)
                        salvar_tabelas(base_saida, produtos)

                    except PlaywrightTimeoutError:
                        print("[produto] Timeout ao abrir/extrair. Pulando.")
                    except Exception as exc:
                        print(f"[produto] Erro: {exc}")
                    finally:
                        try:
                            await produto_page.close()
                        except Exception:
                            pass

        await browser_context.close()

    salvar_tabelas(base_saida, produtos)
    resumo = {
        "total_produtos": len(produtos),
        "irregulares": sum(1 for p in produtos if p.get("status") == "IRREGULAR"),
        "revisar": sum(1 for p in produtos if p.get("status") == "REVISAR"),
        "descartados": sum(1 for p in produtos if p.get("status") == "DESCARTADO"),
        "sem_medidas": sum(1 for p in produtos if p.get("categoria_print") == "irregulares/sem_medidas"),
    }
    salvar_resumo(base_saida, resumo)

    print("\n[resumo]")
    for k, v in resumo.items():
        print(f"- {k}: {v}")
    print(f"\n[saida] Arquivos salvos em: {base_saida.resolve()}")
    return produtos


def executar_sync(**kwargs):
    return asyncio.run(rodar_crawler_aliexpress(**kwargs))
