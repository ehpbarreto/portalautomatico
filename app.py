import os
import re
import time
import html
import requests
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

MAX_TOTAL_NOTICIAS = 8
titulos_usados = set()
links_usados = set()

fontes = [
    {"url": "https://g1.globo.com/rj/norte-fluminense/", "categoria": "Norte Fluminense", "auto": True, "limite": 3},
    {"url": "https://g1.globo.com/rj/regiao-dos-lagos/", "categoria": "Região dos Lagos", "auto": True, "limite": 3},

    {"url": "https://macae.rj.gov.br/noticias", "categoria": "Macaé", "auto": False, "limite": 3},
    {"url": "https://www.riodasostras.rj.gov.br/noticias/", "categoria": "Rio das Ostras", "auto": False, "limite": 3},
    {"url": "https://www.sjb.rj.gov.br/site/noticias", "categoria": "São João da Barra", "auto": False, "limite": 3},
    {"url": "https://www.campos.rj.gov.br/ultimas-noticias.php", "categoria": "Campos", "auto": False, "limite": 3},
    {"url": "https://www.rj.gov.br/noticias", "categoria": "Estado do RJ", "auto": False, "limite": 2},

    {"url": "https://ge.globo.com/", "categoria": "Esporte", "auto": True, "limite": 2},
    {"url": "https://jovempan.com.br/noticias/politica", "categoria": "Política", "auto": True, "limite": 2},
    {"url": "https://www.infomoney.com.br/ultimas-noticias/", "categoria": "Economia", "auto": True, "limite": 2},
    {"url": "https://www.metropoles.com/entretenimento", "categoria": "Entretenimento", "auto": True, "limite": 2},
    {"url": "https://www.cnnbrasil.com.br/internacional/", "categoria": "Mundo", "auto": True, "limite": 2},
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

    link_lower = link.lower()

    bloqueios = [
        "facebook.com", "instagram.com", "twitter.com", "x.com",
        "youtube.com", "whatsapp", "mailto:", "tel:", "#",
        "login", "cadastro", "assinatura", "newsletter",
        "privacy", "politica-de-privacidade", "termos"
    ]

    if any(b in link_lower for b in bloqueios):
        return False

    if link_lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf", ".mp4")):
        return False

    return link.startswith("http")


def titulo_valido(titulo):
    if not titulo:
        return False

    t = titulo.lower().strip()

    if len(t) < 12:
        return False

    ruins = [
        "menu", "buscar", "pesquisar", "compartilhar", "facebook",
        "instagram", "youtube", "newsletter", "publicidade",
        "home", "início", "politica de privacidade"
    ]

    if any(r in t for r in ruins):
        return False

    return True


def coletar_links_da_pagina(fonte):
    url = fonte["url"]

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
    except Exception as e:
        print("Erro ao abrir fonte:", url, e)
        return []

    encontrados = []

    for a in soup.find_all("a", href=True):
        titulo = limpar_texto(a.get_text(" ", strip=True))
        link = urljoin(url, a.get("href"))

        if not url_valida(link):
            continue

        if not titulo_valido(titulo):
            continue

        chave_link = link.split("?")[0].strip().lower()
        chave_titulo = titulo.lower().strip()

        if chave_link in links_usados:
            continue

        if chave_titulo in titulos_usados:
            continue

        links_usados.add(chave_link)
        titulos_usados.add(chave_titulo)

        encontrados.append({
            "titulo": titulo,
            "link": link,
            "categoria": fonte["categoria"],
            "auto": fonte["auto"]
        })

        if len(encontrados) >= fonte["limite"]:
            break

    print(f"Encontradas {len(encontrados)} notícias em {fonte['categoria']}")
    return encontrados


def extrair_conteudo(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
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
                if len(texto) > 200:
                    candidatos.append(texto)

        if candidatos:
            candidatos.sort(key=len, reverse=True)
            return candidatos[0][:4500], imagem

        texto_total = limpar_texto(soup.get_text(" ", strip=True))
        return texto_total[:3500], imagem

    except Exception as e:
        print("Erro ao extrair conteúdo:", url, e)
        return "", None


def gerar_texto(titulo_original, conteudo_base, categoria):
    prompt = f"""
Você é redator de um portal de notícias brasileiro.

Crie uma matéria jornalística em português do Brasil.

Categoria: {categoria}
Título original: {titulo_original}

Conteúdo-base:
{conteudo_base}

Regras:
- Escreva 100% em português do Brasil.
- Crie uma manchete nova e jornalística.
- Não use as palavras TITULO, CATEGORIA, TAGS ou FONTE.
- Não inclua link no texto.
- Não invente fatos.
- Se o conteúdo estiver fraco, escreva uma matéria curta e conservadora.
- Máximo de 350 palavras.
- Use HTML simples com parágrafos <p>...</p>.

Formato obrigatório:

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
    conteudo = re.sub(r"https?://\S+", "", conteudo)

    return manchete, conteudo.strip()


def buscar_categoria(nome):
    try:
        resp = requests.get(
            f"{WP_URL}/wp-json/wp/v2/categories",
            auth=(WP_USERNAME, WP_APP_PASSWORD),
            params={"search": nome, "per_page": 20},
            timeout=20
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
            timeout=20
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
        resp = requests.get(url_img, headers=HEADERS, timeout=15)
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
            timeout=20
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
            timeout=20
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

    try:
        response = requests.post(
            f"{WP_URL}/wp-json/wp/v2/posts",
            auth=(WP_USERNAME, WP_APP_PASSWORD),
            json=payload,
            timeout=20
        )

        print("Publicação:", response.status_code, response.text[:200])

    except Exception as e:
        print("ERRO AO PUBLICAR:", e)
        time.sleep(3)


def processar_noticia(item):
    titulo_original = item["titulo"]
    link = item["link"]
    categoria = item["categoria"]
    auto = item["auto"]

    print("Processando:", titulo_original)
    print("Link:", link)

    conteudo_base, imagem = extrair_conteudo(link)

    if len(conteudo_base) < 80:
        conteudo_base = titulo_original

    texto_ia = gerar_texto(titulo_original, conteudo_base, categoria)
    manchete, conteudo_final = limpar_resposta_ia(texto_ia)

    if not manchete:
        manchete = titulo_original

    if len(conteudo_final) < 60:
        print("Texto muito curto. Pulando.")
        return False

    if ja_existe_no_wordpress(manchete):
        print("Já existe no WordPress. Pulando.")
        return False

    imagem_id = upload_imagem(imagem) if imagem else None

    publicar(manchete, conteudo_final, categoria, imagem_id, auto)
    return True


def main():
    total = 0

    for fonte in fontes:
        if total >= MAX_TOTAL_NOTICIAS:
            break

        print("Fonte:", fonte["url"])

        itens = coletar_links_da_pagina(fonte)

        for item in itens:
            if total >= MAX_TOTAL_NOTICIAS:
                break

            sucesso = processar_noticia(item)

            if sucesso:
                total += 1
                print("Total publicado/processado:", total)

    print("Finalizado. Total:", total)


if __name__ == "__main__":
    main()
