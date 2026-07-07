# Crawler Comparativo Mercado Livre — Playwright x Selenium

Este projeto é um piloto para comparar dois estilos de crawler no Mercado Livre:

- `Playwright`: navegador moderno com locators e esperas automáticas.
- `Selenium`: estilo mais tradicional com WebDriverWait e seletores.
- `pandas`: organização, comparação com base ANATEL e exportação CSV/Parquet.

> Uso responsável: este crawler não implementa bypass de captcha, login, fingerprinting ou evasão anti-bot. Use limites baixos e pauses moderadas.

## Instalação

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

## Rodar com Playwright

```bash
python main.py --engine playwright --query "celular anatel" --limit 10
```

## Rodar com Selenium

```bash
python main.py --engine selenium --query "celular anatel" --limit 10
```

## Rodar os dois

```bash
python main.py --engine ambos --query "celular anatel" --limit 10
```

## Usar base ANATEL em CSV

```bash
python main.py --engine playwright --query "celular anatel" --limit 10 --base "C:\caminho\Produtos_Homologados.csv"
```

Por padrão, o loader tenta ler CSV com `sep=';'` e `encoding='latin1'`, que é comum em bases exportadas.

## Comparar resultados Playwright x Selenium

Depois de rodar ambos, copie os caminhos dos CSVs gerados e rode:

```bash
python comparar_resultados.py --playwright saidas/mercadolivre_playwright_YYYYMMDD_HHMMSS/resultados.csv --selenium saidas/mercadolivre_selenium_YYYYMMDD_HHMMSS/resultados.csv
```

## Estrutura

```text
mercadolivre_crawler/
├── base_anatel.py
├── crawler_playwright_ml.py
├── crawler_selenium_ml.py
├── extracao.py
├── utils.py
main.py
comparar_resultados.py
requirements.txt
```

## O que ele captura

Para cada produto encontrado na listagem:

- URL
- título
- preço aproximado
- marca
- modelo
- fabricante
- possíveis códigos ANATEL encontrados perto de termos como "ANATEL" ou "Homologação"
- status de validação
- motivo da validação
- HTML e print como evidência

## Status possíveis

- `REGULAR`: código ANATEL encontrado e localizado na base, sem divergência forte de marca/fabricante.
- `IRREGULAR`: sem código, código não encontrado na base ou divergência forte.
- `ALERTA`: código encontrado, mas houve divergência de modelo ou informação incompleta.
- `SEM_BASE`: código encontrado, mas nenhuma base ANATEL foi informada.
- `ERRO`: falha na coleta do produto.

## Observação importante

Como o Mercado Livre muda o layout com frequência, os seletores foram feitos com múltiplos fallbacks. Se a captura de cards ou ficha técnica falhar, ajuste primeiro os seletores em:

- `crawler_playwright_ml.py`
- `crawler_selenium_ml.py`
- `extracao.py`
