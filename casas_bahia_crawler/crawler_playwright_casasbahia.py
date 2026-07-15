import asyncio
from playwright.async_api import async_playwright

async def iniciar_playwright():
    """Inicializa o browser sem as credenciais de proxy, apenas com configs base."""
    p = await async_playwright().start()
    browser = await p.chromium.launch(
        headless=False, 
        args=["--disable-blink-features=AutomationControlled"]
    )
    
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080}
    )
    return p, browser, context

async def buscar_produtos_casasbahia(page, termo_busca):
    """Navega até a página injetando a camuflagem nativamente."""
    
    # Camuflagem nativa: apaga a "identidade" de robô do navegador
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    termo_formatado = termo_busca.replace(' ', '-')
    url = f"https://www.casasbahia.com.br/{termo_formatado}/b"
    
    print(f"Acessando: {url} (com bypass nativo)")
    await page.goto(url, timeout=60000, wait_until="domcontentloaded")
    
    # Pausa para carregar
    await page.wait_for_timeout(3000)
    
    # Scroll para forçar o carregamento dinâmico
    for _ in range(8):
        await page.mouse.wheel(0, 800)
        await page.wait_for_timeout(1000)
        
    return page