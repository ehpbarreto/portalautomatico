import os
import requests
import feedparser
from bs4 import BeautifulSoup
from openai import OpenAI

WP_URL = os.getenv("WP_URL")
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

HEADERS = {"User-Agent": "Mozilla/5.0"}

titulos_usados = set()

# =========================
# FEEDS
# =========================

feeds = [
    # ===== AUTOMÁTICO =====
    {"url": "https://g1.globo.com/rss/g1/", "categoria": "Brasil", "auto": True},
    {"url": "https://g1.globo.com/economia/rss/g1/", "categoria": "Economia", "auto": True},
    {"url": "https://g1.globo.com/mundo/rss/g1/", "categoria": "Mundo", "auto": True},
    {"url": "https://ge.globo.com/rss/ge/", "categoria": "Esporte", "auto": True},
    {"url": "https://rss.uol.com.br/feed/entretenimento.xml", "categoria": "Entretenimento", "auto": True},

    # ===== REGIONAIS (RASCU NHO) =====
    {"url": "https://www.noticiasmacae.com/feed", "categoria": "Macaé", "auto": False},
    {"url": "https://cliquediario.com.br/feed", "categoria": "Região", "auto": False},
    {"url": "https://riodasostrasjornal.com/feed", "categoria": "Rio das Ostras", "auto": False},
    {"url": "https://saojoaodabarranews.com.br/feed", "categoria": "São João da Barra", "auto": False}
]

# =========================
# EXTRAIR TEXTO + IMAGEM
# =========================

def extrair_conteudo(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")

        # texto
        texto = soup.get_text(" ", strip=True)[:4000]

        # imagem
        img = None
        img_tag = soup.find("meta", property="og:image")
        if img_tag:
            img = img_tag.get("content")

        return texto, img

    except:
        return "", None

# =========================
# IA
# =========================

def gerar_texto(titulo, conteudo):
    prompt = f"""
Você é um jornalista brasileiro.

Crie uma notícia profissional.

Base:
{titulo}

Conteúdo:
{conteudo}

Regras:
- Português do Brasil
- Criar novo título
- Não inventar fatos
- Não colocar fonte
- Máximo 300 palavras

Formato:

TITULO: ...
TEXTO:
<p>...</p>
<p>...</p>
"""

    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )

    return resp.output_text

# =========================
# LIMPAR
# =========================

def limpar(texto):
    titulo = ""
    conteudo = []

    for linha in texto.splitlines():
        if linha.startswith("TITULO:"):
            titulo = linha.replace("TITULO:", "").strip()
        elif linha.startswith("TEXTO:"):
            continue
        else:
            if "Fonte:" not in linha:
                conteudo.append(linha)

    return titulo, "\n".join(conteudo)

# =========================
# UPLOAD IMAGEM
# =========================

def upload_imagem(url_img):
    try:
        img_data = requests.get(url_img).content

        media = requests.post(
            f"{WP_URL}/wp-json/wp/v2/media",
            auth=(WP_USERNAME, WP_APP_PASSWORD),
            files={"file": ("imagem.jpg", img_data)}
        )

        if media.status_code in [200, 201]:
            return media.json()["id"]
    except:
        pass

    return None

# =========================
# PUBLICAR
# =========================

def publicar(titulo, conteudo, categoria, imagem_id, auto):
    status = "publish" if auto else "draft"

    payload = {
        "title": titulo,
        "content": conteudo,
        "status": status
    }

    if imagem_id:
        payload["featured_media"] = imagem_id

    requests.post(
        f"{WP_URL}/wp-json/wp/v2/posts",
        auth=(WP_USERNAME, WP_APP_PASSWORD),
        json=payload
    )

# =========================
# MAIN
# =========================

def main():
    for feed in feeds:
        data = feedparser.parse(feed["url"])

        for entry in data.entries[:2]:
    titulo_original = entry.title
    link = entry.link

    if titulo_original in titulos_usados:
        continue

    titulos_usados.add(titulo_original)

    print("Processando:", titulo_original)

    conteudo, imagem = extrair_conteudo(link)

    if len(conteudo) < 100:
        conteudo = titulo_original

    texto = gerar_texto(titulo_original, conteudo)

    titulo, conteudo_final = limpar(texto)

    imagem_id = None
    if imagem:
        imagem_id = upload_imagem(imagem)

    publicar(
        titulo,
        conteudo_final,
        feed["categoria"],
        imagem_id,
        feed["auto"]
    )

if __name__ == "__main__":
    main()
    main()
