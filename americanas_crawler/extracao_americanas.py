# -*- coding: utf-8 -*-
"""Funções de extração para Americanas.com."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List
from urllib.parse import urljoin, urlparse, unquote

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError


BASE_URL = "https://www.americanas.com.br"

TERMOS_RELEVANTES_BUSCA = [
    "celular", "smartphone", "telefone", "phone", "mobile", "dual chip", "dual sim",
    "sim card", "gsm", "2g", "3g", "4g", "5g", "lte", "volte", "iphone",
    "samsung", "galaxy", "motorola", "moto ", "xiaomi", "redmi", "positivo",
    "nokia", "multilaser", "lg ", "lg-", "flip", "tijolinho", "feature phone",
    "mini celular", "mini phone", "bluetooth dialer", "ponto eletrônico",
    "l8star", "gtstar", "bm70", "bm30", "bm10", "bm50", "soyes", "melrose",
]

TERMOS_DESCARTE_OBVIO_BUSCA = [
    "chocolate", "amendoim", "amêndoa", "amendoas", "biscoito", "bolacha",
    "leite", "lacta", "garoto", "nestlé", "nestle", "café", "cafe",
    "açúcar", "acucar", "arroz", "feijão", "feijao", "macarrão", "macarrao",
    "molho", "tempero", "salgadinho", "suco", "refrigerante", "vinho",
    "cerveja", "ração", "racao", "shampoo", "condicionador", "sabonete",
    "fralda", "detergente", "desinfetante", "limpador", "desodorante",
    "perfume", "creme dental", "escova dental", "ração", "petisco",
]


def _texto_parece_produto_relevante(texto: str, url: str = "") -> bool:
    """
    Filtra candidatos da busca antes de abrir o anúncio.

    A Americanas mistura itens de mercado em algumas buscas por "mini".
    Aqui só entram links cujo card/URL indiquem celular/telefonia. Assim
    chocolate, amendoim, leite etc. não consomem o limite do crawler.
    """
    texto_base = _limpar_texto(f"{texto or ''} {url or ''}").lower()
    if not texto_base:
        return False

    tem_relevante = any(t in texto_base for t in TERMOS_RELEVANTES_BUSCA)
    tem_descarte = any(t in texto_base for t in TERMOS_DESCARTE_OBVIO_BUSCA)

    if tem_descarte and not tem_relevante:
        return False

    return tem_relevante

CEP_PADRAO = "72115145"


def _limpar_texto(txt: str | None) -> str:
    txt = txt or ""
    txt = txt.replace("\xa0", " ").replace("\u200b", " ")
    return re.sub(r"\s+", " ", txt).strip()


async def esperar_carregamento(page: Page, timeout_ms: int = 30000) -> None:
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        pass

    # A busca da Americanas pode renderizar os cards alguns segundos depois do DOM.
    try:
        await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 12000))
    except Exception:
        pass

    try:
        await page.wait_for_timeout(2200)
    except Exception:
        pass


async def _preencher_cep_popup(page: Page, cep: str = CEP_PADRAO) -> bool:
    """Preenche o popup de CEP quando ele aparecer."""
    try:
        await page.wait_for_timeout(500)
    except Exception:
        pass

    seletores_input = [
        "input[placeholder*='CEP' i]",
        "input[name*='cep' i]",
        "input[id*='cep' i]",
        "input[aria-label*='CEP' i]",
        "input[type='tel']",
        "input[type='text']",
    ]

    preenchido = False
    for sel in seletores_input:
        try:
            loc = page.locator(sel)
            total = await loc.count()
            for i in range(min(total, 8)):
                campo = loc.nth(i)
                try:
                    if not await campo.is_visible(timeout=600):
                        continue
                except Exception:
                    continue
                try:
                    await campo.click(timeout=900)
                    await campo.fill(cep, timeout=1200)
                    preenchido = True
                    break
                except Exception:
                    try:
                        await campo.click(timeout=900)
                        await campo.press("Control+A")
                        await campo.type(cep, delay=25)
                        preenchido = True
                        break
                    except Exception:
                        continue
            if preenchido:
                break
        except Exception:
            continue

    if not preenchido:
        return False

    # Clica no botão de confirmação/OK do popup.
    botoes_texto = [
        "OK", "Ok", "ok", "Confirmar", "confirmar", "Continuar", "continuar",
        "Aplicar", "aplicar", "Salvar", "salvar", "Ver ofertas", "ver ofertas",
        "Buscar", "buscar", "Enviar", "enviar",
    ]
    for texto in botoes_texto:
        try:
            btn = page.get_by_role("button", name=re.compile(rf"^{re.escape(texto)}$", re.IGNORECASE)).first
            if await btn.count() and await btn.is_visible(timeout=600):
                await btn.click(timeout=1200)
                await page.wait_for_timeout(1200)
                return True
        except Exception:
            pass
        try:
            btn = page.get_by_text(texto, exact=True).first
            if await btn.count() and await btn.is_visible(timeout=600):
                await btn.click(timeout=1200)
                await page.wait_for_timeout(1200)
                return True
        except Exception:
            pass

    # Fallback: pressiona Enter no campo preenchido.
    try:
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(1200)
        return True
    except Exception:
        return preenchido


async def fechar_popups_basicos(page: Page) -> None:
    # Primeiro tenta resolver o popup de CEP, pois ele pode bloquear cards e ficha técnica.
    await _preencher_cep_popup(page, CEP_PADRAO)

    textos = [
        "Aceitar", "Aceitar cookies", "Entendi", "Continuar", "Agora não", "Fechar", "OK", "ok",
        "Depois", "Pular",
    ]
    for texto in textos:
        try:
            loc = page.get_by_text(texto, exact=False).first
            if await loc.count():
                await loc.click(timeout=900)
                await page.wait_for_timeout(350)
        except Exception:
            pass
    seletores = [
        "button[aria-label='fechar']", "button[aria-label='Fechar']", "[data-testid*='close']",
        "[aria-label*='close']", "[aria-label*='Close']",
        "button:has-text('×')", "button:has-text('x')",
    ]
    for sel in seletores:
        try:
            loc = page.locator(sel).first
            if await loc.count():
                await loc.click(timeout=900)
        except Exception:
            pass


async def _scroll_busca(page: Page) -> None:
    try:
        await page.wait_for_timeout(900)
        for _ in range(7):
            await page.mouse.wheel(0, 1200)
            await page.wait_for_timeout(650)
        await page.mouse.wheel(0, -900)
        await page.wait_for_timeout(600)
    except Exception:
        pass


def _normalizar_url(url: str) -> str:
    url = (url or "").strip().strip('"').strip("'")
    url = url.replace("\\/", "/")
    url = unquote(url)
    url = url.split("#")[0]
    if url.startswith("//"):
        url = "https:" + url
    url = urljoin(BASE_URL, url)
    return url


def _url_produto_valida(url: str) -> bool:
    if not url:
        return False

    url = _normalizar_url(url)
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    path = parsed.path.lower().rstrip("/")

    if "americanas.com.br" not in netloc:
        return False

    # Evita páginas institucionais, categorias, login etc.
    bloqueios = [
        "/busca", "/s", "/categoria", "/hotsite", "/landingpage", "/login",
        "/checkout", "/especial", "/marca", "/favoritos", "/minha-conta",
        "/carrinho", "/atendimento", "/campanha", "/servicos",
    ]
    if any(path == b or path.startswith(b + "/") for b in bloqueios):
        return False

    # Formatos de produto da Americanas.
    # Exemplo comum atual: /nome-do-produto-4688139641/p
    # Também mantemos compatibilidade com /produto/... e /p/...
    if path.endswith("/p"):
        return True
    if "/produto/" in path or "/p/" in path or "/lojista/" in path:
        return True
    if re.search(r"/[^/]+-\d{6,}/p$", path):
        return True
    if re.search(r"/(?:[a-z0-9-]+/)*(?:produto|p)/?\d+", path):
        return True

    return False


async def _coletar_por_anchors(page: Page) -> List[Dict[str, Any]]:
    seletores = [
        "a[href$='/p']",
        "a[href*='/p?']",
        "a[href*='/produto/']",
        "a[href*='/p/']",
        "a[href*='americanas.com.br/produto']",
        "a[href*='americanas.com.br/'][href$='/p']",
        "a[href]",
    ]

    vistos: set[str] = set()
    itens: List[Dict[str, Any]] = []

    for sel in seletores:
        try:
            anchors = page.locator(sel)
            total = await anchors.count()
        except Exception:
            continue

        for i in range(min(total, 900)):
            try:
                a = anchors.nth(i)
                href = await a.get_attribute("href")
                if not href:
                    continue

                url = _normalizar_url(href)
                if not _url_produto_valida(url) or url in vistos:
                    continue

                texto = _limpar_texto(await a.inner_text(timeout=900))
                if len(texto) < 5:
                    texto = _limpar_texto(await a.get_attribute("title"))
                if len(texto) < 5:
                    try:
                        pai = a.locator("xpath=ancestor::*[self::li or self::article or self::div][1]").first
                        texto = _limpar_texto(await pai.inner_text(timeout=700))
                    except Exception:
                        pass

                if not _texto_parece_produto_relevante(texto, url):
                    continue

                vistos.add(url)
                itens.append({
                    "url": url,
                    "titulo_busca": texto[:500],
                    "texto_card": texto[:1800],
                })
            except Exception:
                continue

        if itens:
            break

    return itens


async def _coletar_por_dom_js(page: Page) -> List[Dict[str, Any]]:
    """
    Fallback: coleta hrefs e textos diretamente pelo DOM.
    Ajuda quando o Playwright locator não reconhece o card por seletor específico.
    """
    try:
        dados = await page.evaluate(
            """
            () => {
                const out = [];
                const anchors = Array.from(document.querySelectorAll('a[href]'));
                for (const a of anchors) {
                    const href = a.href || a.getAttribute('href') || '';
                    const card = a.closest('li, article, [data-testid], div');
                    const texto = ((card && card.innerText) || a.innerText || a.title || '').replace(/\\s+/g, ' ').trim();
                    out.push({href, texto});
                }
                return out;
            }
            """
        )
    except Exception:
        return []

    vistos: set[str] = set()
    itens: List[Dict[str, Any]] = []
    for item in dados or []:
        href = item.get("href", "")
        url = _normalizar_url(href)
        if not _url_produto_valida(url) or url in vistos:
            continue
        texto = _limpar_texto(item.get("texto", ""))
        if not _texto_parece_produto_relevante(texto, url):
            continue

        vistos.add(url)
        itens.append({
            "url": url,
            "titulo_busca": texto[:500],
            "texto_card": texto[:1800],
        })
    return itens


def _extrair_urls_de_html(html: str) -> List[str]:
    html = html or ""
    html2 = html.replace("\\/", "/")
    candidatos: List[str] = []

    padroes = [
        r"https?://(?:www\.)?americanas\.com\.br/[^\"'<>\\\s]+?/p(?:\?[^\"'<>\\\s]+)?",
        r"https?://(?:www\.)?americanas\.com\.br/produto/[^\"'<>\\\s]+",
        r"https?://(?:www\.)?americanas\.com\.br/p/[^\"'<>\\\s]+",
        r"//(?:www\.)?americanas\.com\.br/[^\"'<>\\\s]+?/p(?:\?[^\"'<>\\\s]+)?",
        r"//(?:www\.)?americanas\.com\.br/produto/[^\"'<>\\\s]+",
        r"//(?:www\.)?americanas\.com\.br/p/[^\"'<>\\\s]+",
        r"(?<![a-zA-Z])/(?:[a-z0-9-]+/)*[a-z0-9-]+-\d{6,}/p(?:\?[^\"'<>\\\s]+)?",
        r"(?<![a-zA-Z])/(?:produto|p)/[^\"'<>\\\s]+",
    ]
    for padrao in padroes:
        candidatos.extend(re.findall(padrao, html2, flags=re.IGNORECASE))

    # Links às vezes ficam escapados dentro de JSON.
    for m in re.finditer(r'"(?:url|href|productUrl|canonicalUrl)"\s*:\s*"([^"]+)"', html2, flags=re.IGNORECASE):
        candidatos.append(m.group(1))

    return [_normalizar_url(c) for c in candidatos]


async def _coletar_por_html_regex(page: Page) -> List[Dict[str, Any]]:
    try:
        html = await page.content()
    except Exception:
        return []

    vistos: set[str] = set()
    itens: List[Dict[str, Any]] = []

    for url in _extrair_urls_de_html(html):
        if not _url_produto_valida(url) or url in vistos:
            continue
        if not _texto_parece_produto_relevante("", url):
            continue

        vistos.add(url)
        itens.append({
            "url": url,
            "titulo_busca": "",
            "texto_card": "",
        })

    return itens


async def _coletar_por_texto_renderizado(page: Page) -> List[Dict[str, Any]]:
    """
    Último fallback: usa o texto renderizado e tenta procurar URLs copiadas no body.
    """
    try:
        texto = await page.locator("body").inner_text(timeout=2000)
    except Exception:
        return []

    vistos: set[str] = set()
    itens: List[Dict[str, Any]] = []

    for url in _extrair_urls_de_html(texto):
        if not _url_produto_valida(url) or url in vistos:
            continue
        if not _texto_parece_produto_relevante("", url):
            continue

        vistos.add(url)
        itens.append({
            "url": url,
            "titulo_busca": "",
            "texto_card": "",
        })
    return itens


async def coletar_links_resultados(page: Page) -> List[Dict[str, Any]]:
    await _scroll_busca(page)

    # Tenta aguardar qualquer indício de produto antes dos fallbacks.
    for sel in ["a[href*='/produto/']", "a[href*='/p/']", "[data-testid*='product']", "article", "li"]:
        try:
            await page.locator(sel).first.wait_for(timeout=3500)
            break
        except Exception:
            continue

    tentativas = [
        ("anchors", _coletar_por_anchors),
        ("dom", _coletar_por_dom_js),
        ("html", _coletar_por_html_regex),
        ("body", _coletar_por_texto_renderizado),
    ]

    vistos: set[str] = set()
    itens_finais: List[Dict[str, Any]] = []

    for _, func in tentativas:
        itens = await func(page)
        for item in itens:
            url = _normalizar_url(item.get("url", ""))
            if not _url_produto_valida(url) or url in vistos:
                continue
            vistos.add(url)
            item["url"] = url
            itens_finais.append(item)
        if itens_finais:
            break

    return itens_finais


async def _texto_primeiro(page: Page, seletores: List[str], timeout: int = 900) -> str:
    for sel in seletores:
        try:
            loc = page.locator(sel).first
            if await loc.count():
                texto = _limpar_texto(await loc.inner_text(timeout=timeout))
                if texto:
                    return texto
        except Exception:
            continue
    return ""


async def _atributo_primeiro(page: Page, seletores: List[str], atributo: str) -> str:
    for sel in seletores:
        try:
            loc = page.locator(sel).first
            if await loc.count():
                valor = await loc.get_attribute(atributo)
                if valor:
                    return valor.strip()
        except Exception:
            continue
    return ""


async def _extrair_json_ld(page: Page) -> Dict[str, Any]:
    dados: Dict[str, Any] = {}
    try:
        scripts = await page.locator("script[type='application/ld+json']").all()
        for script in scripts:
            try:
                raw = await script.text_content(timeout=700)
                if not raw:
                    continue
                obj = json.loads(raw)
                objs = obj if isinstance(obj, list) else [obj]
                for item in objs:
                    if not isinstance(item, dict):
                        continue
                    tipo = str(item.get("@type", "")).lower()
                    if "product" in tipo or item.get("name"):
                        if item.get("name") and not dados.get("name"):
                            dados["name"] = _limpar_texto(str(item.get("name")))
                        offers = item.get("offers")
                        if isinstance(offers, dict):
                            price = offers.get("price") or offers.get("lowPrice")
                            if price and not dados.get("price"):
                                dados["price"] = str(price)
                        if item.get("image") and not dados.get("image"):
                            img = item.get("image")
                            dados["image"] = img[0] if isinstance(img, list) and img else str(img)
            except Exception:
                continue
    except Exception:
        pass
    return dados


async def _extrair_blocos_informacao(page: Page) -> str:
    seletores = [
        "section", "article", "table", "dl", "ul",
        "[data-testid*='spec']", "[data-testid*='description']",
        "[data-testid*='product']", "[class*='spec']", "[class*='description']",
        "[class*='Descricao']", "[class*='Product']", "[class*='produto']",
    ]
    blocos: List[str] = []
    for sel in seletores:
        try:
            loc = page.locator(sel)
            total = await loc.count()
            for i in range(min(total, 60)):
                texto = _limpar_texto(await loc.nth(i).inner_text(timeout=700))
                low = texto.lower()
                if len(texto) > 30 and any(t in low for t in ["dimens", "altura", "largura", "comprimento", "tela", "chip", "sim", "gsm", "celular", "telefone", "anatel", "produto"]):
                    blocos.append(texto[:3000])
        except Exception:
            continue
    return " | ".join(dict.fromkeys(blocos))[:12000]


async def _expandir_informacoes_produto(page: Page) -> None:
    """Tenta abrir abas/botões de descrição, ficha técnica e características."""
    textos = [
        "Descrição", "Descrição do produto", "Ficha técnica", "Características", "Características do produto",
        "Especificações", "Informações do produto", "Mais informações", "Ver mais", "Mostrar mais",
        "Detalhes do produto", "Dados técnicos",
    ]
    for _ in range(2):
        for texto in textos:
            try:
                loc = page.get_by_text(texto, exact=False)
                total = await loc.count()
                for i in range(min(total, 4)):
                    item = loc.nth(i)
                    try:
                        if await item.is_visible(timeout=500):
                            await item.click(timeout=1000)
                            await page.wait_for_timeout(650)
                    except Exception:
                        continue
            except Exception:
                continue
        try:
            await page.mouse.wheel(0, 1200)
            await page.wait_for_timeout(500)
        except Exception:
            pass


async def _extrair_scripts_relevantes(page: Page) -> str:
    """Extrai trechos de scripts/JSON que contenham medidas ou dados técnicos."""
    partes: List[str] = []
    termos = ["dimens", "altura", "largura", "comprimento", "height", "width", "length", "depth"]
    try:
        scripts = await page.locator("script").all()
        for script in scripts[:80]:
            try:
                raw = await script.text_content(timeout=600)
            except Exception:
                continue
            if not raw:
                continue
            low = raw.lower()
            if not any(t in low for t in termos):
                continue
            raw = raw.replace("\\u002F", "/").replace("\\/", "/")
            raw = re.sub(r"\\u00a0|&nbsp;", " ", raw)
            raw = re.sub(r"\\n|\\r|\\t", " ", raw)
            raw = re.sub(r"\s+", " ", raw)
            # Mantém o trecho limitado para não poluir o parquet.
            for t in termos:
                pos = raw.lower().find(t)
                if pos >= 0:
                    ini = max(0, pos - 600)
                    fim = min(len(raw), pos + 1800)
                    partes.append(raw[ini:fim])
                    break
    except Exception:
        pass
    return " | ".join(dict.fromkeys(partes))[:12000]


async def extrair_produto(page: Page, url_produto: str, card: Dict[str, Any]) -> Dict[str, Any]:
    await esperar_carregamento(page)
    await fechar_popups_basicos(page)
    try:
        await page.mouse.wheel(0, 1100)
        await page.wait_for_timeout(900)
        await page.mouse.wheel(0, 1600)
        await page.wait_for_timeout(900)
    except Exception:
        pass
    await _expandir_informacoes_produto(page)
    await fechar_popups_basicos(page)

    jsonld = await _extrair_json_ld(page)
    titulo = await _texto_primeiro(page, [
        "h1", "[data-testid='product-title']", "[data-testid*='title']",
        "[class*='ProductTitle']", "[class*='product-title']", "meta[property='og:title']",
    ])
    if not titulo:
        titulo = _limpar_texto(await page.title())
    if not titulo:
        titulo = jsonld.get("name", "") or card.get("titulo_busca", "")

    preco = await _texto_primeiro(page, [
        "[data-testid='price-value']", "[data-testid*='price']", "[class*='price']", "[class*='Price']",
    ])
    if not preco and jsonld.get("price"):
        preco = f"R$ {jsonld.get('price')}"
    if not preco:
        try:
            body_txt = await page.locator("body").inner_text(timeout=1500)
            m = re.search(r"R\$\s?\d{1,3}(?:\.\d{3})*,\d{2}", body_txt)
            if m:
                preco = m.group(0)
        except Exception:
            pass

    imagem = await _atributo_primeiro(page, ["meta[property='og:image']"], "content")
    if not imagem:
        imagem = await _atributo_primeiro(page, ["img[data-testid*='image']", "img[src*='americanas']", "img[src]"], "src")
    if not imagem:
        imagem = jsonld.get("image", "")

    fornecedor = ""
    body_small = ""
    try:
        body_small = _limpar_texto((await page.locator("body").inner_text(timeout=2500))[:14000])
        m = re.search(r"(?:vendido por|vendida por|loja parceira|fornecedor)\s*:??\s*([^|\n\r]{3,90})", body_small, re.IGNORECASE)
        if m:
            fornecedor = _limpar_texto(m.group(1))
    except Exception:
        body_small = ""

    detalhes = await _extrair_blocos_informacao(page)
    scripts_relevantes = await _extrair_scripts_relevantes(page)
    if scripts_relevantes:
        detalhes = " | ".join([detalhes, scripts_relevantes]).strip(" | ")[:16000]
    ficha_tecnica = detalhes
    texto_pagina = body_small
    if not texto_pagina:
        try:
            texto_pagina = _limpar_texto(await page.locator("body").inner_text(timeout=3000))[:45000]
        except Exception:
            texto_pagina = ""

    if scripts_relevantes and scripts_relevantes not in texto_pagina:
        texto_pagina = " | ".join([texto_pagina, scripts_relevantes]).strip(" | ")[:45000]

    return {
        "titulo": titulo,
        "preco": preco,
        "fornecedor": fornecedor,
        "moq": "",
        "vendidos_pedidos": "",
        "url": url_produto,
        "url_canonica": page.url or url_produto,
        "imagem": imagem,
        "detalhes": detalhes,
        "ficha_tecnica": ficha_tecnica,
        "texto_card": card.get("texto_card", "") or card.get("titulo_busca", ""),
        "texto_pagina": texto_pagina,
    }
