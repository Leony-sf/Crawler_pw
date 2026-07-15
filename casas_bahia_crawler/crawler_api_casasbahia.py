import requests

def buscar_produtos_casasbahia_api(termo_busca, api_key):
    """Dispara a busca através do endpoint da API de scraping."""
    termo_formatado = termo_busca.replace(' ', '-')
    target_url = f"https://www.casasbahia.com.br/{termo_formatado}/b"
    
    print(f"Enviando requisição para a URL via API: {target_url}")
    
    # URL oficial do ScraperAPI corrigida
    api_endpoint = "http://api.scraperapi.com"
    
    payload = {
        "api_key": api_key,
        "url": target_url,
        "render": "true" # O ScraperAPI usa 'render' em vez de 'render_js' para renderizar JavaScript
    }
    
    response = requests.get(api_endpoint, params=payload, timeout=90)
    response.raise_for_status() 
    
    return response.text