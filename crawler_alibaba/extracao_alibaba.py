# -*- coding: utf-8 -*-
"""Extração de links e dados de produto no Alibaba.com."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from utils_alibaba import limpar_url


async def fechar_popups_basicos(page: Page) -> None:
    """Fecha popups comuns sem quebrar a execução caso não existam."""
    seletores = [
        "button:has-text('Accept')",
        "button:has-text('I agree')",
        "button:has-text('Agree')",
        "button:has-text('Got it')",
        "button:has-text('OK')",
        "button:has-text('No thanks')",
        "button[aria-label='Close']",
        ".next-dialog-close",
        ".ui-dialog-close",
        "[class*='close']",
    ]
    for seletor in seletores:
        try:
            loc = page.locator(seletor).first
            if await loc.count() and await loc.is_visible(timeout=700):
                await loc.click(timeout=1000)
                await page.wait_for_timeout(300)
        except Exception:
            continue


async def esperar_carregamento(page: Page, timeout_ms: int = 20000) -> None:
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        pass
    try:
        await page.wait_for_load_state("networkidle", timeout=6000)
    except PlaywrightTimeoutError:
        pass
    await fechar_popups_basicos(page)


async def rolar_pagina(page: Page, passos: int = 4, pausa_ms: int = 700) -> None:
    for _ in range(passos):
        try:
            await page.mouse.wheel(0, 1200)
            await page.wait_for_timeout(pausa_ms)
        except Exception:
            break


async def coletar_links_resultados(page: Page) -> List[Dict[str, Any]]:
    """
    Coleta links de produtos da página de busca.

    Esta versão evita `page.evaluate()` na página inteira. A versão anterior
    tinha uma string JavaScript com `split('\n')` que, ao ser interpretada pelo
    Python, virava uma quebra de linha literal dentro do JavaScript e causava:
    "Page.evaluate: SyntaxError: Invalid or unexpected token".

    Usar locators do Playwright deixa a coleta mais estável e mais fácil de
    depurar quando o Alibaba muda o layout.
    """
    await rolar_pagina(page, passos=4, pausa_ms=600)

    seletores_links = [
        "a[href*='/product-detail/']",
        "a[href*='alibaba.com/product-detail']",
        "a[href*='/trade/search'] + a[href*='/product-detail/']",
    ]

    vistos = set()
    resultados: List[Dict[str, Any]] = []

    for seletor in seletores_links:
        try:
            links = page.locator(seletor)
            total = await links.count()
        except Exception:
            continue

        limite = min(total, 160)
        for i in range(limite):
            try:
                a = links.nth(i)
                href = await a.get_attribute("href", timeout=1200)
                if not href:
                    continue

                url = limpar_url(href)
                if not url or "/product-detail/" not in url or url in vistos:
                    continue

                titulo_attr = await a.get_attribute("title", timeout=800) or ""
                aria = await a.get_attribute("aria-label", timeout=800) or ""
                texto_link = ""
                texto_card = ""

                try:
                    texto_link = (await a.inner_text(timeout=1200)).strip()
                except Exception:
                    texto_link = ""

                # Tenta pegar um texto maior do card onde o link está inserido.
                # Se falhar, usa apenas o texto do próprio link.
                for xpath in [
                    "xpath=ancestor::*[contains(@class, 'card')][1]",
                    "xpath=ancestor::*[contains(@class, 'item')][1]",
                    "xpath=ancestor::div[1]",
                    "xpath=ancestor::div[2]",
                    "xpath=ancestor::div[3]",
                ]:
                    try:
                        candidato = (await a.locator(xpath).inner_text(timeout=900)).strip()
                        if len(candidato) > len(texto_card):
                            texto_card = candidato
                    except Exception:
                        continue

                titulo = titulo_attr or aria or texto_link or (texto_card.splitlines()[0] if texto_card else "")
                vistos.add(url)
                resultados.append(
                    {
                        "url": url,
                        "titulo_busca": re.sub(r"\s+", " ", titulo).strip(),
                        "texto_card": re.sub(r"\s+", " ", texto_card or texto_link).strip(),
                    }
                )
            except Exception:
                continue

        if resultados:
            break

    return resultados

async def _primeiro_texto(page: Page, seletores: List[str]) -> str:
    for seletor in seletores:
        try:
            loc = page.locator(seletor).first
            if await loc.count() and await loc.is_visible(timeout=1200):
                txt = (await loc.inner_text(timeout=1500)).strip()
                if txt:
                    return re.sub(r"\s+", " ", txt)
        except Exception:
            continue
    return ""


async def _meta_content(page: Page, seletor: str) -> str:
    try:
        valor = await page.locator(seletor).first.get_attribute("content", timeout=1200)
        return (valor or "").strip()
    except Exception:
        return ""


async def extrair_produto(page: Page, url: str, card: Dict[str, Any] | None = None) -> Dict[str, Any]:
    card = card or {}
    await esperar_carregamento(page)
    await rolar_pagina(page, passos=5, pausa_ms=500)

    titulo = await _primeiro_texto(
        page,
        [
            "h1",
            "[data-pl='product-title']",
            "[class*='product-title']",
            "[class*='ProductTitle']",
            "[class*='title'] h1",
        ],
    )
    if not titulo:
        titulo = await _meta_content(page, "meta[property='og:title']")
    if not titulo:
        titulo = card.get("titulo_busca", "")

    preco = await _primeiro_texto(
        page,
        [
            "[class*='price']",
            "[data-pl='product-price']",
            "[class*='Price']",
            "span:has-text('US$')",
            "span:has-text('$')",
        ],
    )

    fornecedor = await _primeiro_texto(
        page,
        [
            "a[href*='company_profile']",
            "[class*='supplier'] a",
            "[class*='Supplier'] a",
            "[class*='company'] a",
            "[class*='Company'] a",
            "[data-pl='supplier']",
        ],
    )

    imagem = await _meta_content(page, "meta[property='og:image']")
    if not imagem:
        try:
            imagem = await page.locator("img").first.get_attribute("src", timeout=1200) or ""
        except Exception:
            imagem = ""

    texto_pagina = ""
    try:
        texto_pagina = await page.locator("body").inner_text(timeout=8000)
        texto_pagina = re.sub(r"\s+", " ", texto_pagina).strip()
    except Exception:
        texto_pagina = ""

    detalhes = _extrair_trecho_detalhes(texto_pagina)
    moq = _extrair_moq(texto_pagina)
    vendidos = _extrair_vendidos(texto_pagina)

    return {
        "url": url,
        "url_canonica": limpar_url(url),
        "titulo": titulo,
        "preco": preco,
        "fornecedor": fornecedor,
        "moq": moq,
        "vendidos_pedidos": vendidos,
        "imagem": imagem,
        "detalhes": detalhes,
        "texto_card": card.get("texto_card", ""),
        "texto_pagina": texto_pagina[:80000],
    }


def _extrair_trecho_detalhes(texto: str) -> str:
    if not texto:
        return ""
    marcadores = [
        "Product descriptions",
        "Product Description",
        "Key attributes",
        "Product details",
        "Specifications",
        "Overview",
    ]
    lower = texto.lower()
    indices = [lower.find(m.lower()) for m in marcadores if lower.find(m.lower()) >= 0]
    if not indices:
        return texto[:5000]
    inicio = min(indices)
    return texto[inicio : inicio + 9000]


def _extrair_moq(texto: str) -> str:
    if not texto:
        return ""
    padroes = [
        r"(?:Min\.?\s*order|Minimum order|MOQ)\s*[:：]?\s*([^\|]{1,80})",
        r"(\d+\s*(?:piece|pieces|pcs|sets)\s*\(Min\. order\))",
    ]
    for p in padroes:
        m = re.search(p, texto, re.IGNORECASE)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return ""


def _extrair_vendidos(texto: str) -> str:
    if not texto:
        return ""
    m = re.search(r"(\d+[\d,\.]*\s*(?:sold|orders|pieces sold))", texto, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""
