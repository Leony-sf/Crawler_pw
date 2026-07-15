from bs4 import BeautifulSoup

def extrair_dados_produtos_html(html_content):
    """Extrai os dados dos cards de produtos a partir do HTML retornado pela API."""
    produtos_extraidos = []
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Procura os cards pelo atributo data-testid ou classes genéricas
    cards = soup.select('div[data-testid="product-card-container"], a[data-testid="product-card"], .product-card')
    
    print(f"Encontrados {len(cards)} produtos no código da página.")
    
    for i, card in enumerate(cards):
        try:
            # Extração de Título
            titulo_tag = card.select_one('h2, h3, div[data-testid="product-title"], .product-title')
            titulo = titulo_tag.get_text(strip=True) if titulo_tag else "Título indisponível"
            
            # Extração de Preço
            preco_tag = card.select_one('span[data-testid="product-price"], .product-price, [data-testid="price-value"]')
            preco = preco_tag.get_text(strip=True) if preco_tag else "Preço indisponível"
            
            # Extração do Link
            link_tag = card if card.name == 'a' else card.select_one('a')
            link = link_tag.get('href') if link_tag else None
            
            # Normalizar URL
            if link and not link.startswith("http"):
                link = "https://www.casasbahia.com.br" + link
                
            produtos_extraidos.append({
                "Plataforma": "Casas Bahia",
                "Título": titulo,
                "Preço": preco,
                "Link": link
            })
            
        except Exception as e:
            print(f"Erro ao extrair dados do card {i}: {e}")
            continue
            
    return produtos_extraidos