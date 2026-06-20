import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager  # Import webdriver_manager
import urllib
from src.logging import logger

def chrome_browser_options():
    logger.debug("Setting Chrome browser options")
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")  # Opzionale, utile in alcuni ambienti
    options.add_argument("window-size=794x1123")  # A4 @ 96dpi (210x297mm)
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-translate")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-logging")
    options.add_argument("--disable-autofill")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-animations")
    options.add_argument("--disable-cache")
    options.add_argument("--incognito")
    options.add_argument("--headless=new")  # Aggiunto headless per evitare che la finestra del browser appaia
    options.add_argument("--allow-file-access-from-files")  # Consente l'accesso ai file locali
    options.add_argument("--disable-web-security")         # Disabilita la sicurezza web
    logger.debug("Using Chrome in incognito mode")
    
    return options

def init_browser() -> webdriver.Chrome:
    try:
        options = chrome_browser_options()
        # Allow overriding Chrome binary location with environment variable CHROME_BINARY
        chrome_binary = os.environ.get("CHROME_BINARY")
        if chrome_binary:
            logger.debug(f"Using CHROME_BINARY from env: {chrome_binary}")
            options.binary_location = chrome_binary

        # 1. Try finding a cached driver manually to avoid webdriver_manager hanging on network issues
        import glob
        # Match both: .../chromedriver.exe and .../chromedriver-win32/chromedriver.exe
        wdm_patterns = [
            os.path.expanduser("~/.wdm/drivers/chromedriver/win64/**/chromedriver.exe"),
            os.path.expanduser("~/.wdm/drivers/chromedriver/**/chromedriver.exe"),
            "C:/Users/*/.wdm/drivers/chromedriver/**/chromedriver.exe",
        ]
        matches = []
        for pat in wdm_patterns:
            matches.extend(glob.glob(pat, recursive=True))
        # De-duplicate
        matches = list(set(matches))
        driver = None

        if matches:
            try:
                # Prefer newest by mtime
                latest_driver = sorted(matches, key=os.path.getmtime)[-1]
                logger.info(f"Using locally cached chromedriver: {latest_driver}")
                driver = webdriver.Chrome(service=ChromeService(latest_driver), options=options)
            except Exception as e_local:
                logger.warning(f"Failed to use locally cached driver: {e_local}")

        # 2. Fallback to webdriver_manager if no cached driver found or it failed
        # Only try this if explicitly enabled (env var) to avoid network hangs
        if not driver and os.environ.get("ENABLE_WDM_FALLBACK", "0") == "1":
            try:
                logger.info("Attempting to use webdriver_manager...")
                driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
            except Exception as e_manager:
                logger.warning(f"webdriver_manager failed: {e_manager}. Trying without it...")
                driver = webdriver.Chrome(options=options)

        # 3. Last fallback: try without service (use system PATH)
        if not driver:
            try:
                logger.info("Trying chromedriver from system PATH...")
                driver = webdriver.Chrome(options=options)
            except Exception as e_final:
                logger.error(f"All Chrome init attempts failed: {e_final}")
                raise

        logger.debug("Chrome browser initialized successfully.")
        return driver
    except Exception as e:
        logger.error(f"Failed to initialize browser: {str(e)}")
        # Provide a helpful hint about setting CHROME_BINARY on Windows
        hint = "\nHint: ensure Google Chrome is installed and accessible. On Windows you can set the CHROME_BINARY env var to the chrome.exe path, e.g. C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
        raise RuntimeError(f"Failed to initialize browser: {str(e)}{hint}")



def HTML_to_PDF(html_content, driver):
    """
    Converte una stringa HTML in un PDF e restituisce il PDF come stringa base64.

    :param html_content: Stringa contenente il codice HTML da convertire.
    :param driver: Istanza del WebDriver di Selenium.
    :return: Stringa base64 del PDF generato.
    :raises ValueError: Se l'input HTML non è una stringa valida.
    :raises RuntimeError: Se si verifica un'eccezione nel WebDriver.
    """
    # Validazione del contenuto HTML
    if not isinstance(html_content, str) or not html_content.strip():
        raise ValueError("Il contenuto HTML deve essere una stringa non vuota.")

    # Inject centering-safe CSS to avoid left/right offset issues in PDF.
    # The original templates use `body { max-width: 700px; margin: 0 auto; }`
    # which centers body within the viewport. But Chrome's printToPDF
    # uses a different scaling model, causing the centered body to appear
    # offset in the PDF. We override body width to fill the printable area.
    #
    # We append the CSS to the existing <style> blocks (or before </head>).
    centering_css = """
<style id="buping-pdf-centering-fix">
  @page { size: A4; margin: 0; }
  html, body { width: 100%; max-width: none; margin: 0 !important; padding: 0 !important; box-sizing: border-box; }
  body { padding: 16px !important; }
</style>
"""
    if "</head>" in html_content:
        html_content = html_content.replace("</head>", centering_css + "</head>", 1)
    elif "<head>" in html_content:
        html_content = html_content.replace("<head>", "<head>" + centering_css, 1)
    else:
        # No head tag — inject one before <body>
        if "<body" in html_content:
            html_content = html_content.replace("<body", centering_css + "<body", 1)
        else:
            html_content = centering_css + html_content

    # Codifica l'HTML in un URL di tipo data
    encoded_html = urllib.parse.quote(html_content)
    data_url = f"data:text/html;charset=utf-8,{encoded_html}"

    try:
        driver.get(data_url)
        # Attendi che la pagina si carichi completamente
        time.sleep(2)  # Potrebbe essere necessario aumentare questo tempo per HTML complessi

        # Esegue il comando CDP per stampare la pagina in PDF
        pdf_base64 = driver.execute_cdp_cmd("Page.printToPDF", {
            "printBackground": True,          # Includi lo sfondo nella stampa
            "landscape": False,               # Stampa in verticale (False per ritratto)
            "paperWidth": 8.27,               # Larghezza del foglio in pollici (A4)
            "paperHeight": 11.69,             # Altezza del foglio in pollici (A4)
            "marginTop": 0.5,                  # Margine superiore in pollici (~1.27 cm)
            "marginBottom": 0.5,               # Margine inferiore in pollici
            "marginLeft": 0.5,                 # Margine sinistro in pollici
            "marginRight": 0.5,                # Margine destro in pollici
            "displayHeaderFooter": False,      # Non visualizzare intestazioni e piè di pagina
            "preferCSSPageSize": True,         # Preferire le dimensioni della pagina CSS
            "generateDocumentOutline": False,  # Non generare un sommario del documento
            "generateTaggedPDF": False,        # Non generare PDF taggato
            "transferMode": "ReturnAsBase64"   # Restituire il PDF come stringa base64
        })
        return pdf_base64['data']
    except Exception as e:
        logger.error(f"Si è verificata un'eccezione WebDriver: {e}")
        raise RuntimeError(f"Si è verificata un'eccezione WebDriver: {e}")
