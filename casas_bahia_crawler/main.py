import pandas as pd
from crawler_api_casasbahia import buscar_produtos_casasbahia_api
from extracao_casasbahia import extrair_dados_produtos_html

def main():
    termo = "celular samsung"
    API_KEY = "0776b459cea0b986e5e833ca3a1ea92a1d35957e" # Cole sua chave da Universal Scraper API
    
    print(f"Iniciando crawler das Casas Bahia para o termo: '{termo}' (Via Universal Scraper API)")
    
    try:
        # 1. Requisição via API
        html_content = buscar_produtos_casasbahia_api(termo, API_KEY)
        
        # 2. Extração
        dados = extrair_dados_produtos_html(html_content)
        
        # 3. Exportação e Debug
        if dados:
            df = pd.DataFrame(dados)
            arquivo_saida = f"casas_bahia_{termo.replace(' ', '_')}.csv"
            df.to_csv(arquivo_saida, index=False, encoding='utf-8')
            print(f"Sucesso! {len(dados)} produtos salvos em '{arquivo_saida}'.")
        else:
            print("Nenhum dado pôde ser extraído.")
            # Salva o HTML para você inspecionar se a API retornou o site bloqueado ou a página certa
            arquivo_debug = "debug_casasbahia.html"
            with open(arquivo_debug, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"O HTML cru foi salvo como '{arquivo_debug}' para análise de seletores.")
            
    except Exception as e:
        print(f"Erro durante a execução da requisição: {e}")

if __name__ == "__main__":
    main()