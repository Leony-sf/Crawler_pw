from __future__ import annotations
import json
import re
from dataclasses import dataclass, asdict
from typing import Any
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from .base_anatel import BaseAnatel, normalizar_homologacao_base
from .utils import apenas_alnum, bloco, gerar_id, log, normalizar_chave, normalizar_texto, remover_acentos


LABELS_MODELO_VALIDAR = [
    "Modelo",
    "Modelo detalhado",
    "Modelo alfanumérico",
    "Modelo alfanumerico",
    "Número do modelo",
    "Numero do modelo",
]

LABELS_MODELO_IGNORAR = [
    "Modelo do processador",
    "Modelo de processador",
]

@dataclass
class DadosProduto:
    url: str = ""
    titulo: str = ""
    preco: str = ""
    codigo_anatel_principal: str = ""
    codigo_anatel_normalizado: str = ""
    marca: str = ""
    fabricante: str = ""
    modelo: str = ""
    modelo_detalhado: str = ""
    modelo_alfanumerico: str = ""
    numero_modelo: str = ""
    atributos_json: str = ""
    texto_relevante_mini: str = ""
    comentarios: list[str] | None = None


def _click_suave(page: Page, locator_textos: list[str], timeout_ms: int = 1500) -> bool:
    for texto in locator_textos:
        seletores = [
            f"button:has-text('{texto}')",
            f"a:has-text('{texto}')",
            f"span:has-text('{texto}')",
        ]
        for sel in seletores:
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible(timeout=400):
                    loc.scroll_into_view_if_needed(timeout=timeout_ms)
                    page.wait_for_timeout(250)
                    loc.click(timeout=timeout_ms)
                    page.wait_for_timeout(900)
                    return True
            except Exception:
                continue
    return False

def fechar_modais_leves(page: Page) -> None:
    textos = [
        "Aceitar cookies",
        "Entendi",
        "Mais tarde",
        "Agora não",
        "Depois",
        "Fechar",
    ]
    _click_suave(page, textos, timeout_ms=1000)

def expandir_ficha_tecnica(page: Page) -> bool:
    textos = [
        "Ver todas as características",
        "Ver todas as caracteristicas",
        "Ver características",
        "Ver caracteristicas",
        "Ver mais características",
        "Ver mais caracteristicas",
        "Ficha técnica",
        "Ficha tecnica",
    ]
    for y in [0, 700, 1400, 2200, 3200]:
        try:
            page.evaluate("window.scrollTo(0, arguments[0])", y)
            page.wait_for_timeout(350)
        except Exception:
            pass
        if _click_suave(page, textos, timeout_ms=1400):
            log("anatel ml", "Ficha técnica/características expandida.")
            return True
    return False

def _coletar_atributos(page: Page) -> dict[str, str]:
    script = r"""
    () => {
      const out = [];
      const seen = new Set();
      function clean(s) { return (s || '').replace(/\s+/g, ' ').trim(); }
      function push(label, value) {
        label = clean(label); value = clean(value);
        if (!label || !value || label === value) return;
        const key = `${label}=>${value}`;
        if (seen.has(key)) return;
        seen.add(key); out.push([label, value]);
      }
      for (const tr of document.querySelectorAll('tr')) {
        const cells = Array.from(tr.children).map(c => clean(c.innerText || c.textContent));
        if (cells.length >= 2) push(cells[0], cells.slice(1).join(' '));
      }
      const candidates = Array.from(document.querySelectorAll('div, li, section'));
      for (const el of candidates) {
        const children = Array.from(el.children).filter(c => clean(c.innerText || c.textContent));
        if (children.length === 2) {
          const a = clean(children[0].innerText || children[0].textContent);
          const b = clean(children[1].innerText || children[1].textContent);
          if (a.length <= 80 && b.length <= 220) push(a, b);
        }
      }
      return out.slice(0, 300);
    }
    """
    pares = []
    try:
        pares = page.evaluate(script) or []
    except Exception:
        pares = []
    attrs: dict[str, str] = {}
    for label, value in pares:
        label_limpo = normalizar_texto(label)
        value_limpo = normalizar_texto(value)
        if not label_limpo or not value_limpo:
            continue
        chave = normalizar_chave(label_limpo)
        if chave not in attrs or len(attrs[chave]) > len(value_limpo):
            attrs[chave] = value_limpo
    return attrs

def _valor_por_labels(attrs: dict[str, str], labels: list[str], excluir: list[str] | None = None) -> str:
    excluir_norm = [normalizar_chave(x) for x in (excluir or [])]
    labels_norm = [normalizar_chave(x) for x in labels]
    for chave, valor in attrs.items():
        if any(ex in chave for ex in excluir_norm):
            continue
        for label in labels_norm:
            if chave == label or chave.endswith(label) or label in chave:
                return valor
    return ""

def extrair_codigo_de_texto(texto: str) -> str:
    texto = normalizar_texto(texto)
    if not texto:
        return ""
    texto_norm = remover_acentos(texto)
    padroes = [
        r"(?i)(?:anatel|homologacao|homologado|certificacao|certificado|numero\s+de\s+homologacao|codigo\s+anatel)[^0-9]{0,180}((?:\d[\s.\-/]*){8,14})(?![\s.\-/]*\d)",
        r"(?i)((?:\d[\s.\-/]*){8,14})(?![\s.\-/]*\d)[^a-z0-9]{0,180}(?:anatel|homologacao|homologado|certificacao|certificado)",
    ]
    candidatos: list[str] = []
    for padrao in padroes:
        for m in re.finditer(padrao, texto_norm):
            dig = re.sub(r"\D", "", m.group(1) or "")
            if 8 <= len(dig) <= 14:
                candidatos.append(dig)
    for c in candidatos:
        if len(c) == 12:
            return c
    return candidatos[0] if candidatos else ""

def extrair_codigo_anatel(page: Page, attrs: dict[str, str]) -> str:
    for chave, valor in attrs.items():
        if any(p in chave for p in ["anatel", "homolog", "certific"]):
            codigo = extrair_codigo_de_texto(f"{chave} {valor}")
            if codigo:
                return codigo
    try:
        texto = page.locator("body").inner_text(timeout=3000)
    except Exception:
        texto = ""
    texto = normalizar_texto(texto)
    for termo in ["anatel", "homolog", "certific"]:
        for m in re.finditer(termo, texto, flags=re.IGNORECASE):
            ini = max(0, m.start() - 240)
            fim = min(len(texto), m.end() + 320)
            codigo = extrair_codigo_de_texto(texto[ini:fim])
            if codigo:
                return codigo
    return ""


# ============================================================
# MINI CELULARES / DIMENSÕES
# ============================================================

TERMOS_MINI_CELULAR = [
    "mini celular", "mini telefone", "mini phone", "celular pequeno",
    "telefone pequeno", "celular compacto", "telefone compacto",
    "celular chaveiro", "telefone chaveiro", "bluetooth dialer",
    "dual sim", "2 chips", "dois chips", "aceita chip", "chip sim",
    "cartao sim", "cartão sim",
]

TERMOS_PRODUTO_CELULAR = [
    "celular", "smartphone", "telefone", "phone", "dialer",
    "dual sim", "chip", "sim card", "cartao sim", "cartão sim",
    "galaxy", "iphone", "nokia", "motorola", "positivo",
    "multilaser", "alcatel", "doogee", "umidigi",
]

TERMOS_DESCARTAR_MINI = [
    "capinha", "capa para", "capa compatível", "capa compativel",
    "case para", "pelicula", "película", "carregador", "cabo usb",
    "cabo tipo c", "fonte", "fone de ouvido", "suporte", "tripé",
    "tripe", "bateria para", "display para", "tela para",
    "frontal para", "placa para", "conector para", "flex para",
    "slot para", "gaveta chip", "smartwatch", "relógio", "relogio",
    "tablet",
]

MARCAS_SUSPEITAS_MINI = [
    "l8star", "l8 star", "gtstar", "gt star", "zanco", "zanco tiny",
    "servo", "servo phone", "anica", "aizku", "kechaoda", "soyes",
    "melrose", "long-cz", "long cz",
]

MODELOS_SUSPEITOS_MINI = [
    "bm10", "bm20", "bm30", "bm50", "bm70", "bm90", "bm100", "bm200", "bm310",
    "bt11", "bt22", "b25", "b30", "j8", "j9", "j10", "k10", "k33", "k66",
    "soyes s10", "soyes xs", "soyes 7s", "melrose s9", "melrose s10",
    "long-cz j8", "long cz j8", "long-cz j9", "long cz j9",
]

TERMOS_FORMATO_DISFARCE_MINI = [
    "batom", "batonzinho", "caneta", "pen phone", "isqueiro", "lighter phone",
    "chaveiro", "chave de carro", "bmw", "porsche", "keyring phone",
    "cartao", "cartão", "card phone", "key phone", "tamanho de cartao", "tamanho de cartão",
]

TERMOS_INDICIO_TERMINAL_MOVEL = [
    "chip", "sim", "sim card", "cartao sim", "cartão sim", "gsm", "2g", "3g", "4g", "lte",
    "imei", "sms", "ligacao", "ligação", "chamada", "dual sim", "dois chips", "2 chips",
    "aceita chip", "bluetooth dialer", "dialer gsm", "phone companion",
]

MARCAS_CELULAR_CONHECIDAS = [
    "apple", "iphone", "samsung", "galaxy", "motorola", "moto", "xiaomi", "redmi", "poco",
    "nokia", "positivo", "multilaser", "multi", "alcatel", "doogee", "umidigi", "lg",
    "asus", "zenfone", "realme", "oppo", "vivo", "huawei", "honor", "infinix", "tcl",
]

_ROTULO_DIM_MAIOR = ["altura", "comprimento", "diametro", "diâmetro"]
_ROTULO_DIM_LARGURA = ["largura"]

def _numero_ptbr_para_float(valor: object) -> float | None:
    txt = normalizar_texto(valor).replace(" ", "")
    if not txt:
        return None
    if "," in txt:
        txt = txt.replace(".", "").replace(",", ".")
    try:
        return float(txt)
    except Exception:
        return None

def _converter_para_cm(valor: object, unidade: str | None) -> float | None:
    numero = _numero_ptbr_para_float(valor)
    if numero is None:
        return None
    unidade_norm = remover_acentos(unidade or "cm")
    if unidade_norm == "mm":
        return numero / 10.0
    return numero

def _fmt_cm(valor: float | None) -> str:
    if valor is None:
        return ""
    txt = f"{valor:.2f}".rstrip("0").rstrip(".")
    return txt.replace(".", ",")

def _janela_texto(texto: str, inicio: int, fim: int, margem: int = 90) -> str:
    ini = max(0, inicio - margem)
    fim = min(len(texto), fim + margem)
    return normalizar_texto(texto[ini:fim])

def _score_evidencia_dimensao(evidencia: object, maior_cm: float, largura_cm: float) -> tuple[int, float, float]:
    ev = remover_acentos(evidencia or "")
    prioridade = 3
    if "caracteristicas do produto" in ev or "ficha tecnica" in ev:
        prioridade = 0
    elif any(t in ev for t in ["dimens", "altura", "largura", "comprimento", "diametro", "tamanho"]):
        prioridade = 1
    elif any(t in ev for t in [" cm", "mm"]):
        prioridade = 2
    if any(t in ev for t in ["frete", "r$", "parcela", "mercado livre", "produtos relacionados"]):
        prioridade += 2
    return (prioridade, float(maior_cm), float(largura_cm))

def _coletar_texto_caracteristicas_produto(page: Page) -> str:
    script = r"""
    () => {
      const out = [];
      const seen = new Set();
      function clean(s) { return (s || '').replace(/\s+/g, ' ').trim(); }
      function push(s) {
        s = clean(s);
        if (!s || s.length < 20) return;
        if (s.length > 5000) s = s.slice(0, 5000);
        const key = s.toLowerCase();
        if (seen.has(key)) return;
        seen.add(key);
        out.push(s);
      }
      const tituloRegex = /caracter[ií]sticas do produto|caracter[ií]sticas principais|ficha t[eé]cnica|especifica[cç][oõ]es|detalhes do produto/i;
      const candidatos = Array.from(document.querySelectorAll('section, article, div, h2, h3, h4'));
      for (const el of candidatos) {
        const txt = clean(el.innerText || el.textContent || '');
        if (!tituloRegex.test(txt)) continue;
        let alvo = el.closest('section, article') || el;
        for (let i = 0; i < 4 && alvo; i++) {
          const bloco = clean(alvo.innerText || alvo.textContent || '');
          if (bloco.length >= 20 && bloco.length <= 5000) {
            push(bloco);
            break;
          }
          alvo = alvo.parentElement;
        }
      }
      for (const sel of [
        '.ui-pdp-highlighted-specs-res',
        '.ui-pdp-specs',
        '.ui-vpp-highlighted-specs',
        '.ui-pdp-container__row--technical-specifications',
        '[class*="highlighted-specs"]',
        '[class*="technical-specifications"]'
      ]) {
        for (const el of document.querySelectorAll(sel)) {
          push(el.innerText || el.textContent || '');
        }
      }
      return out.slice(0, 8).join(' | ');
    }
    """
    try:
        return normalizar_texto(page.evaluate(script) or "")
    except Exception:
        return ""

def _extrair_texto_relevante_mini(page: Page, attrs: dict[str, str], titulo: str) -> str:
    partes: list[str] = [normalizar_texto(titulo)]
    bloco_caracteristicas = _coletar_texto_caracteristicas_produto(page)
    if bloco_caracteristicas:
        partes.append(f"Características do produto: {bloco_caracteristicas}")
    for chave, valor in attrs.items():
        chave_norm = normalizar_chave(chave)
        if any(t in chave_norm for t in [
            "dimens", "tamanho", "altura", "largura", "comprimento", "diametro", "medida",
            "tela", "display", "formato", "peso"
        ]):
            partes.append(f"{chave}: {valor}")
    try:
        body = page.locator("body").inner_text(timeout=2500)
    except Exception:
        body = ""
    body_norm = normalizar_texto(body)
    body_sem_acento = remover_acentos(body_norm)
    termos = [
        "caracteristicas do produto", "ficha tecnica", "dimens", "tamanho", "altura", "largura",
        "comprimento", "diametro", "medida", " cm", " mm"
    ]
    trechos: list[str] = []
    for termo in termos:
        for m in re.finditer(re.escape(termo), body_sem_acento, flags=re.IGNORECASE):
            trecho = _janela_texto(body_norm, m.start(), m.end(), margem=220)
            if trecho and trecho not in trechos:
                trechos.append(trecho)
            if len(trechos) >= 10:
                break
        if len(trechos) >= 10:
            break
    partes.extend(trechos)
    return normalizar_texto(" | ".join(p for p in partes if p))[:7000]

def _extrair_dimensao_por_multiplicacao(texto: str) -> dict[str, Any] | None:
    padrao = re.compile(
        r"(?P<a>\d+(?:[\.,]\d+)?)\s*(?P<ua>cm|mm)?\s*(?:x| |por)\s*"
        r"(?P<b>\d+(?:[\.,]\d+)?)\s*(?P<ub>cm|mm)?"
        r"(?:\s*(?:x| |por)\s*(?P<c>\d+(?:[\.,]\d+)?)\s*(?P<uc>cm|mm)?)?",
        flags=re.IGNORECASE,
    )
    melhores: list[dict[str, Any]] = []
    for m in padrao.finditer(texto):
        unidades = [m.group("ua"), m.group("ub"), m.group("uc")]
        unidade_padrao = next((u for u in reversed(unidades) if u), "cm")
        valores: list[float] = []
        for nome_num, nome_un in [("a", "ua"), ("b", "ub"), ("c", "uc")]:
            bruto = m.group(nome_num)
            if not bruto:
                continue
            cm = _converter_para_cm(bruto, m.group(nome_un) or unidade_padrao)
            if cm is not None:
                valores.append(cm)
        if len(valores) < 2:
            continue
        if any(v <= 0 or v > 40 for v in valores):
            continue
        ordenados = sorted(valores, reverse=True)
        melhores.append(
            {
                "maior_cm": ordenados[0],
                "largura_cm": ordenados[1],
                "espessura_cm": ordenados[2] if len(ordenados) >= 3 else None,
                "evidencia": _janela_texto(texto, m.start(), m.end(), margem=55),
                "origem": "multiplicacao",
            }
        )
    if not melhores:
        return None
    melhores.sort(key=lambda d: _score_evidencia_dimensao(d.get("evidencia"), d["maior_cm"], d["largura_cm"]))
    return melhores[0]

def _normalizar_rotulo_dimensao(rotulo: str) -> str:
    r = normalizar_chave(rotulo)
    if any(t in r for t in ["altura", "comprimento", "diametro"]):
        return "maior"
    if "largura" in r:
        return "largura"
    return ""

def _extrair_dimensao_por_rotulos(texto: str) -> dict[str, Any] | None:
    rotulos = "altura|comprimento|diametro|diâmetro|largura"
    numero = r"\d+(?:[\.,]\d+)?"
    achados: list[dict[str, Any]] = []
    padroes = [
        re.compile(rf"(?P<label>{rotulos})\b(?P<gap>[^0-9]{{0,35}})(?P<num>{numero})\s*(?P<unit>cm|mm)?", flags=re.IGNORECASE),
        re.compile(rf"(?P<num>{numero})\s*(?P<unit>cm|mm)?\s*(?:de\s*)?(?P<label>{rotulos})\b", flags=re.IGNORECASE),
    ]
    for padrao in padroes:
        for m in padrao.finditer(texto):
            tipo = _normalizar_rotulo_dimensao(m.group("label"))
            if not tipo:
                continue
            grupos = m.groupdict()
            gap = grupos.get("gap") or ""
            if re.search(r"\be\b", remover_acentos(gap)):
                continue
            if "gap" not in grupos:
                antes = texto[max(0, m.start() - 40):m.start()]
                if re.search(r"(altura|comprimento|diametro|diâmetro|largura)\b\s*[:=\-]?\s*$", antes, flags=re.IGNORECASE):
                    continue
            achados.append(
                {
                    "tipo": tipo,
                    "num": m.group("num"),
                    "unit": m.group("unit"),
                    "start": m.start(),
                    "end": m.end(),
                }
            )
    if not achados:
        return None
    unidade_padrao = next((a["unit"] for a in achados if a.get("unit")), None)
    if not unidade_padrao:
        return None
    maior_vals: list[float] = []
    largura_vals: list[float] = []
    ini = min(a["start"] for a in achados)
    fim = max(a["end"] for a in achados)
    for a in achados:
        cm = _converter_para_cm(a["num"], a.get("unit") or unidade_padrao)
        if cm is None or cm <= 0 or cm > 40:
            continue
        if a["tipo"] == "maior":
            maior_vals.append(cm)
        elif a["tipo"] == "largura":
            largura_vals.append(cm)
    if not maior_vals or not largura_vals:
        return None
    maior = min(maior_vals)
    largura = min(largura_vals)
    if largura > maior:
        maior, largura = largura, maior
    return {
        "maior_cm": maior,
        "largura_cm": largura,
        "espessura_cm": None,
        "evidencia": _janela_texto(texto, ini, fim, margem=75),
        "origem": "rotulos",
    }

def extrair_dimensoes_mini_celular(texto: str) -> dict[str, Any] | None:
    texto = normalizar_texto(texto)
    if not texto:
        return None
    candidatos = [
        _extrair_dimensao_por_multiplicacao(texto),
        _extrair_dimensao_por_rotulos(texto),
    ]
    candidatos = [c for c in candidatos if c]
    if not candidatos:
        return None
    candidatos.sort(key=lambda d: _score_evidencia_dimensao(d.get("evidencia"), d["maior_cm"], d["largura_cm"]))
    return candidatos[0]

def _termo_presente(texto_norm: str, termo: str) -> bool:
    termo_norm = remover_acentos(termo)
    if not termo_norm:
        return False
    padrao = r"(?<![a-z0-9])" + re.escape(termo_norm) + r"(?![a-z0-9])"
    return re.search(padrao, texto_norm, flags=re.IGNORECASE) is not None

def _qualquer_termo_presente(texto_norm: str, termos: list[str]) -> bool:
    return any(_termo_presente(texto_norm, termo) for termo in termos)

def _primeiro_termo_presente(texto_norm: str, termos: list[str]) -> str:
    return next((termo for termo in termos if _termo_presente(texto_norm, termo)), "")

def _normalizar_marca_para_suspeito(valor: object) -> str:
    return remover_acentos(valor or "")

def _marca_desconhecida_ou_generica(marca: str) -> bool:
    marca_norm = _normalizar_marca_para_suspeito(marca)
    if not marca_norm:
        return True
    genericos = [
        "generico", "generica", "sem marca", "marca generica", "marca nao informada",
        "nao informado", "nao informada", "outro", "outros", "importado", "unbranded",
    ]
    if any(g in marca_norm for g in genericos):
        return True
    return not _qualquer_termo_presente(marca_norm, MARCAS_CELULAR_CONHECIDAS)

def _base_retorno_mini(maior_max_cm: float, largura_max_cm: float) -> dict[str, Any]:
    return {
        "mini_suspeito_manual": "NAO",
        "mini_suspeito_tipo": "",
        "mini_suspeito_motivo": "",
        "mini_limite_maior_cm": maior_max_cm,
        "mini_limite_largura_cm": largura_max_cm,
    }

def _retorno_suspeito_manual(
    maior_max_cm: float, largura_max_cm: float, tipo: str, motivo: str, evidencia: str = ""
) -> dict[str, Any]:
    return {
        "mini_status": "SUSPEITO_MANUAL",
        "mini_motivo": f"Separado para análise manual: {motivo}",
        "mini_maior_cm": None,
        "mini_largura_cm": None,
        "mini_espessura_cm": None,
        "mini_evidencia": normalizar_texto(evidencia)[:900],
        "mini_fonte_dimensao": "",
        "mini_suspeito_manual": "SIM",
        "mini_suspeito_tipo": tipo,
        "mini_suspeito_motivo": motivo,
        "mini_limite_maior_cm": maior_max_cm,
        "mini_limite_largura_cm": largura_max_cm,
    }

def _avaliar_indicios_suspeitos_mini(
    dados: DadosProduto, attrs_txt: str, texto_identificacao_norm: str, texto_total_norm: str
) -> dict[str, str]:
    termo_marca = _primeiro_termo_presente(texto_total_norm, MARCAS_SUSPEITAS_MINI)
    termo_modelo = _primeiro_termo_presente(texto_total_norm, MODELOS_SUSPEITOS_MINI)
    termo_disfarce = _primeiro_termo_presente(texto_total_norm, TERMOS_FORMATO_DISFARCE_MINI)
    termo_terminal = _primeiro_termo_presente(texto_total_norm, TERMOS_INDICIO_TERMINAL_MOVEL)
    
    if termo_modelo:
        return {
            "tipo": "MODELO_SUSPEITO",
            "motivo": f"modelo associado a mini phone encontrado: {termo_modelo}",
        }
    if termo_marca:
        return {
            "tipo": "MARCA_SUSPEITA",
            "motivo": f"marca associada a mini phone encontrada: {termo_marca}",
        }
    if termo_disfarce and termo_terminal:
        return {
            "tipo": "FORMATO_DISFARCADO",
            "motivo": f"formato/disfarce '{termo_disfarce}' com indício de terminal móvel '{termo_terminal}'",
        }
    marca = normalizar_texto(dados.marca)
    if _marca_desconhecida_ou_generica(marca) and termo_terminal and _qualquer_termo_presente(texto_identificacao_norm, TERMOS_PRODUTO_CELULAR + TERMOS_MINI_CELULAR):
        return {
            "tipo": "MARCA_DESCONHECIDA",
            "motivo": f"marca ausente/desconhecida com indício técnico de celular: {termo_terminal}",
        }
    return {"tipo": "", "motivo": ""}

def _segmentos_dimensoes_prioritarios(dados: DadosProduto, attrs_txt: str) -> list[str]:
    saida: list[str] = []
    vistos: set[str] = set()
    def add(txt: object) -> None:
        txt_norm = normalizar_texto(txt)
        if not txt_norm: return
        chave = remover_acentos(txt_norm)
        if chave in vistos: return
        vistos.add(chave)
        saida.append(txt_norm)
        
    texto_relevante = normalizar_texto(dados.texto_relevante_mini)
    partes_relevantes = [normalizar_texto(p) for p in re.split(r"\s+\|\s+", texto_relevante) if normalizar_texto(p)]
    marcadores_prioridade = [
        "caracteristicas do produto", "caracteristicas principais", "ficha tecnica",
        "especificacoes", "detalhes do produto", "tamanho da tela", "dimens",
        "altura", "largura", "comprimento", "diametro",
    ]
    for parte in partes_relevantes:
        parte_norm = remover_acentos(parte)
        if any(m in parte_norm for m in marcadores_prioridade):
            add(parte)
            
    try:
        attrs = json.loads(dados.atributos_json or "{}")
    except Exception:
        attrs = {}
    if isinstance(attrs, dict):
        for chave, valor in attrs.items():
            chave_norm = normalizar_chave(chave)
            if any(t in chave_norm for t in ["dimens", "tamanho", "altura", "largura", "comprimento", "diametro", "medida"]):
                add(f"{chave}: {valor}")
                
    add(texto_relevante)
    add(dados.titulo)
    return saida

def _extrair_dimensoes_por_prioridade(dados: DadosProduto, attrs_txt: str) -> dict[str, Any] | None:
    for fonte in _segmentos_dimensoes_prioritarios(dados, attrs_txt):
        dim = extrair_dimensoes_mini_celular(fonte)
        if dim:
            dim = dict(dim)
            dim["fonte_prioridade"] = fonte[:350]
            return dim
    return None

def analisar_mini_celular(
    dados: DadosProduto,
    maior_max_cm: float = 8.5,
    largura_max_cm: float = 5.5,
) -> dict[str, Any]:
    """Classifica o anúncio dentro do recorte de mini celulares.
    - Acessórios vão direto para o lixo.
    - Disfarces (chaveiros, etc) com indício de celular viram MANTER imediatamente.
    """
    attrs_txt = ""
    try:
        attrs = json.loads(dados.atributos_json or "{}")
        attrs_txt = " ".join(f"{k}: {v}" for k, v in attrs.items())
    except Exception:
        attrs_txt = dados.atributos_json or ""

    texto_titulo = normalizar_texto(dados.titulo)
    texto_titulo_norm = remover_acentos(texto_titulo)
    
    texto_identificacao_restrita = normalizar_texto(" | ".join([
        dados.titulo, dados.marca, dados.fabricante, dados.modelo,
        dados.modelo_detalhado, dados.modelo_alfanumerico, dados.numero_modelo,
    ]))
    texto_identificacao_norm = remover_acentos(texto_identificacao_restrita)
    
    texto_total_norm = remover_acentos(" | ".join([
        texto_identificacao_restrita, attrs_txt, dados.texto_relevante_mini,
    ]))
    
    extras_base = _base_retorno_mini(maior_max_cm, largura_max_cm)
    
    suspeito = _avaliar_indicios_suspeitos_mini(
        dados=dados,
        attrs_txt=attrs_txt,
        texto_identificacao_norm=texto_identificacao_norm,
        texto_total_norm=texto_total_norm,
    )
    
    termo_descartar = next((t for t in TERMOS_DESCARTAR_MINI if _termo_presente(texto_titulo_norm, t)), "")
    termo_terminal = _primeiro_termo_presente(texto_total_norm, TERMOS_INDICIO_TERMINAL_MOVEL)
    
    # 1. DESCARTA ACESSÓRIOS SEM PIEDADE
    if termo_descartar:
        return {
            **extras_base,
            "mini_status": "DESCARTAR_ACESSORIO",
            "mini_motivo": f"Produto é acessório/peça: {termo_descartar}",
            "mini_maior_cm": None,
            "mini_largura_cm": None,
            "mini_espessura_cm": None,
            "mini_evidencia": "",
            "mini_fonte_dimensao": "",
        }

    # 2. SE FOR DISFARCE E TIVER SINAL DE CELULAR, É ALVO COM CERTEZA (MANTER)
    if suspeito.get("tipo") in ["FORMATO_DISFARCADO", "MODELO_SUSPEITO", "MARCA_SUSPEITA"]:
        return {
            **extras_base,
            "mini_status": "MANTER",
            "mini_motivo": f"Alvo criminoso detectado por formato disfarçado, marca ou modelo sujo: {suspeito.get('motivo')}",
            "mini_maior_cm": 0.0,
            "mini_largura_cm": 0.0,
            "mini_espessura_cm": 0.0,
            "mini_evidencia": texto_identificacao_restrita[:900],
            "mini_fonte_dimensao": "Regra de Disfarce Forçada",
            "mini_suspeito_manual": "SIM",
            "mini_suspeito_tipo": suspeito.get("tipo"),
            "mini_suspeito_motivo": suspeito.get("motivo"),
        }

    parece_mini = _qualquer_termo_presente(texto_identificacao_norm, TERMOS_MINI_CELULAR)
    parece_celular = parece_mini or _qualquer_termo_presente(texto_identificacao_norm, TERMOS_PRODUTO_CELULAR)
    
    if not parece_celular:
        return {
            **extras_base,
            "mini_status": "DESCARTAR_NAO_CELULAR",
            "mini_motivo": "Anúncio não possui indício textual suficiente de celular/telefone",
            "mini_maior_cm": None,
            "mini_largura_cm": None,
            "mini_espessura_cm": None,
            "mini_evidencia": "",
            "mini_fonte_dimensao": "",
        }

    dimensoes = _extrair_dimensoes_por_prioridade(dados, attrs_txt)
    
    if not dimensoes:
        if suspeito.get("tipo"):
            return _retorno_suspeito_manual(
                maior_max_cm, largura_max_cm,
                tipo=suspeito.get("tipo") or "SUSPEITO_SEM_MEDIDA",
                motivo=(suspeito.get("motivo") or "parece mini celular") + "; sem dimensão",
                evidencia=texto_identificacao_restrita or texto_titulo,
            )
        return {
            **extras_base,
            "mini_status": "REVISAR_SEM_MEDIDA" if parece_mini else "DESCARTAR_SEM_MEDIDA",
            "mini_motivo": "Parece mini celular, mas não encontrei medida explícita" if parece_mini else "Sem medida explícita",
            "mini_maior_cm": None,
            "mini_largura_cm": None,
            "mini_espessura_cm": None,
            "mini_evidencia": "",
            "mini_fonte_dimensao": "",
        }
        
    maior = float(dimensoes.get("maior_cm") or 0)
    largura = float(dimensoes.get("largura_cm") or 0)
    espessura = dimensoes.get("espessura_cm")
    evidencia = dimensoes.get("evidencia") or ""
    
    if maior <= float(maior_max_cm) and largura <= float(largura_max_cm):
        status = "MANTER"
        motivo = f"Dentro do limite: maior eixo {_fmt_cm(maior)} cm <= {_fmt_cm(maior_max_cm)} cm e largura {_fmt_cm(largura)} cm <= {_fmt_cm(largura_max_cm)} cm"
    else:
        status = "DESCARTAR_MEDIDA"
        motivo = f"Fora do limite: maior eixo {_fmt_cm(maior)} cm / largura {_fmt_cm(largura)} cm"
        
    extras_suspeito: dict[str, Any] = {}
    if status == "MANTER" and suspeito.get("tipo"):
        extras_suspeito = {
            "mini_suspeito_manual": "SIM",
            "mini_suspeito_tipo": suspeito.get("tipo") or "SUSPEITO",
            "mini_suspeito_motivo": suspeito.get("motivo") or "produto mantido, mas com indício suspeito",
        }
        
    return {
        **extras_base,
        **extras_suspeito,
        "mini_status": status,
        "mini_motivo": motivo,
        "mini_maior_cm": maior,
        "mini_largura_cm": largura,
        "mini_espessura_cm": float(espessura) if espessura is not None else None,
        "mini_evidencia": evidencia,
        "mini_fonte_dimensao": dimensoes.get("fonte_prioridade", ""),
    }

def capturar_comentarios(page: Page, limite: int = 10) -> list[str]:
    bloco("comentários")
    log("comentários", f"Tentando capturar até {limite} comentários.")
    comentarios: list[str] = []
    textos_botao = [
        "Ver todas as opiniões",
        "Ver opiniões",
        "Opiniões",
        "Ver avaliações",
        "Avaliações",
    ]
    _click_suave(page, textos_botao, timeout_ms=1200)
    try:
        page.wait_for_timeout(1000)
    except Exception:
        pass
    seletores = [
        ".ui-review-capability-comments__comment__content",
        ".ui-review-capability-comments__comment__content p",
        ".ui-review-capability__comment",
        ".ui-review-capability-comments__comment",
        "[data-testid*='comment']",
    ]
    for _ in range(10):
        for sel in seletores:
            try:
                for txt in page.locator(sel).all_inner_texts():
                    txt = normalizar_texto(txt)
                    if len(txt) >= 3 and txt not in comentarios:
                        comentarios.append(txt)
                    if len(comentarios) >= limite:
                        break
            except Exception:
                pass
            if len(comentarios) >= limite:
                break
        if len(comentarios) >= limite:
            break
        try:
            page.mouse.wheel(0, 900)
            page.wait_for_timeout(450)
        except Exception:
            break
    log("comentários", f"Comentários capturados: {len(comentarios[:limite])}")
    return comentarios[:limite]

def extrair_produto(page: Page, capturar_reviews: bool = True) -> DadosProduto:
    fechar_modais_leves(page)
    expandir_ficha_tecnica(page)
    try:
        titulo = page.locator("h1, .ui-pdp-title").first.inner_text(timeout=6000)
    except Exception:
        titulo = ""
    try:
        preco = page.locator(".andes-money-amount__fraction, .price-tag-fraction").first.inner_text(timeout=1500)
    except Exception:
        preco = ""
    attrs = _coletar_atributos(page)
    marca = _valor_por_labels(attrs, ["Marca"])
    fabricante = _valor_por_labels(attrs, ["Fabricante"])
    modelo = _valor_por_labels(attrs, ["Modelo"], excluir=LABELS_MODELO_IGNORAR + ["Modelo detalhado", "Modelo alfanumérico", "Modelo alfanumerico"])
    modelo_detalhado = _valor_por_labels(attrs, ["Modelo detalhado"])
    modelo_alfanumerico = _valor_por_labels(attrs, ["Modelo alfanumérico", "Modelo alfanumerico"])
    numero_modelo = _valor_por_labels(attrs, ["Número do modelo", "Numero do modelo"])
    codigo = extrair_codigo_anatel(page, attrs)
    codigo_norm = normalizar_homologacao_base(codigo) if codigo else ""
    texto_relevante_mini = _extrair_texto_relevante_mini(page, attrs, titulo)
    comentarios = capturar_comentarios(page, limite=10) if capturar_reviews else []
    return DadosProduto(
        url=page.url,
        titulo=normalizar_texto(titulo),
        preco=normalizar_texto(preco),
        codigo_anatel_principal=codigo,
        codigo_anatel_normalizado=codigo_norm,
        marca=normalizar_texto(marca),
        fabricante=normalizar_texto(fabricante),
        modelo=normalizar_texto(modelo),
        modelo_detalhado=normalizar_texto(modelo_detalhado),
        modelo_alfanumerico=normalizar_texto(modelo_alfanumerico),
        numero_modelo=normalizar_texto(numero_modelo),
        atributos_json=json.dumps(attrs, ensure_ascii=False),
        texto_relevante_mini=texto_relevante_mini,
        comentarios=comentarios,
    )

def _alias_marca(marca: str) -> set[str]:
    m = remover_acentos(marca)
    tokens = set(re.findall(r"[a-z0-9]+", m))
    aliases = set(tokens)
    joined = " ".join(tokens)
    regras = {
        "xiaomi": ["xiaomi", "redmi", "poco", "mi"],
        "apple": ["apple", "iphone", "ipad", "airpods", "macbook"],
        "samsung": ["samsung", "galaxy"],
        "motorola": ["motorola", "moto"],
        "oppo": ["oppo"],
        "realme": ["realme"],
        "asus": ["asus", "rog", "zenfone"],
        "doogee": ["doogee"],
        "umidigi": ["umidigi"],
        "infinix": ["infinix"],
        "honor": ["honor"],
        "huawei": ["huawei"],
        "nokia": ["nokia"],
        "positivo": ["positivo"],
        "multilaser": ["multilaser", "multi"],
        "tcl": ["tcl"],
    }
    for canon, vals in regras.items():
        if any(v in tokens or v in joined for v in vals):
            aliases.add(canon)
            aliases.update(vals)
    return {a for a in aliases if len(a) >= 2}

def marca_compativel(marca_capturada: str, fabricante_base: str) -> bool:
    marca_capturada = normalizar_texto(marca_capturada)
    fabricante_base = normalizar_texto(fabricante_base)
    if not marca_capturada or not fabricante_base:
        return False
    aliases = _alias_marca(marca_capturada)
    fab_norm = remover_acentos(fabricante_base)
    fab_tokens = set(re.findall(r"[a-z0-9]+", fab_norm))
    for alias in aliases:
        if alias in fab_tokens or alias in fab_norm:
            return True
    return False

def _normalizar_modelo_comparacao(valor: str) -> str:
    return apenas_alnum(valor)

def _partes_modelo_no_campo(valor: str) -> list[str]:
    txt = normalizar_texto(valor)
    if not txt:
        return []
    partes = re.split(
        r"\s*(?:,|;|\||\s+\+\s+|\s+e\s+|\s+ou\s+)\s*",
        txt,
        flags=re.IGNORECASE,
    )
    saida: list[str] = []
    vistos: set[str] = set()
    for parte in partes:
        parte = normalizar_texto(parte)
        chave = _normalizar_modelo_comparacao(parte)
        if len(chave) < 3:
            continue
        if chave not in vistos:
            vistos.add(chave)
            saida.append(parte)
    return saida

def modelo_compativel(modelo_capturado: str, modelo_base: str) -> bool:
    a = _normalizar_modelo_comparacao(modelo_capturado)
    b = _normalizar_modelo_comparacao(modelo_base)
    if not a or not b:
        return False
    return a == b

def _modelos_capturados(dados: DadosProduto) -> dict[str, str]:
    modelos = {
        "Modelo": dados.modelo,
        "Modelo detalhado": dados.modelo_detalhado,
        "Modelo alfanumérico": dados.modelo_alfanumerico,
        "Número do modelo": dados.numero_modelo,
    }
    return {k: normalizar_texto(v) for k, v in modelos.items() if normalizar_texto(v)}

def _modelo_decisivo_capturado(dados: DadosProduto) -> tuple[str, str]:
    prioridade = [
        ("Modelo alfanumérico", dados.modelo_alfanumerico),
        ("Modelo detalhado", dados.modelo_detalhado),
        ("Modelo", dados.modelo),
    ]
    for label, valor in prioridade:
        valor_norm = normalizar_texto(valor)
        if valor_norm:
            return label, valor_norm
    return "", ""


def validar_produto(dados: DadosProduto, base: BaseAnatel | None) -> dict[str, Any]:
    """Valida APENAS código e marca contra a base ANATEL.
    Regras atuais:
    - sem código ANATEL => IRREGULAR;
    - código fora da base e sem prefixo válido => IRREGULAR;
    - marca capturada divergente da base => IRREGULAR;
    (A validação de modelo foi removida a pedido do usuário).
    """
    motivos_irreg: list[str] = []
    avisos: list[str] = []
    
    codigo = dados.codigo_anatel_normalizado or normalizar_homologacao_base(dados.codigo_anatel_principal)
    
    bloco("anatel")
    if not codigo:
        motivos_irreg.append("Código ANATEL não encontrado")
        log("anatel", "Código capturado: não encontrado")
    else:
        log("anatel", f"Código capturado: {dados.codigo_anatel_principal}")
        log("anatel", f"Código normalizado: {codigo}")
        
    if not codigo:
        status = "IRREGULAR"
        return _resultado_validacao(status, motivos_irreg, avisos, modo_base="sem_codigo")
        
    if base is None:
        avisos.append("Código ANATEL capturado, mas nenhuma base foi informada")
        return _resultado_validacao("SEM_BASE", motivos_irreg, avisos, modo_base="sem_base")
        
    modo, candidatos = base.candidatos_para_codigo(codigo)
    pref = codigo[: base.prefix_len]
    
    bloco("base")
    log("base", f"Código exato no CSV: {'SIM' if modo == 'exato' else 'NÃO'}")
    log("base", f"Prefixo {pref} no CSV: {'SIM' if modo in ['exato', 'prefixo'] else 'NÃO'}")
    
    if modo == "nenhum" or candidatos.empty:
        motivos_irreg.append(f"Código ANATEL {codigo} não existe na base nem por prefixo {base.prefix_len}")
        return _resultado_validacao("IRREGULAR", motivos_irreg, avisos, modo_base="nenhum")
        
    if modo == "prefixo":
        avisos.append(f"Código sem match exato, mas prefixo {pref} existe na base")
        
    # Marca capturada x fabricante/marca da base.
    bloco("marca x base")
    if dados.marca:
        fabricantes = [normalizar_texto(v) for v in candidatos.get("fabricante_base", []).tolist() if normalizar_texto(v)]
        if fabricantes:
            ok_marca = any(marca_compativel(dados.marca, fab) for fab in fabricantes)
            log("marca x base", f"Marca capturada: {dados.marca}")
            log("marca x base", f"Fabricantes candidatos: {', '.join(fabricantes[:5])}")
            if not ok_marca:
                motivos_irreg.append(
                    f"Marca '{dados.marca}' diverge da base para o código/prefixo. Base encontrada: {', '.join(fabricantes[:5])}"
                )
        else:
            avisos.append("Base não possui fabricante para validar marca")
    else:
        avisos.append("Marca não capturada no anúncio")
        
    # Validação de modelo removida - se a marca e o código baterem, é REGULAR.
    status = "IRREGULAR" if motivos_irreg else "REGULAR"
    return _resultado_validacao(status, motivos_irreg, avisos, modo_base=modo)


def _resultado_validacao(status: str, motivos_irreg: list[str], avisos: list[str], modo_base: str) -> dict[str, Any]:
    motivos = motivos_irreg + avisos
    bloco("resultado")
    log("resultado", f"Situação final: {status}")
    if motivos_irreg:
        log("resultado", "Irregularidades:")
        for m in motivos_irreg:
            print(f"- {m}")
    if avisos:
        log("resultado", "Avisos:")
        for a in avisos:
            print(f"- {a}")
    return {
        "status_validacao": status,
        "motivo_validacao": "; ".join(motivos),
        "irregularity_reasons": "; ".join(motivos_irreg),
        "warnings": "; ".join(avisos),
        "modo_match_base": modo_base,
    }


def dados_para_linha(dados: DadosProduto, validacao: dict[str, Any]) -> dict[str, Any]:
    status = validacao.get("status_validacao", "")
    pid = gerar_id(dados.titulo, dados.marca, dados.codigo_anatel_normalizado, dados.url)
    modelos = _modelos_capturados(dados)
    modelo_decisivo_label, modelo_decisivo_valor = _modelo_decisivo_capturado(dados)
    
    linha = {
        "pid": pid,
        "marketplace_id": "2",
        "name": dados.titulo,
        "titulo": dados.titulo,
        "link": dados.url,
        "url": dados.url,
        "anatel_number": dados.codigo_anatel_normalizado,
        "codigo_anatel_principal": dados.codigo_anatel_normalizado,
        "brand": dados.marca,
        "marca": dados.marca,
        "price": dados.preco,
        "preco": dados.preco,
        "reviewers": "",
        "status": "Irregular" if status == "IRREGULAR" else ("Regular" if status == "REGULAR" else status),
        "status_validacao": status,
        "irregularity_reasons": validacao.get("irregularity_reasons", ""),
        "motivo_validacao": validacao.get("motivo_validacao", ""),
        "warnings": validacao.get("warnings", ""),
        "created_at": "",
        "modelo": dados.modelo,
        "modelo_detalhado": dados.modelo_detalhado,
        "modelo_alfanumerico": dados.modelo_alfanumerico,
        "numero_modelo": dados.numero_modelo,
        "modelo_decisivo_label": modelo_decisivo_label,
        "modelo_decisivo": modelo_decisivo_valor,
        "modelo_decisivo_partes_json": json.dumps(_partes_modelo_no_campo(modelo_decisivo_valor), ensure_ascii=False),
        "modelos_capturados_json": json.dumps(modelos, ensure_ascii=False),
        "fabricante": dados.fabricante,
        "modo_match_base": validacao.get("modo_match_base", ""),
    }
    return linha