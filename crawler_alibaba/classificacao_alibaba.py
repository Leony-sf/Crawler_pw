# -*- coding: utf-8 -*-
"""
Regras de classificação para o crawler Alibaba.com.

Regra operacional atual:
- classificar como IRREGULAR anúncio de celular com dimensões iguais ou inferiores a 12cm (altura) x 5,5cm (largura);
- celular com dimensões maiores em ambos os eixos é DESCARTADO;
- celular com uma dimensão menor e outra maior fica como SUSPEITO;
- celular em que as medidas não foram localizadas fica como REVISAR.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

LIMITE_ALTURA_CM = 12.0
LIMITE_LARGURA_CM = 5.5

TERMOS_TELEFONIA = [
    "dual sim", "single sim", "sim card", "nano sim", "micro sim", "gsm", "2g", "3g", "4g", "5g", "lte", "volte",
    "cell phone", "cellphone", "mobile phone", "feature phone", "smartphone", "phone", "telefone", "celular", "telefono",
    "chamadas", "call", "calling",
]

TERMOS_TELEFONIA_FORTE = [
    "dual sim", "single sim", "sim card", "nano sim", "micro sim", "gsm", "lte", "volte", "cell phone", "cellphone",
    "mobile phone", "feature phone", "smartphone", "telefone celular", "calling",
]

TERMOS_ACESSORIO = [
    "case", "cover", "phone case", "screen protector", "tempered glass", "película", "pelicula", "capa", "capinha",
    "battery replacement", "replacement battery", "charger", "charging cable", "usb cable", "lcd screen replacement",
    "touch screen replacement", "display replacement", "motherboard", "flex cable", "spare parts", "parts for",
    "holder", "stand", "mount", "headphone only",
]

TERMOS_BRINQUEDO = [
    "toy phone", "kids toy", "children toy", "educational toy", "brinquedo", "infantil educativo",
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

def extrair_medidas(*textos: str) -> Tuple[str, Optional[float], Optional[float]]:
    """Extrai altura e largura em cm baseando-se em formatos comuns (ex: 115x52x14mm)."""
    padroes = [
        re.compile(r"(\d{1,3}(?:[\.,]\d+)?)\s*(?:x|X|\*|×)\s*(\d{1,3}(?:[\.,]\d+)?)\s*(?:x|X|\*|×)\s*(\d{1,3}(?:[\.,]\d+)?)\s*(mm|cm)\b", re.IGNORECASE),
        re.compile(r"(?:size|dimensions?|medidas?|tamanho)[^\d]{0,20}(\d{1,3}(?:[\.,]\d+)?)\s*(?:x|X|\*|×)\s*(\d{1,3}(?:[\.,]\d+)?)\s*(mm|cm)\b", re.IGNORECASE),
        re.compile(r"(?:L\*W\*H|L\s*x\s*W\s*x\s*H)[^\d]{0,20}(\d{1,3}(?:[\.,]\d+)?)\s*(?:x|X|\*|×|-)\s*(\d{1,3}(?:[\.,]\d+)?)\s*(?:x|X|\*|×|-)\s*(\d{1,3}(?:[\.,]\d+)?)\s*(mm|cm)\b", re.IGNORECASE)
    ]

    for texto in textos:
        texto_norm = normalizar_texto(texto)
        if not texto_norm:
            continue
        for padrao in padroes:
            for m in padrao.finditer(texto_norm):
                try:
                    v1 = _parse_numero(m.group(1))
                    v2 = _parse_numero(m.group(2))
                    unidade = m.groups()[-1].lower()

                    if unidade == 'mm':
                        v1, v2 = v1 / 10.0, v2 / 10.0

                    altura = max(v1, v2)
                    largura = min(v1, v2)

                    if 3.0 <= altura <= 25.0 and 1.5 <= largura <= 15.0:
                        contexto = _contexto_match(texto_norm, m.start(), m.end(), margem=50)
                        return contexto, round(altura, 2), round(largura, 2)
                except Exception:
                    continue
    return "", None, None

def _classificacao_base(
    *, status: str, categoria_print: str, motivos: List[str], evidencias: List[str], codigo_anatel: str,
    medidas_txt: str, altura: Optional[float], largura: Optional[float], sem_medidas: bool,
    eh_mini_celular: bool, eh_acessorio: bool, regra: str,
) -> Classificacao:
    return Classificacao(
        status=status, categoria_print=categoria_print, motivos=motivos, evidencias=sorted(set(evidencias), key=evidencias.index),
        codigo_anatel=codigo_anatel, medidas_extraidas=medidas_txt, altura_cm=altura, largura_cm=largura,
        medida_proxima_ou_menor=eh_mini_celular, sem_medidas=sem_medidas, tela_extraida="", tela_polegadas=None,
        tela_mini=False, tela_suspeita=False, tela_grande=False, eh_mini_celular=eh_mini_celular,
        eh_acessorio=eh_acessorio, sem_tela=False, regra_classificacao=regra,
    )

def classificar_produto(produto: Dict[str, Any]) -> Classificacao:
    titulo = normalizar_texto(produto.get("titulo"))
    texto_card = normalizar_texto(produto.get("texto_card"))
    detalhes = normalizar_texto(produto.get("detalhes"))
    texto_produto = normalizar_texto(produto.get("texto_pagina"))

    texto_focado_lower = " ".join([titulo, texto_card, detalhes]).lower()
    titulo_lower = titulo.lower()
    texto_completo = " ".join([titulo, texto_card, detalhes, texto_produto])

    termos_tel = contem_termo(texto_focado_lower, TERMOS_TELEFONIA)
    termos_tel_forte = contem_termo(texto_focado_lower, TERMOS_TELEFONIA_FORTE)
    termos_acessorio = contem_termo(titulo_lower, TERMOS_ACESSORIO)
    termos_brinquedo = contem_termo(texto_focado_lower, TERMOS_BRINQUEDO)

    codigo_anatel = extrair_codigo_anatel(texto_completo)
    medidas_txt, altura_cm, largura_cm = extrair_medidas(" ".join([titulo, texto_card]), detalhes, texto_produto[:30000])

    tem_indicio_telefonia = bool(termos_tel)
    eh_acessorio = bool(termos_acessorio) and not termos_tel_forte
    eh_brinquedo_sem_telefonia_real = bool(termos_brinquedo) and not termos_tel_forte

    if eh_acessorio:
        return _classificacao_base(
            status="DESCARTADO", categoria_print="", motivos=["Produto aparenta ser acessório/peça, não aparelho celular."],
            evidencias=termos_acessorio[:6], codigo_anatel=codigo_anatel, medidas_txt=medidas_txt, altura=altura_cm,
            largura=largura_cm, sem_medidas=altura_cm is None, eh_mini_celular=False, eh_acessorio=True, regra="acessorio_descartado",
        )

    if eh_brinquedo_sem_telefonia_real:
        return _classificacao_base(
            status="DESCARTADO", categoria_print="", motivos=["Produto aparenta ser brinquedo sem indício real de telefonia."],
            evidencias=termos_brinquedo[:6], codigo_anatel=codigo_anatel, medidas_txt=medidas_txt, altura=altura_cm,
            largura=largura_cm, sem_medidas=altura_cm is None, eh_mini_celular=False, eh_acessorio=False, regra="brinquedo_descartado",
        )

    if not tem_indicio_telefonia:
        return _classificacao_base(
            status="DESCARTADO", categoria_print="", motivos=["Sem indício suficiente de celular/telefone com chip."],
            evidencias=[], codigo_anatel=codigo_anatel, medidas_txt=medidas_txt, altura=altura_cm, largura=largura_cm,
            sem_medidas=altura_cm is None, eh_mini_celular=False, eh_acessorio=False, regra="sem_telefonia",
        )

    evidencias: List[str] = []
    if medidas_txt: evidencias.append(f"Medidas: {medidas_txt}")
    evidencias.extend(termos_tel[:8])
    if codigo_anatel: evidencias.append(f"ANATEL: {codigo_anatel}")

    if altura_cm is None:
        return _classificacao_base(
            status="REVISAR", categoria_print="suspeitos/sem_medidas",
            motivos=["Aparelho celular localizado, mas as dimensões físicas não foram capturadas."],
            evidencias=evidencias, codigo_anatel=codigo_anatel, medidas_txt="", altura=None, largura=None,
            sem_medidas=True, eh_mini_celular=False, eh_acessorio=False, regra="celular_sem_medidas",
        )

    eh_menor_ou_igual = altura_cm <= LIMITE_ALTURA_CM and largura_cm <= LIMITE_LARGURA_CM
    eh_maior = altura_cm > LIMITE_ALTURA_CM and largura_cm > LIMITE_LARGURA_CM

    if eh_menor_ou_igual:
        motivos = [f"Medidas ({altura_cm}x{largura_cm} cm) menores ou iguais ao limite estipulado (12x5,5 cm)."]
        if not codigo_anatel: motivos.append("Código ANATEL não identificado no anúncio.")
        return _classificacao_base(
            status="IRREGULAR", categoria_print="irregulares/medidas_ate_12x5_5", motivos=motivos, evidencias=evidencias,
            codigo_anatel=codigo_anatel, medidas_txt=medidas_txt, altura=altura_cm, largura=largura_cm, sem_medidas=False,
            eh_mini_celular=True, eh_acessorio=False, regra="medidas_irregulares",
        )
    elif eh_maior:
        return _classificacao_base(
            status="DESCARTADO", categoria_print="", motivos=[f"Medidas ({altura_cm}x{largura_cm} cm) superiores ao limite."],
            evidencias=evidencias, codigo_anatel=codigo_anatel, medidas_txt=medidas_txt, altura=altura_cm, largura=largura_cm,
            sem_medidas=False, eh_mini_celular=False, eh_acessorio=False, regra="medida_maior",
        )
    else:
        motivos = [f"Medidas ({altura_cm}x{largura_cm} cm) têm proporções mistas em relação ao limite (12x5,5 cm)."]
        if not codigo_anatel: motivos.append("Código ANATEL não identificado no anúncio.")
        return _classificacao_base(
            status="SUSPEITO", categoria_print="suspeitos/medida_mista", motivos=motivos, evidencias=evidencias,
            codigo_anatel=codigo_anatel, medidas_txt=medidas_txt, altura=altura_cm, largura=largura_cm, sem_medidas=False,
            eh_mini_celular=False, eh_acessorio=False, regra="medida_mista",
        )