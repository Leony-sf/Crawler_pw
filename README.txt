TUTORIAL GERAL DOS CRAWLERS DE MARKETPLACES — MINI CELULARES
=================================================================

Este arquivo serve como explicação geral dos crawlers desenvolvidos para análise de anúncios de mini celulares/celulares possivelmente irregulares em diferentes marketplaces.

Marketplaces contemplados:
1. Mercado Livre
2. Shopee
3. Amazon
4. AliExpress
5. Alibaba
6. Magalu
7. Americanas
8. Carrefour
9. Casas Bahia


=================================================================
1. OBJETIVO GERAL
=================================================================

Os crawlers foram criados para localizar, coletar e organizar anúncios de possíveis mini celulares ou celulares suspeitos em marketplaces.

O foco principal é encontrar produtos que possam se enquadrar como aparelhos celulares de tamanho reduzido, mini celulares, telefones GSM pequenos, Bluetooth dialers, celulares Dual SIM compactos, aparelhos com chip/SIM ou dispositivos semelhantes.

A análise busca separar os produtos em categorias como:

- IRREGULAR
- SUSPEITO
- DESCARTADO

A saída principal dos programas é feita em arquivo Parquet:

products.parquet

Quando existem produtos suspeitos, também pode ser gerado:

suspeitos/suspeitos.parquet

Quando o produto é relevante para comprovação, o crawler também pode salvar prints nas pastas de saída.


=================================================================
2. REGRAS GERAIS CONSOLIDADAS
=================================================================

As regras gerais que devem ser mantidas nos crawlers são:

- Usar products.parquet como saída principal.
- Usar suspeitos/suspeitos.parquet para produtos suspeitos.
- Não criar pasta de descartados.
- Não salvar prints de produtos descartados.
- Salvar prints apenas de produtos irregulares ou suspeitos relevantes de acordo com as dimensões designadas.

- O TXT de busca do respectivo marketplace deve ser processado linha por linha.
    - A ordem esperada é:
      página 1 da linha 1 do TXT
      página 1 da linha 2 do TXT
      página 1 da linha 3 do TXT
      ...

- Produtos claramente fora do escopo, como comidas, itens de mercado, higiene, limpeza, capinhas e acessórios, devem ser descartados.

- O termo “mini” sozinho não deve classificar um produto como irregular.

- A decisão deve considerar indícios reais de mini celular, telefonia, chip, SIM, GSM, dimensões ou modelo conhecido.


=================================================================
3. REGRA PRINCIPAL DE MINI CELULARES POR DIMENSÃO
=================================================================

A regra mais recente para marketplaces nacionais é baseada na dimensão física do aparelho:

Maior dimensão física <= 80 mm
    → IRREGULAR

Maior dimensão física > 80 mm e <= 90 mm
    → SUSPEITO

Maior dimensão física > 90 mm
    → DESCARTADO

Sem medida física, mas com indício forte de mini celular
    → SUSPEITO

Sem medida física e sem indício forte
    → DESCARTADO

A regra considera a maior dimensão física do produto. Exemplo:

165 x 76 x 8 mm

Neste caso, mesmo que a largura ou espessura pareça pequena, a maior dimensão é 165 mm. Portanto, não é mini celular dentro do critério de 80 mm.

Exemplo de produto irregular:

61.8 x 23.6 x 11.6 mm

Maior dimensão: 61.8 mm
Classificação: IRREGULAR


=================================================================
4. INDÍCIOS FORTES DE MINI CELULAR
=================================================================

Palavras/modelos que indicam maior chance de mini celular:

- mini celular
- mini phone
- micro celular
- smallest phone
- bluetooth dialer
- card phone
- ponto eletrônico
- telefone GSM pequeno
- telefone com chip
- Dual SIM
- SIM card
- GSM
- L8Star
- BM70
- BM30
- BM10
- BM50
- GTStar
- Soyes
- Melrose

Observação: nomes como “iPhone Mini” ou “Smartphone Mini” de marcas conhecidas não significam, por si só, que o produto tem menos de 80 mm. Se não houver medida física ou indício forte, deve ser descartado ou mantido fora dos irregulares.


=================================================================
5. ESTRUTURA GERAL DE SAÍDA
=================================================================

Estrutura ideal:

saidas_<marketplace>/
├── products.parquet
├── resumo.txt
├── suspeitos/
│   └── suspeitos.parquet
└── prints/
    ├── irregulares/
    │   └── menor_80mm/
    └── suspeitos/


=================================================================
6. MERCADO LIVRE
=================================================================

Objetivo:
    Coletar anúncios do Mercado Livre e verificar produtos relacionados a celulares, mini celulares e possíveis irregularidades.

Pontos principais:
    - Pode analisar código ANATEL.
    - Pode comparar com uma base homologada da ANATEL.
    - Pode analisar vendedor.
    - Pode identificar CPF/CNPJ quando o fluxo de vendedor está habilitado.
    - Pode salvar prints de irregulares.

Regras específicas:
    - Código ANATEL ausente ou inválido pode indicar irregularidade.
    - Código fora da base pode indicar irregularidade.
    - Vendedor pessoa física/CPF pode ser tratado como irregular.
    - Vendedor CNPJ tende a ser tratado como regular, dependendo da regra ativa.
    - Produtos sem vendedor identificado podem ficar como aviso, dependendo da versão usada.
    - Para mini celulares, manter celulares pequenos, Dual SIM, GSM, tela pequena, aceita chip/SIM e Bluetooth dialer.

Exemplo aproximado:

python main.py --query celular --limit 50 --max-paginas 1 --base Produtos_Homologados_Anatel.csv

Quando usar:
    Use quando a análise envolver Mercado Livre, vendedores, CPF/CNPJ ou validação com base ANATEL.


=================================================================
7. SHOPEE
=================================================================

Objetivo:
    Capturar anúncios da Shopee relacionados a mini celulares e similares.

Pontos principais:
    - Pode exigir login.
    - Pode exigir captcha manual.
    - Pode usar pausa inicial para o usuário resolver bloqueios.
    - A paginação deve avançar corretamente pela seta da Shopee.
    - Comentários podem existir em versões antigas, mas para mini celulares o foco atual é produto/anúncio.

Regras específicas:
    - Manter celulares pequenos, Dual SIM, GSM, aceita chip/SIM, Bluetooth dialer e modelos de mini celular.
    - Não descartar apenas por falta de medida quando houver forte indício.
    - Sem medida e com indício forte pode ir para suspeitos.
    - Produtos claramente fora do escopo devem ser descartados.

Exemplo aproximado:

python main_shopee.py --txt buscar_shopee.txt --limit 50 --max-paginas 1 --pausar-inicio

Quando usar:
    Use quando a análise envolver Shopee e for necessário lidar com login/captcha/paginação manualmente.


=================================================================
8. AMAZON
=================================================================

Objetivo:
    Coletar anúncios da Amazon relacionados a celulares, mini celulares e possíveis irregularidades.

Pontos principais:
    - O modelo deve ser buscado em “Detalhes do produto” sempre que possível.
    - Pode analisar vendedores quando implementado.
    - Pode separar regulares/irregulares por ANATEL e CPF/CNPJ, dependendo da versão.
    - Para mini celulares, a planilha/parquet deve manter apenas produtos compatíveis com a busca.

Regras específicas:
    - Manter celulares pequenos, Dual SIM, GSM, aceita chip/SIM, Bluetooth dialer.
    - Produtos fora do escopo devem ser descartados.
    - A análise de modelo deve priorizar detalhes do produto, não apenas título.

Exemplo aproximado:

python main_amazon.py --txt buscar_amazon.txt --limit 50 --max-paginas 1 --pausar-inicio

Quando usar:
    Use quando a análise envolver Amazon e extração de detalhes técnicos/modelo.


=================================================================
9. ALIEXPRESS
=================================================================

Objetivo:
    Capturar mini celulares no AliExpress.

Pontos principais:
    - Foco em mini celulares.
    - Sem JSON nos resultados.
    - Não usar comentários no fluxo atual.
    - Evitar CSV desnecessário.
    - Saída principal em products.parquet.
    - Suspeitos em pasta própria.

Regras específicas:
    - Mini celulares de modelos como L8Star, BM70, BM30, BM10 e similares devem ser mantidos.
    - Produtos sem medida, mas com indício forte, podem ser suspeitos.
    - Produtos sem relação com telefonia devem ser descartados.
    - O crawler deve processar o TXT corretamente, linha por linha.

Exemplo:

python main_aliexpress.py --txt buscar_aliexpress.txt --limit 50 --max-paginas 1 --pausar-inicio

Estrutura esperada:

saidas_aliexpress/
├── products.parquet
├── resumo.txt
├── suspeitos/
│   └── suspeitos.parquet
└── prints/

Quando usar:
    Use para buscar mini celulares importados ou anúncios internacionais de aparelhos muito pequenos.


=================================================================
10. ALIBABA
=================================================================

Objetivo:
    Capturar mini celulares no Alibaba.

Pontos principais:
    - O Alibaba tem comportamento diferente dos marketplaces nacionais.
    - Pode exigir verificação manual/captcha.
    - A busca deve respeitar o TXT linha por linha.
    - Foi usada regra de dimensão física e, em versões anteriores, análise por polegadas de tela.

Regra consolidada atual:
    - Maior dimensão física <= 80 mm → IRREGULAR
    - >80 mm até 90 mm → SUSPEITO
    - >90 mm → DESCARTADO
    - Sem medida + indício forte → SUSPEITO

Exemplo:

python main_alibaba.py --txt buscar_alibaba.txt --limit 50 --max-paginas 1 --pausar-inicio

Quando usar:
    Use para capturar fornecedores internacionais, mini celulares e modelos vendidos em atacado.


=================================================================
11. MAGALU
=================================================================

Objetivo:
    Capturar possíveis mini celulares no Magalu.

Pontos principais:
    - Usa regra de dimensão física <= 80 mm.
    - Produtos entre 80 e 90 mm ficam como suspeitos.
    - Produtos sem medida, mas com indício forte, podem ficar como suspeitos.
    - Produtos sem medida e sem indício forte são descartados.
    - Suspeitos ficam todos em uma pasta única.

Regra:
    Maior dimensão física <= 80 mm
        → IRREGULAR

    Maior dimensão física > 80 mm e <= 90 mm
        → SUSPEITO

    Sem medida + indício forte
        → SUSPEITO

    Sem medida sem indício forte
        → DESCARTADO

Exemplo:

python main_magalu.py --txt buscar_magalu.txt --limit 10 --max-paginas 1 --pausar-inicio

Saída esperada:

saidas_magalu/
├── products.parquet
├── resumo.txt
├── suspeitos/
│   └── suspeitos.parquet
└── prints/
    ├── irregulares/
    │   └── menor_80mm/
    └── suspeitos/


=================================================================
12. AMERICANAS
=================================================================

Objetivo:
    Capturar possíveis mini celulares na Americanas.

Pontos principais:
    - Mesma lógica do Magalu.
    - A coleta de links precisou aceitar formatos diferentes, como produtos terminando em /p.
    - Foi necessário filtrar comidas e itens de mercado, pois a busca da Americanas pode misturar produtos fora do escopo.
    - O crawler não deve mandar tudo para revisão apenas por estar sem medida.

Regras importantes:
    - Produtos como chocolate, amendoim, leite, biscoito, higiene e limpeza devem ser ignorados.
    - Smartphone comum sem medida deve ser descartado se não houver indício forte de mini celular.
    - “iPhone Mini” e “Smartphone Mini” não são, por si só, mini celulares dentro do critério de 80 mm.
    - Sem medida + indício forte → SUSPEITO.
    - Sem medida sem indício forte → DESCARTADO.

Exemplo:

python main_americanas.py --txt buscar_americanas.txt --limit 10 --max-paginas 1 --pausar-inicio

Saída esperada:

saidas_americanas/
├── products.parquet
├── resumo.txt
├── suspeitos/
│   └── suspeitos.parquet
└── prints/
    ├── irregulares/
    │   └── menor_80mm/
    └── suspeitos/


=================================================================
13. CARREFOUR
=================================================================

Objetivo:
    Capturar possíveis mini celulares no Carrefour.

Pontos principais:
    - Mesma regra de dimensão física.
    - Não preencher CEP automaticamente.
    - Apenas aceitar cookies, se necessário.
    - Não digitar CEP em campos aleatórios.
    - Filtrar produtos fora do escopo.

Regras específicas:
    - Sem preenchimento de CEP.
    - Sem busca por campos aleatórios.
    - Aceitar cookies é permitido.
    - Produtos fora de telefonia devem ser descartados.

Exemplo:

python main_carrefour.py --txt buscar_carrefour.txt --limit 10 --max-paginas 1 --pausar-inicio

Saída esperada:

saidas_carrefour/
├── products.parquet
├── resumo.txt
├── suspeitos/
│   └── suspeitos.parquet
└── prints/
    ├── irregulares/
    │   └── menor_80mm/
    └── suspeitos/


=================================================================
14. CASAS BAHIA
=================================================================

Objetivo:
    Capturar possíveis mini celulares nas Casas Bahia.

Situação:
    Este crawler foi o mais problemático porque o site pode redirecionar para telas como:

- “Ops! Algo deu errado.”
- Tela do bonequinho.
- “Ih, ainda não encontramos nada para...”
- Páginas de topterms, como /Smartphones/b?origem=topterms

Fluxo ideal:
    1. Não clicar aleatoriamente em nada.
    2. Não preencher CEP.
    3. Não aceitar autocomplete/topterms.
    4. Não usar movimento humano solto.
    5. Abrir URL de busca.
    6. Se a URL funcionar, scrollar sem clicar.
    7. Coletar links.
    8. Abrir cada produto por URL direta.
    9. Analisar produto.
    10. Passar para a próxima linha do TXT.

Versão híbrida organizada:
    Caso a URL de busca caia na tela do bonequinho, o crawler pode usar a caixa de busca visível de forma controlada.

Interações permitidas:
    - aceitar cookies, se aparecer;
    - usar caixa de busca apenas se a URL falhar;
    - acionar botão/lupa de busca apenas nesse fallback.

Interações proibidas:
    - cliques aleatórios;
    - cliques em sugestões/topterms;
    - preencher CEP;
    - clicar em produtos na página de busca;
    - movimento humano sem alvo;
    - ficar preso na tela do bonequinho.

Exemplo:

python main_casas_bahia.py --txt buscar_casas_bahia.txt --limit 10 --max-paginas 1 --pausar-inicio --perfil perfil_casas_bahia

Observação importante:
    Se o crawler continuar caindo na tela do bonequinho, o ajuste deve ser feito apenas na função de montagem de URLs de busca, geralmente em:

utils_casas_bahia.py
função montar_urls_busca()

O restante do fluxo não deve ser alterado sem necessidade.


=================================================================
15. BOAS PRÁTICAS AO RODAR
=================================================================

Antes de rodar:

1. Ativar o ambiente virtual.
2. Conferir se o VS Code usa o interpretador correto.
3. Instalar requirements.
4. Rodar playwright install chromium.
5. Conferir se o TXT de busca existe.
6. Conferir se a pasta de saída está correta.
7. Usar --pausar-inicio se o marketplace exige login/captcha/cookies.
8. Testar com --limit 5 ou --limit 10 antes de rodar grande.
9. Conferir se products.parquet foi criado.
10. Conferir se os suspeitos/irregulares fazem sentido.


=================================================================
16. EXEMPLOS DE COMANDOS POR MARKETPLACE
=================================================================

Mercado Livre:

python main.py --query celular --limit 50 --max-paginas 1 --base Produtos_Homologados_Anatel.csv

Shopee:

python main_shopee.py --txt buscar_shopee.txt --limit 50 --max-paginas 1 --pausar-inicio

Amazon:

python main_amazon.py --txt buscar_amazon.txt --limit 50 --max-paginas 1 --pausar-inicio

AliExpress:

python main_aliexpress.py --txt buscar_aliexpress.txt --limit 50 --max-paginas 1 --pausar-inicio

Alibaba:

python main_alibaba.py --txt buscar_alibaba.txt --limit 50 --max-paginas 1 --pausar-inicio

Magalu:

python main_magalu.py --txt buscar_magalu.txt --limit 10 --max-paginas 1 --pausar-inicio

Americanas:

python main_americanas.py --txt buscar_americanas.txt --limit 10 --max-paginas 1 --pausar-inicio

Carrefour:

python main_carrefour.py --txt buscar_carrefour.txt --limit 10 --max-paginas 1 --pausar-inicio

Casas Bahia:

python main_casas_bahia.py --txt buscar_casas_bahia.txt --limit 10 --max-paginas 1 --pausar-inicio --perfil perfil_casas_bahia
