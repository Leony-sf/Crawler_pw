# -*- coding: utf-8 -*-
"""
Regras de classificação para o crawler Alibaba.com.

Regra operacional atual:
- classificar como IRREGULAR apenas anúncio de celular/telefone com tela
  igual ou inferior a 3 polegadas;
- celular com tela acima de 3 e até 3,5 polegadas fica como SUSPEITO;
- celular com tela maior que 3,5 polegadas é DESCARTADO;
- celular em que a tela não foi localizada fica como REVISAR, separado em
  parquet/pasta própria para análise manual;
- acessórios/peças/brinquedos sem indício real de telefonia são descartados.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


LIMITE_TELA_IRREGULAR_POLEGADAS = 3.0
LIMITE_TELA_SUSPEITA_POLEGADAS = 3.5

TERMOS_TELEFONIA = [
    "dual sim",
    "single sim",
    "sim card",
    "nano sim",
    "micro sim",
    "gsm",
    "2g",
    "3g",
    "4g",
    "5g",
    "lte",
    "volte",
    "cell phone",
    "cellphone",
    "mobile phone",
    "feature phone",
    "smartphone",
    "phone",
    "telefone",
    "celular",
    "telefono",
    "chamadas",
    "call",
    "calling",
]

TERMOS_TELEFONIA_FORTE = [
    "dual sim",
    "single sim",
    "sim card",
    "nano sim",
    "micro sim",
    "gsm",
    "lte",
    "volte",
    "cell phone",
    "cellphone",
    "mobile phone",
    "feature phone",
    "smartphone",
    "telefone celular",
    "calling",
]

TERMOS_ACESSORIO = [
    "case",
    "cover",
    "phone case",
    "screen protector",
    "tempered glass",
    "película",
    "pelicula",
    "capa",
    "capinha",
    "battery replacement",
    "replacement battery",
    "charger",
    "charging cable",
    "usb cable",
    "lcd screen replacement",
    "touch screen replacement",
    "display replacement",
    "motherboard",
    "flex cable",
    "spare parts",
    "parts for",
    "holder",
    "stand",
    "mount",
    "headphone only",
]

TERMOS_BRINQUEDO = [
    "toy phone",
    "kids toy",
    "children toy",
    "educational toy",
    "brinquedo",
    "infantil educativo",
]

PADROES_ANATEL = [
    re.compile(r"\bANATEL\b[^\d]{0,40}(\d{8,13})", re.IGNORECASE),
    re.compile(r"\b(\d{5}[-\s]?\d{2}[-\s]?\d{4})\b"),
]


@dataclass
class Classificacao:
    status: str
    categoria_print: str
    motivos: List[str] = field(default_factory=list)
    evidencias: List[str] = field(default_factory=list)
    codigo_anatel: str = ""
    medidas_extraidas: str = ""
    altura_cm: Optional[float] = None
    largura_cm: Optional[float] = None
    medida_proxima_ou_menor: bool = False
    sem_medidas: bool = False
    tela_extraida: str = ""
    tela_polegadas: Optional[float] = None
    tela_mini: bool = False
    tela_suspeita: bool = False
    tela_grande: bool = False
    eh_mini_celular: bool = False
    eh_acessorio: bool = False
    sem_tela: bool = False
    regra_classificacao: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "categoria_print": self.categoria_print,
            "motivo": "; ".join(self.motivos),
            "evidencias": "; ".join(self.evidencias),
            "codigo_anatel": self.codigo_anatel,
            "medidas_extraidas": self.medidas_extraidas,
            "altura_cm": self.altura_cm,
            "largura_cm": self.largura_cm,
            "medida_proxima_ou_menor": self.medida_proxima_ou_menor,
            "sem_medidas": self.sem_medidas,
            "tela_extraida": self.tela_extraida,
            "tela_polegadas": self.tela_polegadas,
            "tela_mini": self.tela_mini,
            "tela_suspeita": self.tela_suspeita,
            "tela_grande": self.tela_grande,
            "eh_mini_celular": self.eh_mini_celular,
            "eh_acessorio": self.eh_acessorio,
            "sem_tela": self.sem_tela,
            "regra_classificacao": self.regra_classificacao,
        }


def normalizar_texto(valor: Any) -> str:
    if valor is None:
        return ""
    texto = str(valor).replace("\xa0", " ")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def contem_termo(texto_lower: str, termos: List[str]) -> List[str]:
    return [termo for termo in termos if termo.lower() in texto_lower]


def _parse_numero(num: str) -> float:
    return float(num.replace(",", "."))


def extrair_codigo_anatel(texto: str) -> str:
    texto = normalizar_texto(texto)
    for padrao in PADROES_ANATEL:
        for match in padrao.finditer(texto):
            codigo = re.sub(r"\D", "", match.group(1))
            if 8 <= len(codigo) <= 13:
                return codigo
    return ""


def _contexto_match(texto: str, inicio: int, fim: int, margem: int = 70) -> str:
    ini = max(0, inicio - margem)
    fim2 = min(len(texto), fim + margem)
    return normalizar_texto(texto[ini:fim2])


def _contexto_eh_dimensao_fisica(contexto_lower: str) -> bool:
    termos_dimensao = [
        "product size",
        "package size",
        "packing size",
        "carton size",
        "dimension",
        "dimensions",
        "length",
        "width",
        "height",
        "l*w*h",
        "l x w x h",
        "body size",
        "phone size",
        "product dimension",
    ]
    return any(t in contexto_lower for t in termos_dimensao)


def extrair_tela_polegadas(*textos: str) -> Tuple[str, Optional[float], bool, bool, bool]:
    """
    Extrai tamanho de tela em polegadas.

    Padrões aceitos:
    - 6.5 Inch Rugged Phone
    - 4.0 Inch IPS Touch Screen
    - screen size: 2.4 inch
    - display 0.66"
    - tela de 5 polegadas

    A ordem dos textos importa: título/card têm prioridade, depois detalhes,
    depois body. Isso reduz contaminação por anúncios recomendados na página.
    """
    unidade = r"(?:\"|''|inch|inches|in\.?|polegadas?|pol\.?)"
    numero = r"(\d{1,2}(?:[\.,]\d{1,2})?)"

    padroes = [
        re.compile(
            rf"(?:screen\s*size|display\s*size|screen|display|touchscreen|touch\s*screen|lcd|tela|pantalla)"
            rf"[^\d]{{0,40}}{numero}\s*{unidade}(?!\s*[xX×\*])",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?<!\d){numero}\s*(?:-|\s)?{unidade}(?!\s*[xX×\*])"
            rf"(?:[^\|,;:]{{0,80}})?"
            rf"(?:screen|display|touch\s*screen|touchscreen|lcd|smartphone|mobile\s*phone|cell\s*phone|phone|telefone|celular|telefono)",
            re.IGNORECASE,
        ),
    ]

    candidatos: List[Tuple[int, int, str, float, str]] = []
    termos_contexto = [
        "screen",
        "display",
        "touchscreen",
        "touch screen",
        "lcd",
        "smartphone",
        "mobile phone",
        "cell phone",
        "cellphone",
        "phone",
        "telefone",
        "celular",
        "telefono",
        "tela",
        "pantalla",
    ]

    for prioridade, texto in enumerate(textos):
        texto_norm = normalizar_texto(texto)
        if not texto_norm:
            continue
        for padrao in padroes:
            for m in padrao.finditer(texto_norm):
                try:
                    valor = _parse_numero(m.group(1))
                except Exception:
                    continue

                # Faixa plausível para tela de telefone. Evita capturar 33W, 128GB etc.
                if not (0.5 <= valor <= 8.5):
                    continue

                contexto = _contexto_match(texto_norm, m.start(), m.end())
                contexto_lower = contexto.lower()
                if _contexto_eh_dimensao_fisica(contexto_lower):
                    continue
                if not any(t in contexto_lower for t in termos_contexto):
                    continue

                candidatos.append((prioridade, m.start(), m.group(0), valor, contexto))

    if not candidatos:
        return "", None, False, False, False

    candidatos.sort(key=lambda item: (item[0], item[1]))
    _, _, trecho, valor, contexto = candidatos[0]
    valor = round(valor, 2)
    tela_mini = valor <= LIMITE_TELA_IRREGULAR_POLEGADAS
    tela_suspeita = LIMITE_TELA_IRREGULAR_POLEGADAS < valor <= LIMITE_TELA_SUSPEITA_POLEGADAS
    tela_grande = valor > LIMITE_TELA_SUSPEITA_POLEGADAS
    return contexto or trecho, valor, tela_mini, tela_suspeita, tela_grande


def _classificacao_base(
    *,
    status: str,
    categoria_print: str,
    motivos: List[str],
    evidencias: List[str],
    codigo_anatel: str,
    tela_txt: str,
    tela_pol: Optional[float],
    tela_mini: bool,
    tela_suspeita: bool,
    tela_grande: bool,
    eh_mini_celular: bool,
    eh_acessorio: bool,
    sem_tela: bool,
    regra: str,
) -> Classificacao:
    return Classificacao(
        status=status,
        categoria_print=categoria_print,
        motivos=motivos,
        evidencias=sorted(set(evidencias), key=evidencias.index),
        codigo_anatel=codigo_anatel,
        medidas_extraidas="",
        altura_cm=None,
        largura_cm=None,
        medida_proxima_ou_menor=False,
        sem_medidas=sem_tela,
        tela_extraida=tela_txt,
        tela_polegadas=tela_pol,
        tela_mini=tela_mini,
        tela_suspeita=tela_suspeita,
        tela_grande=tela_grande,
        eh_mini_celular=eh_mini_celular,
        eh_acessorio=eh_acessorio,
        sem_tela=sem_tela,
        regra_classificacao=regra,
    )


def classificar_produto(produto: Dict[str, Any]) -> Classificacao:
    titulo = normalizar_texto(produto.get("titulo"))
    texto_card = normalizar_texto(produto.get("texto_card"))
    detalhes = normalizar_texto(produto.get("detalhes"))
    texto_produto = normalizar_texto(produto.get("texto_pagina"))

    texto_focado = " ".join([titulo, texto_card, detalhes])
    texto_focado_lower = texto_focado.lower()
    titulo_lower = titulo.lower()
    texto_completo = " ".join([titulo, texto_card, detalhes, texto_produto])

    termos_tel = contem_termo(texto_focado_lower, TERMOS_TELEFONIA)
    termos_tel_forte = contem_termo(texto_focado_lower, TERMOS_TELEFONIA_FORTE)
    termos_acessorio = contem_termo(titulo_lower, TERMOS_ACESSORIO)
    termos_brinquedo = contem_termo(texto_focado_lower, TERMOS_BRINQUEDO)

    codigo_anatel = extrair_codigo_anatel(texto_completo)
    tela_txt, tela_pol, tela_mini, tela_suspeita, tela_grande = extrair_tela_polegadas(
        " ".join([titulo, texto_card]),
        detalhes,
        texto_produto[:30000],
    )

    tem_indicio_telefonia = bool(termos_tel)
    eh_acessorio = bool(termos_acessorio) and not termos_tel_forte
    eh_brinquedo_sem_telefonia_real = bool(termos_brinquedo) and not termos_tel_forte

    if eh_acessorio:
        return _classificacao_base(
            status="DESCARTADO",
            categoria_print="",
            motivos=["Produto aparenta ser acessório/peça, não aparelho celular."],
            evidencias=termos_acessorio[:6],
            codigo_anatel=codigo_anatel,
            tela_txt=tela_txt,
            tela_pol=tela_pol,
            tela_mini=tela_mini,
            tela_suspeita=tela_suspeita,
            tela_grande=tela_grande,
            eh_mini_celular=False,
            eh_acessorio=True,
            sem_tela=tela_pol is None,
            regra="acessorio_descartado",
        )

    if eh_brinquedo_sem_telefonia_real:
        return _classificacao_base(
            status="DESCARTADO",
            categoria_print="",
            motivos=["Produto aparenta ser brinquedo/infantil sem indício real de chip/SIM/GSM."],
            evidencias=termos_brinquedo[:6],
            codigo_anatel=codigo_anatel,
            tela_txt=tela_txt,
            tela_pol=tela_pol,
            tela_mini=tela_mini,
            tela_suspeita=tela_suspeita,
            tela_grande=tela_grande,
            eh_mini_celular=False,
            eh_acessorio=False,
            sem_tela=tela_pol is None,
            regra="brinquedo_descartado",
        )

    if not tem_indicio_telefonia:
        return _classificacao_base(
            status="DESCARTADO",
            categoria_print="",
            motivos=["Sem indício suficiente de celular/telefone com chip."],
            evidencias=[],
            codigo_anatel=codigo_anatel,
            tela_txt=tela_txt,
            tela_pol=tela_pol,
            tela_mini=tela_mini,
            tela_suspeita=tela_suspeita,
            tela_grande=tela_grande,
            eh_mini_celular=False,
            eh_acessorio=False,
            sem_tela=tela_pol is None,
            regra="sem_telefonia",
        )

    evidencias: List[str] = []
    if tela_txt:
        evidencias.append(f"Tela capturada: {tela_txt}")
    evidencias.extend(termos_tel[:8])
    if codigo_anatel:
        evidencias.append(f"ANATEL: {codigo_anatel}")

    if tela_pol is None:
        return _classificacao_base(
            status="REVISAR",
            categoria_print="suspeitos/sem_tela",
            motivos=["Aparelho celular localizado, mas o tamanho da tela não foi capturado automaticamente."],
            evidencias=evidencias,
            codigo_anatel=codigo_anatel,
            tela_txt="",
            tela_pol=None,
            tela_mini=False,
            tela_suspeita=False,
            tela_grande=False,
            eh_mini_celular=False,
            eh_acessorio=False,
            sem_tela=True,
            regra="celular_sem_tela_localizada",
        )

    if tela_mini:
        motivos = [f"Tela de {tela_pol}\" é igual ou inferior a 3 polegadas; classificar como mini celular."]
        if not codigo_anatel:
            motivos.append("Código ANATEL não identificado no anúncio.")
        return _classificacao_base(
            status="IRREGULAR",
            categoria_print="irregulares/tela_ate_3_polegadas",
            motivos=motivos,
            evidencias=evidencias,
            codigo_anatel=codigo_anatel,
            tela_txt=tela_txt,
            tela_pol=tela_pol,
            tela_mini=True,
            tela_suspeita=False,
            tela_grande=False,
            eh_mini_celular=True,
            eh_acessorio=False,
            sem_tela=False,
            regra="tela_igual_ou_inferior_3_polegadas",
        )

    if tela_suspeita:
        motivos = [f"Tela de {tela_pol}\" está próxima de 3 polegadas; enviar para revisão manual como suspeito."]
        if not codigo_anatel:
            motivos.append("Código ANATEL não identificado no anúncio.")
        return _classificacao_base(
            status="SUSPEITO",
            categoria_print="suspeitos/tela_proxima_3_polegadas",
            motivos=motivos,
            evidencias=evidencias,
            codigo_anatel=codigo_anatel,
            tela_txt=tela_txt,
            tela_pol=tela_pol,
            tela_mini=False,
            tela_suspeita=True,
            tela_grande=False,
            eh_mini_celular=False,
            eh_acessorio=False,
            sem_tela=False,
            regra="tela_acima_3_ate_3_5_polegadas_suspeito",
        )

    return _classificacao_base(
        status="DESCARTADO",
        categoria_print="",
        motivos=[f"Tela de {tela_pol}\" é maior que 3,5 polegadas; fora do recorte de mini celular."],
        evidencias=evidencias,
        codigo_anatel=codigo_anatel,
        tela_txt=tela_txt,
        tela_pol=tela_pol,
        tela_mini=False,
        tela_suspeita=False,
        tela_grande=True,
        eh_mini_celular=False,
        eh_acessorio=False,
        sem_tela=False,
        regra="tela_maior_que_3_5_polegadas",
    )
