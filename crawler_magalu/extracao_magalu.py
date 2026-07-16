# -*- coding: utf-8 -*-
"""Extração de links e dados de produto no Magalu."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from utils_magalu import BASE_URL_MAGALU, limpar_url


async def fechar_popups_basicos(page: Page) -> None:
    seletores = [
        "button:has-text('Aceitar')",
        "button:has-text('ACEITAR')",
        "button:has-text('Entendi')",
        "button:has-text('OK')",
        "button:has-text('Ok')",
        "button:has-text('Agora não')",
        "button:has-text('Não, obrigado')",
        "button[aria-label='Fechar']",
        "button[aria-label='close']",
        "[data-testid*='close']",
        "[class*='close']",
    ]
    for seletor in seletores:
        try:
            loc = page.locator(seletor).first
            if await loc.count() and await loc.is_visible(timeout=700):
                await loc.click(timeout=1000)
                await page.wait_for_timeout(250)
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


async def rolar_pagina(page: Page, passos: int = 4, pausa_ms: int = 650) -> None:
    for _ in range(passos):
        try:
            await page.mouse.wheel(0, 1200)
            await page.wait_for_timeout(pausa_ms)
        except Exception:
            break


def _parece_link_produto(url: str) -> bool:
    url_l = url.lower()
    if "magazineluiza.com.br" not in url_l:
        return False
    if "/busca/" in url_l or "/departamentos/" in url_l or "/marcas/" in url_l:
        return False
    if any(x in url_l for x in ["/sacola", "/login", "/cadastro", "/atendimento", "/servicos"]):
        return False
    # Links de produto do Magalu costumam conter /p/<id>/...
    return "/p/" in url_l


async def coletar_links_resultados(page: Page) -> List[Dict[str, Any]]:
    """Coleta links de produtos na página de busca usando locators, sem page.evaluate."""
    await rolar_pagina(page, passos=5, pausa_ms=650)

    vistos = set()
    resultados: List[Dict[str, Any]] = []
    try:
        links = page.locator("a[href]")
        total = await links.count()
    except Exception:
        return resultados

    for i in range(min(total, 260)):
        try:
            a = links.nth(i)
            href = await a.get_attribute("href", timeout=900)
            if not href:
                continue
            url = limpar_url(href)
            if not url.startswith("http"):
                url = limpar_url(BASE_URL_MAGALU + href)
            if not _parece_link_produto(url) or url in vistos:
                continue

            texto_link = ""
            texto_card = ""
            try:
                texto_link = (await a.inner_text(timeout=900)).strip()
            except Exception:
                texto_link = ""

            # Tenta pegar o texto do card do produto.
            for xpath in [
                "xpath=ancestor::*[contains(@data-testid, 'product')][1]",
                "xpath=ancestor::li[1]",
                "xpath=ancestor::article[1]",
                "xpath=ancestor::div[1]",
                "xpath=ancestor::div[2]",
                "xpath=ancestor::div[3]",
            ]:
                try:
                    candidato = (await a.locator(xpath).inner_text(timeout=800)).strip()
                    if len(candidato) > len(texto_card):
                        texto_card = candidato
                except Exception:
                    continue

            titulo_attr = await a.get_attribute("title", timeout=600) or ""
            aria = await a.get_attribute("aria-label", timeout=600) or ""
            titulo = titulo_attr or aria or texto_link or (texto_card.splitlines()[0] if texto_card else "")
            titulo = re.sub(r"\s+", " ", titulo).strip()
            texto_card = re.sub(r"\s+", " ", texto_card or texto_link).strip()

            vistos.add(url)
            resultados.append({"url": url, "titulo_busca": titulo, "texto_card": texto_card})
        except Exception:
            continue

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
    await rolar_pagina(page, passos=6, pausa_ms=500)

    titulo = await _primeiro_texto(
        page,
        [
            "h1[data-testid*='heading']",
            "h1",
            "[data-testid='product-title']",
            "[class*='ProductTitle']",
            "[class*='product-title']",
        ],
    )
    if not titulo:
        titulo = await _meta_content(page, "meta[property='og:title']")
    if not titulo:
        titulo = card.get("titulo_busca", "")

    preco = await _primeiro_texto(
        page,
        [
            "[data-testid='price-value']",
            "[data-testid*='price']",
            "[class*='Price']",
            "[class*='price']",
            "p:has-text('R$')",
            "span:has-text('R$')",
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
        texto_pagina = await page.locator("body").inner_text(timeout=9000)
        texto_pagina = re.sub(r"\s+", " ", texto_pagina).strip()
    except Exception:
        texto_pagina = ""

    ficha = _extrair_ficha_tecnica(texto_pagina)
    detalhes = _extrair_trecho_detalhes(texto_pagina)
    vendedor = _extrair_vendedor(texto_pagina)
    avaliacao = _extrair_avaliacao(texto_pagina)

    return {
        "url": url,
        "url_canonica": limpar_url(url),
        "titulo": titulo,
        "preco": preco,
        "fornecedor": vendedor,
        "moq": "",
        "vendidos_pedidos": avaliacao,
        "imagem": imagem,
        "detalhes": detalhes,
        "ficha_tecnica": ficha,
        "texto_card": card.get("texto_card", ""),
        "texto_pagina": texto_pagina[:80000],
    }


def _extrair_trecho_detalhes(texto: str) -> str:
    if not texto:
        return ""
    marcadores = [
        "Informações do Produto", "Informacoes do Produto", "Descrição do Produto", "Descricao do Produto",
        "Características", "Caracteristicas", "Ficha Técnica", "Ficha Tecnica", "Dados do produto",
        "Especificações", "Especificacoes",
    ]
    lower = texto.lower()
    indices = [lower.find(m.lower()) for m in marcadores if lower.find(m.lower()) >= 0]
    if not indices:
        return texto[:5000]
    inicio = min(indices)
    return texto[inicio : inicio + 10000]


def _extrair_ficha_tecnica(texto: str) -> str:
    if not texto:
        return ""
    lower = texto.lower()
    marcadores_inicio = ["ficha técnica", "ficha tecnica", "características", "caracteristicas", "especificações", "especificacoes"]
    marcadores_fim = ["avaliações", "avaliacoes", "perguntas", "produtos relacionados", "quem viu", "também comprou"]
    inicios = [lower.find(m) for m in marcadores_inicio if lower.find(m) >= 0]
    if not inicios:
        return ""
    inicio = min(inicios)
    fim = len(texto)
    for m in marcadores_fim:
        idx = lower.find(m, inicio + 30)
        if idx >= 0:
            fim = min(fim, idx)
    return texto[inicio:min(fim, inicio + 12000)]


def _extrair_vendedor(texto: str) -> str:
    if not texto:
        return ""
    padroes = [
        r"Vendido\s+por\s+([^\|]{2,90})",
        r"Vendido\s+e\s+entregue\s+por\s+([^\|]{2,90})",
        r"Entregue\s+por\s+([^\|]{2,90})",
    ]
    for p in padroes:
        m = re.search(p, texto, re.IGNORECASE)
        if m:
            vendedor = re.sub(r"\s+", " ", m.group(1)).strip()
            vendedor = re.split(r"(?:Política|Politica|Adicionar|Comprar|R\$|Avalia)", vendedor)[0].strip()
            return vendedor[:120]
    return ""


def _extrair_avaliacao(texto: str) -> str:
    if not texto:
        return ""
    m = re.search(r"(\d+[\d\.,]*\s*(?:avaliaç(?:ão|ões)|avaliacoes|reviews?))", texto, re.IGNORECASE)
    return m.group(1).strip() if m else ""
