# -*- coding: utf-8 -*-
"""
Regras de classificação para o crawler Casas Bahia.

Regra operacional:
- aparelho celular com maior dimensão física <= 80 mm = IRREGULAR;
- aparelho celular com maior dimensão física > 80 mm e <= 90 mm = SUSPEITO;
- aparelho celular sem medida física localizada = DESCARTADO, exceto quando houver indício forte de mini celular <= 80 mm;
- aparelho celular com maior dimensão física > 90 mm = DESCARTADO;
- sem medida física + indício forte de mini celular <= 80 mm = SUSPEITO;
- acessórios/peças/brinquedos sem indício real de telefonia são descartados.

A classificação usa a MAIOR dimensão física do aparelho para evitar falso positivo
por largura/espessura. Ex.: 165 x 76 x 8 mm é descartado, pois a maior dimensão
é 165 mm, mesmo que a largura seja menor que 80 mm.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


LIMITE_DIMENSAO_IRREGULAR_MM = 80.0
LIMITE_DIMENSAO_SUSPEITA_MM = 90.0

TERMOS_TELEFONIA = [
    "dual sim", "single sim", "dois chips", "2 chips", "chip", "sim card",
    "nano sim", "micro sim", "gsm", "2g", "3g", "4g", "5g", "lte", "volte",
    "celular", "telefone celular", "telefone móvel", "telefone movel", "smartphone",
    "feature phone", "mobile phone", "cell phone", "cellphone", "flip phone",
    "telefone simples", "celular simples", "celular antigo", "tijolinho",
    "chamada", "ligações", "ligacoes", "realiza chamada", "discagem",
]

TERMOS_TELEFONIA_FORTE = [
    "dual sim", "dois chips", "2 chips", "sim card", "gsm", "lte", "volte",
    "celular", "telefone celular", "smartphone", "mobile phone", "cell phone",
    "feature phone", "flip phone", "celular simples", "tijolinho",
]

TERMOS_INDICIO_FORTE_MENOR_80MM = [
    # Termos/modelos usados para manter em suspeitos quando a Casas Bahia não exibe dimensão física.
    # Não inclui apenas "mini", pois isso gera falso positivo em iPhone 13 Mini, Twist Mini etc.
    "mini celular", "mini telefone", "mini mobile", "mini phone", "mini cellphone",
    "menor celular", "menor telefone", "smallest phone", "tiny phone", "micro celular",
    "card phone", "bluetooth dialer", "discador bluetooth", "ponto eletrônico",
    "telefone espião", "telefone espiao", "fone discador", "headset dialer",
    "l8star", "gtstar", "bm70", "bm30", "bm10", "bm50", "k8 mini",
    "soyes xs", "soyes xs11", "melrose s9x",
]

TERMOS_ACESSORIO = [
    "capa", "capinha", "case", "cover", "película", "pelicula", "vidro temperado",
    "screen protector", "tempered glass", "carregador", "cabo usb", "fonte",
    "bateria", "bateria para", "tela para", "display para", "lcd para",
    "peça", "peca", "peças", "pecas", "conector", "flex", "placa", "suporte",
    "fone de ouvido", "headphone", "headset", "adaptador", "carteira", "bolsa",
]

TERMOS_PRODUTO_FORA_DO_ESCOPO = [
    "chocolate", "amendoim", "amêndoa", "amendoas", "biscoito", "bolacha",
    "leite", "lacta", "garoto", "nestlé", "nestle", "café", "cafe",
    "açúcar", "acucar", "arroz", "feijão", "feijao", "macarrão", "macarrao",
    "molho", "tempero", "salgadinho", "suco", "refrigerante", "vinho",
    "cerveja", "ração", "racao", "shampoo", "condicionador", "sabonete",
    "fralda", "detergente", "desinfetante", "limpador", "desodorante",
    "perfume", "creme dental", "escova dental",
]

TERMOS_BRINQUEDO = [
    "brinquedo", "infantil educativo", "educativo", "toy phone", "kids toy",
    "children toy", "mini smartphone infantil", "telefone infantil",
]

PADROES_ANATEL = [
    re.compile(r"\bANATEL\b[^\d]{0,45}(\d{8,13})", re.IGNORECASE),
    re.compile(r"\b(\d{5}[-\s]?\d{2}[-\s]?\d{4})\b"),
]


@dataclass
class Classificacao:
    status: str
    categoria_print: str
    motivos: List[str] = field(default_factory=list)
    evidencias: List[str] = field(default_factory=list)
    codigo_anatel: str = ""
    tela_extraida: str = ""
    tela_polegadas: Optional[float] = None
    tela_mini: bool = False
    tela_suspeita: bool = False
    tela_grande: bool = False
    eh_mini_celular: bool = False
    eh_acessorio: bool = False
    sem_tela: bool = False
    regra_classificacao: str = ""
    medidas_extraidas: str = ""
    altura_cm: Optional[float] = None
    largura_cm: Optional[float] = None
    medida_proxima_ou_menor: bool = False
    sem_medidas: bool = False
    maior_dimensao_mm: Optional[float] = None
    altura_mm: Optional[float] = None
    largura_mm: Optional[float] = None
    comprimento_mm: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "categoria_print": self.categoria_print,
            "motivo": "; ".join(self.motivos),
            "evidencias": "; ".join(self.evidencias),
            "codigo_anatel": self.codigo_anatel,
            "tela_extraida": self.tela_extraida,
            "tela_polegadas": self.tela_polegadas,
            "tela_mini": self.tela_mini,
            "tela_suspeita": self.tela_suspeita,
            "tela_grande": self.tela_grande,
            "eh_mini_celular": self.eh_mini_celular,
            "eh_acessorio": self.eh_acessorio,
            "sem_tela": self.sem_tela,
            "regra_classificacao": self.regra_classificacao,
            "medidas_extraidas": self.medidas_extraidas,
            "altura_cm": self.altura_cm,
            "largura_cm": self.largura_cm,
            "medida_proxima_ou_menor": self.medida_proxima_ou_menor,
            "sem_medidas": self.sem_medidas,
            "maior_dimensao_mm": self.maior_dimensao_mm,
            "altura_mm": self.altura_mm,
            "largura_mm": self.largura_mm,
            "comprimento_mm": self.comprimento_mm,
        }


def normalizar_texto(valor: Any) -> str:
    if valor is None:
        return ""
    texto = str(valor).replace("\xa0", " ").replace("\u200b", " ")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def contem_termo(texto_lower: str, termos: List[str]) -> List[str]:
    return [termo for termo in termos if termo.lower() in texto_lower]


def _parse_numero(num: str) -> float:
    return float(num.replace(",", "."))


def _formatar_num(valor: float) -> str:
    valor = round(float(valor), 2)
    if valor.is_integer():
        return str(int(valor))
    return str(valor).replace(".", ",")


def _para_mm(valor: float, unidade: str) -> float:
    unidade = unidade.lower().strip()
    if unidade in ["cm", "centimetro", "centimetros", "centímetro", "centímetros"]:
        return valor * 10.0
    return valor


def extrair_codigo_anatel(texto: str) -> str:
    texto = normalizar_texto(texto)
    for padrao in PADROES_ANATEL:
        for match in padrao.finditer(texto):
            codigo = re.sub(r"\D", "", match.group(1))
            if 8 <= len(codigo) <= 13:
                return codigo
    return ""


def _contexto_match(texto: str, inicio: int, fim: int, margem: int = 85) -> str:
    ini = max(0, inicio - margem)
    fim2 = min(len(texto), fim + margem)
    return normalizar_texto(texto[ini:fim2])


def _contexto_eh_dimensao_fisica(contexto_lower: str) -> bool:
    termos_dimensao = [
        "tamanho do produto", "dimensão", "dimensao", "dimensões", "dimensoes",
        "altura", "largura", "profundidade", "comprimento", "peso", "embalagem",
        "package", "dimension", "dimensions", "height", "width", "length", "l x w x h",
    ]
    return any(t in contexto_lower for t in termos_dimensao)


def extrair_tela_polegadas(*textos: str) -> Tuple[str, Optional[float], bool, bool, bool]:
    """Extrai tela só como dado auxiliar; a decisão atual é por dimensão física."""
    numero = r"(\d{1,2}(?:[\.,]\d{1,2})?)"
    unidade = r"(?:\"|''|polegadas?|pol\.?|inch|inches|in\.?)"
    padroes = [
        re.compile(
            rf"(?:tamanho\s+da\s+tela|tela|display|visor|screen\s*size|screen|display\s*size|touchscreen|lcd)"
            rf"[^\d]{{0,45}}{numero}\s*{unidade}(?!\s*[xX×\*])",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?<!\d){numero}\s*{unidade}(?!\s*[xX×\*])"
            rf"(?:[^\|,;:]{{0,80}})?"
            rf"(?:tela|display|visor|screen|touch\s*screen|touchscreen|lcd|celular|smartphone|telefone|phone)",
            re.IGNORECASE,
        ),
        re.compile(rf"(?:tela|display|visor)\s*(?:de|:)?\s*{numero}\s*(?!gb|g|mah|mp|w\b)", re.IGNORECASE),
    ]
    termos_contexto = ["tamanho da tela", "tela", "display", "visor", "screen", "touchscreen", "lcd", "celular", "smartphone", "telefone", "phone", "mobile"]
    candidatos: List[Tuple[int, int, str, float, str]] = []
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
    return contexto or trecho, valor, valor <= 3.0, 3.0 < valor <= 3.5, valor > 3.5


def _parece_medida_valida(valores_mm: List[float]) -> bool:
    if not valores_mm:
        return False
    maior = max(valores_mm)
    menor = min(valores_mm)
    if maior < 40 or maior > 260:
        return False
    if len(valores_mm) >= 3 and menor < 3:
        return False
    return True


def _extrair_dimensoes_grupo(texto: str, prioridade: int) -> List[Dict[str, Any]]:
    candidatos: List[Dict[str, Any]] = []
    numero = r"(\d{1,3}(?:[\.,]\d{1,2})?)"
    sep = r"\s*(?:x|X|×|\*)\s*"
    unidade = r"(mm|mil[ií]metros?|cm|cent[ií]metros?)"
    padrao = re.compile(rf"{numero}{sep}{numero}(?:{sep}{numero})?\s*{unidade}\b", re.IGNORECASE)
    for m in padrao.finditer(texto):
        nums = [m.group(1), m.group(2)]
        if m.group(4):
            nums.append(m.group(3))
            unidade_txt = m.group(4)
        else:
            unidade_txt = m.group(3)
        try:
            valores_mm = [_para_mm(_parse_numero(n), unidade_txt) for n in nums]
        except Exception:
            continue
        contexto = _contexto_match(texto, m.start(), m.end(), margem=100)
        if not _parece_medida_valida(valores_mm):
            continue
        valores_ordenados = sorted(valores_mm, reverse=True)
        candidatos.append({
            "prioridade": prioridade,
            "posicao": m.start(),
            "trecho": contexto,
            "maior_dimensao_mm": round(max(valores_mm), 2),
            "altura_mm": round(valores_ordenados[0], 2) if valores_ordenados else None,
            "largura_mm": round(valores_ordenados[1], 2) if len(valores_ordenados) >= 2 else None,
            "comprimento_mm": round(valores_ordenados[0], 2) if valores_ordenados else None,
            "valores_mm": [round(v, 2) for v in valores_mm],
        })
    return candidatos


def _extrair_dimensoes_rotuladas(texto: str, prioridade: int) -> List[Dict[str, Any]]:
    """
    Captura medidas rotuladas. Para classificar, usa altura/comprimento/length.
    Não usa largura isolada como dimensão principal, porque quase todo celular tem
    largura menor que 80 mm.
    """
    candidatos: List[Dict[str, Any]] = []
    numero = r"(\d{1,3}(?:[\.,]\d{1,2})?)"
    unidade = r"(?:mm|mil[ií]metros?|cm|cent[ií]metros?)"

    def aplicar_medida(rotulo: str, numero_txt: str, unidade_txt: str, inicio: int, fim: int, encontrados: Dict[str, float], contextos: List[str]) -> None:
        try:
            valor_mm = _para_mm(_parse_numero(numero_txt), unidade_txt)
        except Exception:
            return
        if not (3 <= valor_mm <= 260):
            return
        contextos.append(_contexto_match(texto, inicio, fim, margem=90))
        rotulo_low = rotulo.lower()
        if rotulo_low in ["altura", "height"]:
            encontrados["altura_mm"] = round(valor_mm, 2)
        elif rotulo_low in ["comprimento", "profundidade", "length"]:
            encontrados["comprimento_mm"] = round(valor_mm, 2)
        elif rotulo_low in ["largura", "width"]:
            encontrados["largura_mm"] = round(valor_mm, 2)

    encontrados: Dict[str, float] = {}
    contexto_unificado: List[str] = []
    primeira_pos = 10**9

    # Ex.: Altura 12,4 cm / Height: 124 mm
    padrao_valor_unidade = re.compile(
        rf"\b(altura|comprimento|profundidade|height|length|largura|width)\b[^\d\|]{{0,55}}?{numero}\s*({unidade})\b",
        re.IGNORECASE,
    )
    for m in padrao_valor_unidade.finditer(texto):
        primeira_pos = min(primeira_pos, m.start())
        aplicar_medida(m.group(1), m.group(2), m.group(3), m.start(), m.end(), encontrados, contexto_unificado)

    # Ex.: Altura do produto (cm) 12,4 / Largura (mm): 56
    padrao_unidade_no_rotulo = re.compile(
        rf"\b(altura|comprimento|profundidade|height|length|largura|width)\b[^\n\r\|:]{{0,80}}?\(({unidade})\)[^\d]{{0,35}}{numero}\b",
        re.IGNORECASE,
    )
    for m in padrao_unidade_no_rotulo.finditer(texto):
        primeira_pos = min(primeira_pos, m.start())
        aplicar_medida(m.group(1), m.group(3), m.group(2), m.start(), m.end(), encontrados, contexto_unificado)

    principais = [
        v for k, v in encontrados.items()
        if k in ["altura_mm", "comprimento_mm"] and v is not None
    ]
    if principais:
        maior = round(max(principais), 2)
        if 40 <= maior <= 260:
            candidatos.append({
                "prioridade": prioridade,
                "posicao": primeira_pos,
                "trecho": " | ".join(contexto_unificado[:5]),
                "maior_dimensao_mm": maior,
                "altura_mm": encontrados.get("altura_mm"),
                "largura_mm": encontrados.get("largura_mm"),
                "comprimento_mm": encontrados.get("comprimento_mm"),
                "valores_mm": list(encontrados.values()),
            })
    return candidatos


def extrair_medida_fisica_mm(*textos: str) -> Dict[str, Any]:
    candidatos: List[Dict[str, Any]] = []
    for prioridade, texto in enumerate(textos):
        texto_norm = normalizar_texto(texto)
        if not texto_norm:
            continue
        candidatos.extend(_extrair_dimensoes_grupo(texto_norm, prioridade))
        candidatos.extend(_extrair_dimensoes_rotuladas(texto_norm, prioridade))
    if not candidatos:
        return {"medidas_extraidas": "", "maior_dimensao_mm": None, "altura_mm": None, "largura_mm": None, "comprimento_mm": None}
    candidatos.sort(key=lambda c: (c["prioridade"], c["posicao"], c["maior_dimensao_mm"]))
    melhor = candidatos[0]
    return {
        "medidas_extraidas": melhor["trecho"],
        "maior_dimensao_mm": melhor["maior_dimensao_mm"],
        "altura_mm": melhor.get("altura_mm"),
        "largura_mm": melhor.get("largura_mm"),
        "comprimento_mm": melhor.get("comprimento_mm"),
    }


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
    medidas_extraidas: str = "",
    maior_dimensao_mm: Optional[float] = None,
    altura_mm: Optional[float] = None,
    largura_mm: Optional[float] = None,
    comprimento_mm: Optional[float] = None,
) -> Classificacao:
    altura_cm = round(altura_mm / 10, 2) if altura_mm is not None else None
    largura_cm = round(largura_mm / 10, 2) if largura_mm is not None else None
    return Classificacao(
        status=status,
        categoria_print=categoria_print,
        motivos=motivos,
        evidencias=sorted(set(evidencias), key=evidencias.index),
        codigo_anatel=codigo_anatel,
        tela_extraida=tela_txt,
        tela_polegadas=tela_pol,
        tela_mini=tela_mini,
        tela_suspeita=tela_suspeita,
        tela_grande=tela_grande,
        eh_mini_celular=eh_mini_celular,
        eh_acessorio=eh_acessorio,
        sem_tela=sem_tela,
        regra_classificacao=regra,
        medidas_extraidas=medidas_extraidas,
        altura_cm=altura_cm,
        largura_cm=largura_cm,
        medida_proxima_ou_menor=bool(maior_dimensao_mm is not None and maior_dimensao_mm <= LIMITE_DIMENSAO_SUSPEITA_MM),
        sem_medidas=maior_dimensao_mm is None,
        maior_dimensao_mm=maior_dimensao_mm,
        altura_mm=altura_mm,
        largura_mm=largura_mm,
        comprimento_mm=comprimento_mm,
    )


def classificar_produto(produto: Dict[str, Any]) -> Classificacao:
    titulo = normalizar_texto(produto.get("titulo"))
    texto_card = normalizar_texto(produto.get("texto_card"))
    detalhes = normalizar_texto(produto.get("detalhes"))
    ficha_tecnica = normalizar_texto(produto.get("ficha_tecnica"))
    texto_produto = normalizar_texto(produto.get("texto_pagina"))

    texto_focado = " ".join([titulo, texto_card, detalhes, ficha_tecnica])
    texto_focado_lower = texto_focado.lower()
    titulo_lower = titulo.lower()
    texto_completo = " ".join([titulo, texto_card, detalhes, ficha_tecnica, texto_produto[:15000]])

    termos_fora_escopo = contem_termo(texto_focado_lower, TERMOS_PRODUTO_FORA_DO_ESCOPO)
    termos_tel = contem_termo(texto_focado_lower, TERMOS_TELEFONIA)
    termos_tel_forte = contem_termo(texto_focado_lower, TERMOS_TELEFONIA_FORTE)
    termos_indicio_forte_menor_80 = contem_termo(texto_focado_lower, TERMOS_INDICIO_FORTE_MENOR_80MM)
    termos_acessorio = contem_termo(titulo_lower, TERMOS_ACESSORIO)
    termos_brinquedo = contem_termo(texto_focado_lower, TERMOS_BRINQUEDO)
    termos_aparelho_no_titulo = contem_termo(
        titulo_lower,
        ["dual chip", "dois chips", "2 chips", "chip", "sim card", "gsm", "2g", "3g", "4g", "5g", "lte", "telefone", "celular simples", "telefone celular", "flip phone", "tijolinho", "feature phone"],
    )

    codigo_anatel = extrair_codigo_anatel(texto_completo)
    tela_txt, tela_pol, tela_mini, tela_suspeita, tela_grande = extrair_tela_polegadas(" ".join([titulo, texto_card]), ficha_tecnica, detalhes)
    medida = extrair_medida_fisica_mm(" ".join([titulo, texto_card]), ficha_tecnica, detalhes, texto_produto[:12000])
    medidas_extraidas = medida["medidas_extraidas"]
    maior_dimensao_mm = medida["maior_dimensao_mm"]
    altura_mm = medida["altura_mm"]
    largura_mm = medida["largura_mm"]
    comprimento_mm = medida["comprimento_mm"]

    tem_indicio_telefonia = bool(termos_tel)
    eh_acessorio = bool(termos_acessorio) and not termos_aparelho_no_titulo
    eh_brinquedo_sem_telefonia_real = bool(termos_brinquedo) and not termos_tel_forte

    common = dict(
        codigo_anatel=codigo_anatel,
        tela_txt=tela_txt,
        tela_pol=tela_pol,
        tela_mini=tela_mini,
        tela_suspeita=tela_suspeita,
        tela_grande=tela_grande,
        sem_tela=tela_pol is None,
        medidas_extraidas=medidas_extraidas,
        maior_dimensao_mm=maior_dimensao_mm,
        altura_mm=altura_mm,
        largura_mm=largura_mm,
        comprimento_mm=comprimento_mm,
    )

    if termos_fora_escopo and not termos_tel:
        return _classificacao_base(
            status="DESCARTADO",
            categoria_print="",
            motivos=["Produto fora do escopo de telefonia/celular."],
            evidencias=termos_fora_escopo[:6],
            eh_mini_celular=False,
            eh_acessorio=False,
            regra="fora_escopo_comida_mercado_descartado",
            **common,
        )

    if eh_acessorio:
        return _classificacao_base(status="DESCARTADO", categoria_print="", motivos=["Produto aparenta ser acessório/peça, não aparelho celular."], evidencias=termos_acessorio[:6], eh_mini_celular=False, eh_acessorio=True, regra="acessorio_descartado", **common)
    if eh_brinquedo_sem_telefonia_real:
        return _classificacao_base(status="DESCARTADO", categoria_print="", motivos=["Produto aparenta ser brinquedo/infantil sem indício real de chip/SIM/GSM."], evidencias=termos_brinquedo[:6], eh_mini_celular=False, eh_acessorio=False, regra="brinquedo_descartado", **common)
    if not tem_indicio_telefonia:
        return _classificacao_base(status="DESCARTADO", categoria_print="", motivos=["Sem indício suficiente de celular/telefone com chip."], evidencias=[], eh_mini_celular=False, eh_acessorio=False, regra="sem_telefonia", **common)

    evidencias: List[str] = []
    if medidas_extraidas:
        evidencias.append(f"Medida capturada: {medidas_extraidas}")
    if tela_txt:
        evidencias.append(f"Tela capturada: {tela_txt}")
    evidencias.extend(termos_tel[:8])
    if codigo_anatel:
        evidencias.append(f"ANATEL: {codigo_anatel}")

    if maior_dimensao_mm is None:
        if termos_indicio_forte_menor_80:
            evidencias.extend(termos_indicio_forte_menor_80[:6])
            return _classificacao_base(
                status="SUSPEITO",
                categoria_print="suspeitos",
                motivos=[
                    "Medida física não localizada, mas há indício forte de mini celular possivelmente menor que 80 mm."
                ],
                evidencias=evidencias,
                eh_mini_celular=False,
                eh_acessorio=False,
                regra="sem_medida_com_indicio_forte_menor_80mm",
                medidas_extraidas="",
                maior_dimensao_mm=None,
                altura_mm=None,
                largura_mm=None,
                comprimento_mm=None,
                codigo_anatel=codigo_anatel,
                tela_txt=tela_txt,
                tela_pol=tela_pol,
                tela_mini=False,
                tela_suspeita=True,
                tela_grande=False,
                sem_tela=tela_pol is None,
            )

        return _classificacao_base(
            status="DESCARTADO",
            categoria_print="",
            motivos=[
                "Aparelho celular sem medida física capturada e sem indício forte de dimensões menores que 80 mm."
            ],
            evidencias=evidencias,
            eh_mini_celular=False,
            eh_acessorio=False,
            regra="sem_medida_sem_indicio_forte_descartado",
            medidas_extraidas="",
            maior_dimensao_mm=None,
            altura_mm=None,
            largura_mm=None,
            comprimento_mm=None,
            codigo_anatel=codigo_anatel,
            tela_txt=tela_txt,
            tela_pol=tela_pol,
            tela_mini=False,
            tela_suspeita=False,
            tela_grande=False,
            sem_tela=tela_pol is None,
        )

    if maior_dimensao_mm <= LIMITE_DIMENSAO_IRREGULAR_MM:
        motivos = [f"Maior dimensão física capturada: {_formatar_num(maior_dimensao_mm)} mm, igual ou inferior a 80 mm."]
        if not codigo_anatel:
            motivos.append("Código ANATEL não identificado no anúncio.")
        return _classificacao_base(status="IRREGULAR", categoria_print="irregulares/menor_80mm", motivos=motivos, evidencias=evidencias, eh_mini_celular=True, eh_acessorio=False, regra="maior_dimensao_igual_ou_inferior_80mm", codigo_anatel=codigo_anatel, tela_txt=tela_txt, tela_pol=tela_pol, tela_mini=True, tela_suspeita=False, tela_grande=False, sem_tela=tela_pol is None, medidas_extraidas=medidas_extraidas, maior_dimensao_mm=maior_dimensao_mm, altura_mm=altura_mm, largura_mm=largura_mm, comprimento_mm=comprimento_mm)

    if maior_dimensao_mm <= LIMITE_DIMENSAO_SUSPEITA_MM:
        motivos = [f"Maior dimensão física capturada: {_formatar_num(maior_dimensao_mm)} mm, próxima de 80 mm."]
        if not codigo_anatel:
            motivos.append("Código ANATEL não identificado no anúncio.")
        return _classificacao_base(status="SUSPEITO", categoria_print="suspeitos", motivos=motivos, evidencias=evidencias, eh_mini_celular=False, eh_acessorio=False, regra="maior_dimensao_acima_80_ate_90mm_suspeito", codigo_anatel=codigo_anatel, tela_txt=tela_txt, tela_pol=tela_pol, tela_mini=False, tela_suspeita=True, tela_grande=False, sem_tela=tela_pol is None, medidas_extraidas=medidas_extraidas, maior_dimensao_mm=maior_dimensao_mm, altura_mm=altura_mm, largura_mm=largura_mm, comprimento_mm=comprimento_mm)

    return _classificacao_base(
        status="DESCARTADO",
        categoria_print="",
        motivos=[f"Maior dimensão física capturada: {_formatar_num(maior_dimensao_mm)} mm, acima do limite de 90 mm."],
        evidencias=evidencias,
        eh_mini_celular=False,
        eh_acessorio=False,
        regra="maior_dimensao_acima_90mm",
        codigo_anatel=codigo_anatel,
        tela_txt=tela_txt,
        tela_pol=tela_pol,
        tela_mini=False,
        tela_suspeita=False,
        tela_grande=True,
        sem_tela=tela_pol is None,
        medidas_extraidas=medidas_extraidas,
        maior_dimensao_mm=maior_dimensao_mm,
        altura_mm=altura_mm,
        largura_mm=largura_mm,
        comprimento_mm=comprimento_mm,
    )
