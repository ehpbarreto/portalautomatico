import os
import re
import time
import html
import requests
import feedparser
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from openai import OpenAI

WP_URL = os.getenv("WP_URL")
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

titulos_usados = set()
links_usados = set()

fontes = [
    {"url": "https://g1.globo.com/rj/norte-fluminense/", "categoria": "Norte Fluminense", "auto": True, "limite": 3},
    {"url": "https://g1.globo.com/rj/regiao-dos-lagos/", "categoria": "Região dos Lagos", "auto": True, "limite": 3},

    {"url": "https://www.rj.gov.br/noticias", "categoria": "Estado do RJ", "auto": False, "limite": 3},
    {"url": "https://macae.rj.gov.br/noticias", "categoria": "Macaé", "auto": False, "limite": 3},
    {"url": "https://www.riodasostras.rj.gov.br/noticias/", "categoria": "Rio das Ostras", "auto": False, "limite": 3},
    {"url": "https://www.sjb.rj.gov.br/site/noticias", "categoria": "São João da Barra", "auto": False, "limite": 3},
    {"url": "https://www.campos.rj.gov.br/ultimas-noticias.php", "categoria": "Campos", "auto": False, "limite": 3},

    {"url": "https://ge.globo.com/", "categoria": "Esporte", "auto": True, "limite": 3},
    {"url": "https://jovempan.com.br/noticias/politica", "categoria": "Política", "auto": True, "limite": 3},
    {"url": "https://www.infomoney.com.br/ultimas-noticias/", "categoria": "Economia", "auto": True, "limite": 3},
    {"url": "https://www.metropoles.com/entretenimento", "categoria": "Entretenimento", "auto": True, "limite": 3},
    {"url": "https://www.cnnbrasil.com.br/internacional/", "categoria": "Mundo", "auto": True, "limite": 3},
]


def limpar_texto(texto):
    if not texto:
        return ""
    texto = html.unescape(texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def url_valida(link):
    if not link:
        return False

    ignorar = [
        "facebook.com", "instagram.com", "twitter.com", "x.com",
        "youtube.com", "whatsapp", "mailto:", "tel:", "#"
    ]

    link_lower = link.lower()

    if any(i in link_lower for i in ignorar):
        return False

    if link_lower.endswith((".jpg", ".png", ".jpeg", ".webp", ".gif", ".pdf")):
        return False

    return link.startswith("http")


def parece_noticia(url):
    u = url.lower()

    palavras = [
        "noticia", "noticias", "politica", "economia", "internacional",
        "entretenimento", "esporte", "ultimas-noticias", "mundo",
        "rj", "regiao-dos-lagos", "norte-fluminense"
    ]

    return any(p in u for p in palavras)


def coletar_links_da_pagina(fonte):
    url = fonte["url"]
    base_domain = urlparse(url).netloc

    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
    except Exception as e:
        print("Erro ao abrir fonte:", url, e)
        return []

    encontrados = []

    for a in soup.find_all("a", href=True):
        href = a.get("href")
        titulo = limpar_texto(a.get_text(" ", strip=True))
        link = urljoin(url, href)

        if not url_valida(link):
            continue

        # if not parece_noticia(link):
        #     continue

        if len(titulo) < 15:
            continue

        # Evita links externos inúteis, mas permite subdomínios Globo, CNN etc.
        domain = urlparse(link).netloc
        if base_domain.replace("www.", "") not in domain.replace("www.", ""):
            if "globo.com" not in domain and "cnnbrasil.com.br" not in domain:
                continue

        chave = link.split("?")[0].strip().lower()

        if chave in links_usados:
            continue

        links_usados.add(chave)

        encontrados.append({
            "titulo": titulo,
            "link": link,
            "categoria": fonte["categoria"],
            "auto": fonte["auto"]
        })

        if len(encontrados) >= fonte["limite"]:
            break

    return encontrados


def extrair_conteudo(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        for tag in soup(["script", "style", "noscript", "svg", "form", "header", "footer"]):
            tag.decompose()

        imagem = None

        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            imagem = og_img.get("content")

        if not imagem:
            img = soup.find("img")
            if img and img.get("src"):
                imagem = urljoin(url, img.get("src"))

        candidatos = []

        seletores = [
            "article",
            "main",
            "[role='main']",
            ".mc-article-body",
            ".content-text",
            ".entry-content",
            ".post-content",
            ".article-content",
            ".news-content",
            ".materia-conteudo",
            ".texto",
            ".conteudo"
        ]

        for seletor in seletores:
            for item in soup.select(seletor):
                texto = limpar_texto(item.get_text(" ", strip=True))
                if len(texto) > 300:
                    candidatos.append(texto)

        if candidatos:
            candidatos.sort(key=len, reverse=True)
            texto_final = candidatos[0][:5000]
        else:
            texto_final = limpar_texto(soup.get_text(" ", strip=True))[:5000]

        return texto_final, imagem

    except Exception as e:
        print("Erro ao extrair conteúdo:", url, e)
        return "", None


def gerar_texto(titulo_original, conteudo_base, categoria):
    prompt = f"""
Você é redator de um portal de notícias brasileiro.

Crie uma matéria jornalística em português do Brasil com base nas informações abaixo.

CATEGORIA: {categoria}
TÍTULO ORIGINAL: {titulo_original}

CONTEÚDO EXTRAÍDO:
{conteudo_base}

REGRAS:
- Escreva 100% em português do Brasil.
- Crie uma manchete nova, clara e jornalística.
- Não use as palavras TITULO, CATEGORIA, TAGS ou FONTE no texto final.
- Não inclua link, fonte ou referência no final.
- Não invente fatos.
- Se o conteúdo estiver fraco, escreva uma matéria curta e conservadora.
- Máximo de 400 palavras.
- Use parágrafos em HTML simples com <p>...</p>.

FORMATO EXATO:
MANCHETE: ...
TEXTO:
<p>...</p>
<p>...</p>
"""

    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )

    return resp.output_text


def limpar_resposta_ia(texto):
    manchete = ""
    corpo = []
    dentro_texto = False

    for linha in texto.splitlines():
        linha = linha.strip()

        if not linha:
            continue

        if linha.upper().startswith("MANCHETE:"):
            manchete = linha.split(":", 1)[1].strip()
            continue

        if linha.upper().startswith("TEXTO:"):
            dentro_texto = True
            continue

        if linha.upper().startswith(("TITULO:", "TÍTULO:", "CATEGORIA:", "TAGS:", "FONTE:", "FONTES:")):
            continue

        if "http://" in linha or "https://" in linha:
            continue

        if dentro_texto or linha.startswith("<p>"):
            corpo.append(linha)

    conteudo = "\n".join(corpo).strip()

    conteudo = re.sub(r"(?i)\bfonte\s*:.*", "", conteudo)
    conteudo = re.sub(r"https?://\S+", "", conteudo).strip()

    return manchete, conteudo


def buscar_categoria(nome):
    try:
        resp = requests.get(
            f"{WP_URL}/wp-json/wp/v2/categories",
            auth=(WP_USERNAME, WP_APP_PASSWORD),
            params={"search": nome, "per_page": 20},
            timeout=30
        )

        if resp.status_code != 200:
            return None

        for cat in resp.json():
            if cat.get("name", "").strip().lower() == nome.strip().lower():
                return cat["id"]

        return None

    except Exception as e:
        print("Erro ao buscar categoria:", e)
        return None


def criar_categoria(nome):
    existente = buscar_categoria(nome)
    if existente:
        return existente

    try:
        resp = requests.post(
            f"{WP_URL}/wp-json/wp/v2/categories",
            auth=(WP_USERNAME, WP_APP_PASSWORD),
            json={"name": nome},
            timeout=30
        )

        if resp.status_code in [200, 201]:
            return resp.json()["id"]

        print("Erro criando categoria:", resp.status_code, resp.text[:200])
        return None

    except Exception as e:
        print("Erro ao criar categoria:", e)
        return None


def upload_imagem(url_img):
    if not url_img:
        return None

    try:
        resp = requests.get(url_img, headers=HEADERS, timeout=25)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "image/jpeg")

        if "image" not in content_type:
            return None

        media = requests.post(
            f"{WP_URL}/wp-json/wp/v2/media",
            auth=(WP_USERNAME, WP_APP_PASSWORD),
            headers={
                "Content-Disposition": "attachment; filename=noticia.jpg",
                "Content-Type": content_type
            },
            data=resp.content,
            timeout=15
        )

        if media.status_code in [200, 201]:
            return media.json().get("id")

        print("Erro upload imagem:", media.status_code, media.text[:200])
        return None

    except Exception as e:
        print("Erro ao subir imagem:", e)
        return None


def ja_existe_no_wordpress(titulo):
    try:
        resp = requests.get(
            f"{WP_URL}/wp-json/wp/v2/posts",
            auth=(WP_USERNAME, WP_APP_PASSWORD),
            params={"search": titulo, "per_page": 5},
            timeout=30
        )

        if resp.status_code != 200:
            return False

        titulo_limpo = titulo.lower().strip()

        for post in resp.json():
            wp_title = BeautifulSoup(post.get("title", {}).get("rendered", ""), "lxml").get_text().lower().strip()
            if titulo_limpo == wp_title:
                return True

        return False

    except Exception as e:
        print("Erro ao verificar duplicado:", e)
        return False


def publicar(titulo, conteudo, categoria, imagem_id, auto):
    status = "publish" if auto else "draft"

    categoria_id = criar_categoria(categoria)

    payload = {
        "title": titulo,
        "content": conteudo,
        "status": status
    }

    if categoria_id:
        payload["categories"] = [categoria_id]

    if imagem_id:
        payload["featured_media"] = imagem_id

    url = f"{WP_URL}/wp-json/wp/v2/posts"

    try:
        print("Tentando publicar em:", url)
        print("Status desejado:", status)

        response = requests.post(
            url,
            auth=(WP_USERNAME, WP_APP_PASSWORD),
            json=payload,
            timeout=15
        )

        print("Status:", response.status_code)
        print("Resposta:", response.text[:300])

    except Exception as e:
        print("ERRO AO PUBLICAR:", e)
        time.sleep(5)


def processar_noticia(item):
    titulo_original = item["titulo"]
    link = item["link"]
    categoria = item["categoria"]
    auto = item["auto"]

    titulo_check = titulo_original.lower().strip()

    if titulo_check in titulos_usados:
        print("Ignorada por repetição na rodada:", titulo_original)
        return

    titulos_usados.add(titulo_check)

    print("Processando:", titulo_original)
    print("Link:", link)

    conteudo_base, imagem = extrair_conteudo(link)

    if len(conteudo_base) < 80:
        print("Conteúdo fraco. Usando título como base.")
        conteudo_base = titulo_original

    texto_ia = gerar_texto(titulo_original, conteudo_base, categoria)

    manchete, conteudo_final = limpar_resposta_ia(texto_ia)

    if not manchete:
        manchete = titulo_original

    if len(conteudo_final) < 80:
        print("Texto final muito curto. Pulando.")
        return

    if ja_existe_no_wordpress(manchete):
        print("Já existe no WordPress. Pulando:", manchete)
        return

    imagem_id = upload_imagem(imagem) if imagem else None

    publicar(manchete, conteudo_final, categoria, imagem_id, auto)


def main():
    for fonte in fontes:
        print("Fonte:", fonte["url"])

        itens = coletar_links_da_pagina(fonte)

        if not itens:
            print("Nenhum link encontrado nessa fonte.")
            continue

        for item in itens:
            processar_noticia(item)


if __name__ == "__main__":
    main()
