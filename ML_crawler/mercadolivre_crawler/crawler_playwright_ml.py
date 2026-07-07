from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus
import time
from typing import Any

import pandas as pd
from playwright.sync_api import sync_playwright, Page, BrowserContext

from .base_anatel import BaseAnatel
from .extracao import (
    analisar_mini_celular,
    capturar_comentarios,
    dados_para_linha,
    extrair_produto,
    fechar_modais_leves,
    validar_produto,
)
from .utils import arquivo_seguro, bloco, criar_pastas_saida, gerar_id, log, secao


# ============================================================
# URL / INÍCIO
# ============================================================

def _url_busca(query: str) -> str:
    termo = quote_plus(query or "celular").replace("+", "-")
    return f"https://lista.mercadolivre.com.br/{termo}"


def _inicio_lento(page: Page, query: str, url: str | None) -> None:
    """Abertura mais calma para reduzir modal/fluxo de login/conta."""
    page.goto(
        "https://www.mercadolivre.com.br/",
        wait_until="domcontentloaded",
        timeout=45000,
    )
    page.wait_for_timeout(2500)
    fechar_modais_leves(page)
    _fechar_cookies_se_aparecer(page)
    page.wait_for_timeout(1200)

    destino = url or _url_busca(query)
    log("busca", f"Abrindo listagem: {destino}")

    page.goto(destino, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(3500)
    fechar_modais_leves(page)
    _fechar_cookies_se_aparecer(page)

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    page.wait_for_timeout(1500)


# ============================================================
# LISTAGEM / LINKS
# ============================================================

def _coletar_links_produtos(page: Page, max_scrolls: int = 16, alvo_minimo: int = 35) -> list[str]:
    """
    Coleta links da listagem com rolagem progressiva e controlada.

    Pontos importantes:
    - não para ao encontrar poucos links;
    - não captura links de reviews/questions;
    - não captura links de paginação;
    - não depende de fallback _Desde_.
    """
    script = r"""
    () => {
      const out = new Set();
      const anchors = Array.from(document.querySelectorAll('a[href]'));

      for (const a of anchors) {
        const href = (a.href || '').split('#')[0].trim();
        if (!href) continue;
        if (!href.includes('mercadolivre.com.br')) continue;
        if (href.includes('/questions') || href.includes('/reviews')) continue;

        const texto = [a.innerText, a.textContent, a.getAttribute('title'), a.getAttribute('aria-label')]
          .join(' ')
          .replace(/\s+/g, ' ')
          .trim()
          .toLowerCase();

        const pareceProduto = href.includes('/p/')
          || /\/MLB-?\d+/i.test(href)
          || /\bMLB\d+\b/i.test(href);

        const parecePaginacao = texto.includes('seguinte')
          || texto.includes('próxima')
          || texto.includes('proxima')
          || texto.includes('siguiente')
          || texto.includes('next')
          || href.includes('_Desde_');

        if (pareceProduto && !parecePaginacao) {
          out.add(href);
        }
      }

      return Array.from(out);
    }
    """

    links: list[str] = []
    sem_novos = 0
    ultima_qtd = 0

    try:
        page.evaluate("() => window.scrollTo(0, 0)")
        page.wait_for_timeout(600)
    except Exception:
        pass

    for tentativa in range(1, max_scrolls + 1):
        try:
            novos = page.evaluate(script) or []
            for href in novos:
                href = str(href or "").split("#")[0].strip()
                if href and href not in links:
                    links.append(href)
        except Exception:
            pass

        log("listagem", f"Coleta {tentativa}/{max_scrolls}: {len(links)} links de produto")

        if len(links) >= alvo_minimo and len(links) == ultima_qtd:
            break

        if len(links) == ultima_qtd:
            sem_novos += 1
        else:
            sem_novos = 0
            ultima_qtd = len(links)

        if sem_novos >= 4:
            break

        try:
            page.mouse.wheel(0, 950)
            page.wait_for_timeout(650)
        except Exception:
            break

    return links


# ============================================================
# PAGINAÇÃO
# ============================================================

def _fechar_cookies_se_aparecer(page: Page) -> None:
    """Fecha banner de cookies se ele estiver atrapalhando a paginação."""
    candidatos = [
        "Aceitar cookies",
        "Aceitar todos",
        "Entendi",
        "Concordo",
    ]

    for texto in candidatos:
        try:
            botao = page.get_by_role("button", name=texto, exact=False).first
            if botao.count() and botao.is_visible(timeout=800):
                botao.click(timeout=1500)
                page.wait_for_timeout(700)
                log("cookies", f"Banner fechado com: {texto}")
                return
        except Exception:
            pass


def _clicar_seguinte_visivel(page: Page, url_antes: str) -> bool:
    """Tenta clicar no botão/link real 'Seguinte' quando ele está no DOM."""
    seletores_seguinte = [
        "li.andes-pagination__button--next a",
        "li.andes-pagination__button--next button",
        "a.andes-pagination__link:has-text('Seguinte')",
        "a:has-text('Seguinte')",
        "button:has-text('Seguinte')",
        "a[title*='Seguinte']",
        "a[aria-label*='Seguinte']",
        "[class*='pagination'] a:has-text('Seguinte')",
        "[class*='pagination'] button:has-text('Seguinte')",
        "a:has-text('Próxima')",
        "a:has-text('Proxima')",
        "a:has-text('Siguiente')",
    ]

    for seletor in seletores_seguinte:
        try:
            loc = page.locator(seletor)
            total = loc.count()
        except Exception:
            total = 0

        for i in range(total):
            try:
                item = loc.nth(i)

                if not item.is_visible(timeout=800):
                    continue

                classe = " ".join(
                    [
                        item.get_attribute("class") or "",
                        item.evaluate("el => el.parentElement ? el.parentElement.className || '' : ''"),
                    ]
                ).lower()

                aria_disabled = (item.get_attribute("aria-disabled") or "").lower()
                href = (item.get_attribute("href") or "").strip()

                if "disabled" in classe or aria_disabled == "true":
                    log("paginação", "Botão 'Seguinte' encontrado, mas está desabilitado.")
                    return False

                item.scroll_into_view_if_needed(timeout=3000)
                page.wait_for_timeout(500)

                log("paginação", f"Botão 'Seguinte' encontrado pelo seletor: {seletor}")

                try:
                    item.click(timeout=4000)
                except Exception:
                    handle = item.element_handle()
                    if handle:
                        page.evaluate("(el) => el.click()", handle)
                    else:
                        raise

                try:
                    page.wait_for_url(lambda url: str(url) != str(url_antes), timeout=20000)
                except Exception:
                    if href:
                        log("paginação", "Clique não mudou URL rapidamente. Abrindo href diretamente.")
                        page.goto(href, wait_until="domcontentloaded", timeout=45000)

                try:
                    page.wait_for_load_state("domcontentloaded", timeout=20000)
                except Exception:
                    pass

                try:
                    page.wait_for_load_state("networkidle", timeout=12000)
                except Exception:
                    pass

                page.wait_for_timeout(2500)
                fechar_modais_leves(page)
                _fechar_cookies_se_aparecer(page)

                mudou = page.url.split("#")[0].rstrip("/") != str(url_antes or "").split("#")[0].rstrip("/")

                if mudou:
                    log("paginação", f"Próxima página carregada: {page.url}")
                    return True

            except Exception:
                continue

    return False


def _ir_proxima_pagina(page: Page, pagina_atual: int | None = None) -> bool:
    """
    Vai para a próxima página clicando no botão real 'Seguinte'.

    Esta versão NÃO monta URL com _Desde_ e NÃO faz rolagem agressiva até o fim absoluto.
    Ela desce gradualmente até a paginação exibida pelo Mercado Livre e clica no botão real.
    """
    bloco("paginação")

    if pagina_atual is not None:
        log("paginação", f"Procurando botão 'Seguinte' após finalizar a página {pagina_atual}.")
    else:
        log("paginação", "Procurando botão 'Seguinte' da paginação.")

    _fechar_cookies_se_aparecer(page)
    url_antes = page.url

    # Primeiro tenta sem rolar, caso a página já esteja perto da paginação.
    if _clicar_seguinte_visivel(page, url_antes):
        return True

    # Desce gradualmente. O botão fica antes de 'Produtos relacionados'.
    for tentativa in range(1, 13):
        log("paginação", f"Descendo para localizar paginação. Tentativa {tentativa}/12")

        try:
            page.mouse.wheel(0, 850)
        except Exception:
            try:
                page.evaluate("() => window.scrollBy(0, 850)")
            except Exception:
                pass

        page.wait_for_timeout(750)
        _fechar_cookies_se_aparecer(page)

        if _clicar_seguinte_visivel(page, url_antes):
            return True

    log("paginação", "Não encontrei o botão 'Seguinte'. Encerrando paginação.")
    return False


# ============================================================
# ARQUIVOS / PARQUET / PRINTS
# ============================================================

MINI_COLUNAS_NUMERICAS = [
    "mini_maior_cm",
    "mini_largura_cm",
    "mini_espessura_cm",
    "mini_limite_maior_cm",
    "mini_limite_largura_cm",
]


def _preparar_dataframe_parquet(linhas: list[dict[str, Any]]) -> pd.DataFrame:
    """Garante tipos estáveis antes de salvar em Parquet.

    O PyArrow quebra quando uma mesma coluna mistura float/int com string vazia.
    Por isso, colunas mini_*_cm são sempre numéricas e as demais são texto.
    """
    df = pd.DataFrame(linhas)
    if df.empty:
        return df

    for col in MINI_COLUNAS_NUMERICAS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].replace("", None), errors="coerce").astype("float64")

    for col in df.columns:
        if col not in MINI_COLUNAS_NUMERICAS:
            df[col] = df[col].where(pd.notna(df[col]), "").astype(str)

    return df


def _salvar_print(page: Page, saida_base: Path, linha: dict[str, Any]) -> None:
    pid = linha.get("pid") or gerar_id(linha.get("titulo"), linha.get("url"))
    status = str(linha.get("status_validacao") or linha.get("status") or "").upper()
    pasta = "irregulares" if status == "IRREGULAR" else "regulares"
    nome = arquivo_seguro(f"{pid}_{linha.get('titulo', 'produto')}", 100)
    caminho = saida_base / "prints" / pasta / f"{nome}.png"

    try:
        page.screenshot(path=str(caminho), full_page=True)
        log("arquivos", f"Print salvo em: {caminho}")
    except Exception as exc:
        log("arquivos", f"Falha ao salvar print: {exc}")


def _salvar_resultados(
    saida: Path,
    linhas: list[dict[str, Any]],
    comentarios: list[dict[str, Any]],
    descartados_mini: list[dict[str, Any]] | None = None,
    suspeitos_mini: list[dict[str, Any]] | None = None,
) -> None:
    """Salva apenas Parquet. Não gera CSV e não gera pasta HTML."""
    df = _preparar_dataframe_parquet(linhas)
    df.to_parquet(saida / "products.parquet", index=False)
    df.to_parquet(saida / "resultados.parquet", index=False)

    dfc = _preparar_dataframe_parquet(comentarios)
    dfc.to_parquet(saida / "comments.parquet", index=False)

    if descartados_mini is not None:
        dfd = _preparar_dataframe_parquet(descartados_mini)
        dfd.to_parquet(saida / "products_descartados_mini.parquet", index=False)

    if suspeitos_mini is not None:
        dfs = _preparar_dataframe_parquet(suspeitos_mini)
        dfs.to_parquet(saida / "products_suspeitos_mini.parquet", index=False)


# ============================================================
# CONTEXTO / NAVEGADOR
# ============================================================

def _abrir_contexto_chrome_persistente(p, headless: bool = False) -> BrowserContext:
    profile_dir = Path("chrome_profiles") / "mercadolivre_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    return p.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=headless,
        viewport={"width": 1366, "height": 900},
        locale="pt-BR",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        args=[
            "--start-maximized",
            "--disable-blink-features=AutomationControlled",
        ],
        slow_mo=140,
    )


def _clicar_ver_mais_resultados_se_existir(page: Page) -> None:
    candidatos = [
        "Ver mais resultados",
        "Mostrar mais resultados",
        "Ver mais",
        "Mais resultados",
    ]

    for texto in candidatos:
        try:
            loc = page.get_by_text(texto, exact=False).first

            if loc.count() and loc.is_visible(timeout=1200):
                loc.scroll_into_view_if_needed(timeout=2500)
                page.wait_for_timeout(800)
                loc.click(timeout=3000)
                page.wait_for_load_state("domcontentloaded", timeout=20000)

                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass

                page.wait_for_timeout(2000)
                log("listagem", f"Cliquei em: {texto}")
                return

        except Exception:
            continue

    log("listagem", "Botão 'Ver mais resultados' não apareceu.")


def _sem_limite(valor: int | None) -> bool:
    try:
        return int(valor or 0) <= 0
    except Exception:
        return True


# ============================================================
# FLUXO PRINCIPAL
# ============================================================

def _conectar_chrome_real_ml(p) -> BrowserContext:
    """
    Conecta o Playwright em um Chrome real já aberto com:
    --remote-debugging-port=9225
    """
    log("chrome", "Conectando ao Chrome real na porta 9225...")

    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9225")

    if browser.contexts:
        context = browser.contexts[0]
    else:
        context = browser.new_context(
            viewport={"width": 1366, "height": 900},
            locale="pt-BR",
        )

    log("chrome", "Conectado ao Chrome real com sucesso.")
    return context

def _pausa_manual_login_ml(page: Page) -> None:
    secao("Pausa manual Mercado Livre")
    log("login", "Se o Mercado Livre pediu login/criar conta, resolva manualmente no navegador.")
    log("login", "Quando estiver na tela correta da busca/listagem de celulares, volte aqui no terminal.")
    input("[login] Pressione ENTER para iniciar o crawler... ")

    try:
        page.wait_for_load_state("domcontentloaded", timeout=20000)
    except Exception:
        pass

    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass

    page.wait_for_timeout(1500)
    fechar_modais_leves(page)
    _fechar_cookies_se_aparecer(page)

    log("login", f"Continuando execução na URL atual: {page.url}")


def rodar_playwright_mercadolivre(
    query: str = "smartphone",
    queries: list[str] | None = None,
    limite: int = 5,
    base_anatel: BaseAnatel | None = None,
    headless: bool = False,
    url: str | None = None,
    saida: str | Path | None = None,
    max_paginas: int = 0,
    mini_celulares: bool = False,
    mini_maior_cm: float = 8.5,
    mini_largura_cm: float = 5.5,
    mini_manter_sem_medida: bool = False,
) -> dict[str, Any]:
    """
    Fluxo Mercado Livre no padrão da Shopee.

    max_paginas <= 0 significa sem limite de páginas: roda até não existir próxima página.
    limite <= 0 significa sem limite de produtos: processa enquanto houver páginas/produtos.
    """
    saida_base = criar_pastas_saida(saida)
    linhas: list[dict[str, Any]] = []
    comentarios_linhas: list[dict[str, Any]] = []
    descartados_mini: list[dict[str, Any]] = []
    suspeitos_mini: list[dict[str, Any]] = []

    if url:
        consultas_busca = [(query or "URL direta", url)]
    else:
        consultas_raw = queries or [query]
        consultas_busca = []
        vistos_consultas: set[str] = set()
        for q in consultas_raw:
            q = str(q or "").strip()
            if not q:
                continue
            chave = q.lower()
            if chave in vistos_consultas:
                continue
            vistos_consultas.add(chave)
            consultas_busca.append((q, _url_busca(q)))
        if not consultas_busca:
            consultas_busca = [("celular", _url_busca("celular"))]

    url_busca = consultas_busca[0][1]
    urls_processadas: set[str] = set()
    total_processados = 0

    sem_limite_produtos = _sem_limite(limite)
    sem_limite_paginas = _sem_limite(max_paginas)
    limite_txt = "sem limite" if sem_limite_produtos else str(limite)
    max_paginas_txt = "sem limite" if sem_limite_paginas else str(max_paginas)

    secao("Mercado Livre Playwright")
    log("crawler", f"URL inicial: {url_busca}")
    log("crawler", f"Total de buscas: {len(consultas_busca)}")
    log("crawler", f"Limite total de produtos: {limite_txt}")
    log("crawler", f"Máximo de páginas: {max_paginas_txt}")
    if mini_celulares:
        log("mini celular", "Modo mini celular ativado")
        log("mini celular", f"Limite dimensional: maior eixo <= {mini_maior_cm} cm e largura <= {mini_largura_cm} cm")
        log("mini celular", f"Sem medida explícita: {'manter para revisão' if mini_manter_sem_medida else 'descartar da planilha principal'}")
    log("crawler", f"Saída: {saida_base.resolve()}")

    with sync_playwright() as p:
        context = _conectar_chrome_real_ml(p)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(12000)
        page.set_default_navigation_timeout(45000)

        try:
            _inicio_lento(page, query=consultas_busca[0][0], url=consultas_busca[0][1])

            secao("Pausa manual Mercado Livre")
            log("login", "Use o Chrome real aberto para resolver login/captcha se necessário.")
            log("login", "Deixe o navegador exatamente na listagem de celulares.")
            input("[login] Quando estiver pronto, pressione ENTER para iniciar a coleta... ")

            fechar_modais_leves(page)
            _fechar_cookies_se_aparecer(page)
            _clicar_ver_mais_resultados_se_existir(page)


            for consulta_indice, (consulta_query, consulta_url) in enumerate(consultas_busca, start=1):
                if not sem_limite_produtos and total_processados >= int(limite):
                    log("busca", f"Limite total atingido antes da próxima busca: {total_processados}/{limite}.")
                    break

                secao(f"BUSCA {consulta_indice}/{len(consultas_busca)}")
                log("busca", f"Termo atual: {consulta_query}")
                log("busca", f"URL da busca: {consulta_url}")

                if consulta_indice > 1:
                    page.goto(consulta_url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(2500)
                    try:
                        page.wait_for_load_state("networkidle", timeout=12000)
                    except Exception:
                        pass
                    fechar_modais_leves(page)
                    _fechar_cookies_se_aparecer(page)
                    _clicar_ver_mais_resultados_se_existir(page)

                pagina_atual = 1
                paginas_sem_links_novos = 0

                while True:
                    if not sem_limite_produtos and total_processados >= int(limite):
                        log("busca", f"Limite total atingido: {total_processados}/{limite}.")
                        break

                    if not sem_limite_paginas and pagina_atual > int(max_paginas):
                        log("paginação", f"Máximo de páginas atingido: {max_paginas}.")
                        break

                    secao(f"PÁGINA {pagina_atual}")
                    bloco("listagem")
                    log("listagem", f"URL atual: {page.url}")
                    log("listagem", "Coletando links dos produtos da página atual.")

                    links_pagina = _coletar_links_produtos(page)

                    try:
                        page.evaluate("() => window.scrollTo(0, 0)")
                        page.wait_for_timeout(500)
                    except Exception:
                        pass

                    links_novos: list[str] = []
                    vistos_pagina: set[str] = set()

                    for href in links_pagina:
                        href_limpo = str(href or "").split("#")[0].strip()

                        if not href_limpo:
                            continue

                        if href_limpo in vistos_pagina:
                            continue

                        if href_limpo in urls_processadas:
                            continue

                        vistos_pagina.add(href_limpo)
                        links_novos.append(href_limpo)

                    log("listagem", f"Links capturados: {len(links_pagina)}")
                    log("listagem", f"Links novos para processar: {len(links_novos)}")

                    if not links_novos:
                        paginas_sem_links_novos += 1
                        bloco("paginação")
                        log(
                            "paginação",
                            f"Nenhum produto novo nesta página. Ocorrências seguidas: {paginas_sem_links_novos}/3",
                        )

                        if paginas_sem_links_novos >= 3:
                            log("paginação", "Três páginas seguidas sem links novos. Encerrando para evitar loop.")
                            break

                        if not _ir_proxima_pagina(page, pagina_atual=pagina_atual):
                            log("paginação", "Não há próxima página disponível. Encerrando.")
                            break

                        pagina_atual += 1
                        continue

                    paginas_sem_links_novos = 0

                    for indice_pagina, href in enumerate(links_novos, start=1):
                        if not sem_limite_produtos and total_processados >= int(limite):
                            log("busca", f"Limite total atingido: {total_processados}/{limite}.")
                            break

                        urls_processadas.add(href)
                        total_processados += 1

                        secao(f"PÁGINA {pagina_atual} | PRODUTO {indice_pagina}/{len(links_novos)}")
                        bloco("navegação")
                        log("navegação", f"Produto geral {total_processados}/{limite_txt}")
                        log("navegação", f"Abrindo anúncio: {href}")

                        prod_page = context.new_page()
                        prod_page.set_default_timeout(12000)
                        prod_page.set_default_navigation_timeout(45000)

                        try:
                            prod_page.goto(href, wait_until="domcontentloaded", timeout=45000)
                            prod_page.wait_for_timeout(2200)

                            try:
                                prod_page.wait_for_load_state("networkidle", timeout=10000)
                            except Exception:
                                pass

                            dados = extrair_produto(prod_page, capturar_reviews=not mini_celulares)

                            mini_info: dict[str, Any] = {}
                            if mini_celulares:
                                mini_info = analisar_mini_celular(
                                    dados,
                                    maior_max_cm=mini_maior_cm,
                                    largura_max_cm=mini_largura_cm,
                                )

                                mini_status = str(mini_info.get("mini_status") or "")
                                manter_por_medida = mini_status == "MANTER"
                                manter_sem_medida = mini_manter_sem_medida and mini_status == "REVISAR_SEM_MEDIDA"
                                eh_suspeito_manual = mini_status == "SUSPEITO_MANUAL" or str(mini_info.get("mini_suspeito_manual") or "").upper() == "SIM"

                                bloco("mini celular")
                                log("mini celular", f"Status: {mini_status or 'não classificado'}")
                                log("mini celular", f"Motivo: {mini_info.get('mini_motivo') or 'sem motivo'}")
                                if eh_suspeito_manual:
                                    log("mini celular", f"Suspeito manual: {mini_info.get('mini_suspeito_tipo') or 'SIM'} - {mini_info.get('mini_suspeito_motivo') or mini_info.get('mini_motivo') or ''}")
                                if mini_info.get("mini_evidencia"):
                                    log("mini celular", f"Evidência: {mini_info.get('mini_evidencia')}")

                                if not (manter_por_medida or manter_sem_medida):
                                    destino_suspeito = eh_suspeito_manual
                                    linha_destino = dados_para_linha(
                                        dados,
                                        {
                                            "status_validacao": "SUSPEITO_MANUAL" if destino_suspeito else "FORA_ESCOPO_MINI",
                                            "motivo_validacao": mini_info.get("mini_motivo", "Fora do recorte de mini celular"),
                                            "irregularity_reasons": "",
                                            "warnings": mini_info.get("mini_motivo", ""),
                                            "modo_match_base": "mini_suspeito_manual" if destino_suspeito else "mini_descartado",
                                        },
                                    )
                                    linha_destino.update(mini_info)
                                    linha_destino["created_at"] = time.strftime("%Y-%m-%d")
                                    linha_destino["query_busca"] = consulta_query
                                    if destino_suspeito:
                                        suspeitos_mini.append(linha_destino)
                                    else:
                                        descartados_mini.append(linha_destino)
                                    _salvar_resultados(saida_base, linhas, comentarios_linhas, descartados_mini, suspeitos_mini)
                                    continue

                                dados.comentarios = capturar_comentarios(prod_page, limite=10)

                            validacao = validar_produto(dados, base_anatel)
                            linha_produto = dados_para_linha(dados, validacao)
                            if mini_info:
                                linha_produto.update(mini_info)
                            linha_produto["created_at"] = time.strftime("%Y-%m-%d")
                            linha_produto["query_busca"] = consulta_query
                            linhas.append(linha_produto)

                            if mini_celulares and str(linha_produto.get("mini_suspeito_manual") or "").upper() == "SIM":
                                suspeitos_mini.append(dict(linha_produto))

                            for i, comentario in enumerate(dados.comentarios or [], start=1):
                                comentarios_linhas.append(
                                    {
                                        "pid": linha_produto["pid"],
                                        "marketplace_id": "2",
                                        "url": linha_produto["url"],
                                        "comentario_ordem": i,
                                        "comment": comentario,
                                        "created_at": linha_produto["created_at"],
                                        "query_busca": consulta_query,
                                    }
                                )

                            bloco("produto")
                            log("produto", f"Nome: {linha_produto.get('name') or linha_produto.get('titulo') or 'não encontrado'}")
                            log("anatel", f"Código: {linha_produto.get('anatel_number') or linha_produto.get('codigo_anatel_principal') or 'não encontrado'}")
                            log("marca", f"Marca: {linha_produto.get('brand') or linha_produto.get('marca') or 'não encontrada'}")
                            log("modelo", f"Modelo: {linha_produto.get('modelo_decisivo') or linha_produto.get('model') or linha_produto.get('modelo') or 'não encontrado'}")
                            log("resultado", f"Situação: {linha_produto.get('status') or linha_produto.get('status_validacao')}")

                            motivo = linha_produto.get("irregularity_reasons") or linha_produto.get("motivo_validacao") or ""
                            if motivo:
                                log("motivo", motivo)

                            bloco("arquivos")
                            _salvar_print(prod_page, saida_base, linha_produto)
                            _salvar_resultados(saida_base, linhas, comentarios_linhas, descartados_mini, suspeitos_mini)

                        except Exception as exc:
                            bloco("erro")
                            log("erro", f"Falha ao processar produto: {type(exc).__name__}: {exc}")

                            linhas.append(
                                {
                                    "pid": gerar_id(href),
                                    "marketplace_id": "2",
                                    "name": "",
                                    "titulo": "",
                                    "link": href,
                                    "url": href,
                                    "status": "ERRO",
                                    "status_validacao": "ERRO",
                                    "motivo_validacao": f"Falha ao processar: {type(exc).__name__}: {exc}",
                                    "irregularity_reasons": f"Falha ao processar: {type(exc).__name__}: {exc}",
                                    "created_at": time.strftime("%Y-%m-%d"),
                                    "query_busca": consulta_query,
                                }
                            )
                            _salvar_resultados(saida_base, linhas, comentarios_linhas, descartados_mini, suspeitos_mini)

                        finally:
                            try:
                                prod_page.close()
                            except Exception:
                                pass
    
                            bloco("navegação")
                            log("navegação", f"Produto geral {total_processados}/{limite_txt} finalizado.")

                if not sem_limite_produtos and total_processados >= int(limite):
                    log("busca", f"Limite total atingido: {total_processados}/{limite}.")
                    break

                if not sem_limite_paginas and pagina_atual >= int(max_paginas):
                    log("paginação", f"Máximo de páginas atingido: {pagina_atual}/{max_paginas}.")
                    break

                bloco("paginação")
                log("paginação", "Produtos da página finalizados. Tentando avançar para a próxima página.")

                if not _ir_proxima_pagina(page, pagina_atual=pagina_atual):
                    log("paginação", "Não encontrei próxima página. Encerrando.")
                    break

                pagina_atual += 1

        finally:
            try:
                context.close()
            except Exception:
                pass

    _salvar_resultados(saida_base, linhas, comentarios_linhas, descartados_mini, suspeitos_mini)

    resumo = {
        "saida": str(saida_base.resolve()),
        "total_produtos": len(linhas),
        "total_comentarios": len(comentarios_linhas),
        "regulares": sum(
            1
            for l in linhas
            if str(l.get("status_validacao") or l.get("status")).upper() == "REGULAR"
        ),
        "irregulares": sum(
            1
            for l in linhas
            if str(l.get("status_validacao") or l.get("status")).upper() == "IRREGULAR"
        ),
        "erros": sum(
            1
            for l in linhas
            if str(l.get("status_validacao") or l.get("status")).upper() == "ERRO"
        ),
        "mini_modo": "ativado" if mini_celulares else "desativado",
        "mini_mantidos": sum(1 for l in linhas if str(l.get("mini_status") or "") == "MANTER"),
        "mini_revisar_sem_medida": sum(1 for l in linhas if str(l.get("mini_status") or "") == "REVISAR_SEM_MEDIDA"),
        "mini_descartados": len(descartados_mini),
        "mini_suspeitos_manual": len(suspeitos_mini),
        "paginas_maximas": max_paginas_txt,
        "buscas_total": len(consultas_busca),
        "buscas": [q for q, _ in consultas_busca],
        "urls_processadas": len(urls_processadas),
        "products_parquet": str((saida_base / "products.parquet").resolve()),
        "comments_parquet": str((saida_base / "comments.parquet").resolve()),
        "products_descartados_mini_parquet": str((saida_base / "products_descartados_mini.parquet").resolve()) if mini_celulares else "",
        "products_suspeitos_mini_parquet": str((saida_base / "products_suspeitos_mini.parquet").resolve()) if mini_celulares else "",
    }

    secao("Resumo Playwright")
    for chave, valor in resumo.items():
        log("resumo", f"{chave}: {valor}")

    return resumo
