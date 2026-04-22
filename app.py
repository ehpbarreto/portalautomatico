import os
import re
import html
import requests
import feedparser
from bs4 import BeautifulSoup
from openai import OpenAI

WP_URL = os.getenv("WP_URL")
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

feeds = [
    "https://news.google.com/rss/search?q=Campos+dos+Goytacazes+when:7d&hl=pt-BR&gl=BR&ceid=BR:pt-419",
    "https://news.google.com/rss/search?q=Macae+when:7d&hl=pt-BR&gl=BR&ceid=BR:pt-419",
    "https://news.google.com/rss/search?q=Regiao+dos+Lagos+when:7d&hl=pt-BR&gl=BR&ceid=BR:pt-419"
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


def limpar_texto(texto):
    if not texto:
        return ""
    texto = html.unescape(texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def coletar_noticias():
    noticias = []
    vistos = set()

    for feed_url in feeds:
        feed = feedparser.parse(feed_url)

        for entry in feed.entries[:5]:
            titulo = limpar_texto(entry.get("title", ""))
            link = entry.get("link", "")

            if not titulo or not link:
                continue

            if len(titulo) < 20:
                continue

            chave = titulo.lower().strip()
            if chave in vistos:
                continue

            vistos.add(chave)

            noticias.append({
                "titulo": titulo,
                "link": link
            })

    return noticias[:3]


def extrair_texto_html(html_text):
    soup = BeautifulSoup(html_text, "lxml")

    for tag in soup(["script", "style", "noscript", "header", "footer", "svg", "form"]):
        tag.decompose()

    candidatos = []

    for seletor in [
        "article",
        "main",
        "[role='main']",
        ".post-content",
        ".entry-content",
        ".article-content",
        ".materia-conteudo",
        ".news-content",
        ".content"
    ]:
        encontrados = soup.select(seletor)
        for item in encontrados:
            texto = limpar_texto(item.get_text(" ", strip=True))
            if len(texto) > 300:
                candidatos.append(texto)

    if candidatos:
        candidatos.sort(key=len, reverse=True)
        return candidatos[0][:5000]

    texto_total = limpar_texto(soup.get_text(" ", strip=True))
    return texto_total[:5000]


def baixar_conteudo_noticia(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return extrair_texto_html(resp.text)
    except Exception as e:
        print(f"Erro ao baixar conteúdo da notícia: {url} -> {e}")
        return ""


def ja_existe_post_semelhante(titulo):
    try:
        url = f"{WP_URL}/wp-json/wp/v2/posts"
        resp = requests.get(
            url,
            auth=(WP_USERNAME, WP_APP_PASSWORD),
            params={"search": titulo, "per_page": 5},
            timeout=20
        )
        if resp.status_code != 200:
            return False

        posts = resp.json()
        titulo_normalizado = titulo.lower().strip()

        for post in posts:
            titulo_wp = (
                post.get("title", {})
                .get("rendered", "")
                .strip()
                .lower()
            )
            if titulo_wp == titulo_normalizado:
                return True

        return False
    except Exception as e:
        print(f"Erro ao verificar duplicidade: {e}")
        return False


def gerar_texto(noticia, conteudo_base):
    prompt = f"""
Você é um redator profissional de um portal de notícias brasileiro regional.

Seu trabalho é criar uma matéria em português do Brasil com base em uma notícia real.

DADOS:
- Manchete original: {noticia['titulo']}
- Link da fonte: {noticia['link']}

TRECHO EXTRAÍDO DA FONTE:
{conteudo_base}

REGRAS OBRIGATÓRIAS:
- Escreva 100% em português do Brasil.
- Nunca escreva em inglês.
- Se a manchete original estiver em outro idioma, traduza o sentido e reescreva naturalmente.
- Crie um NOVO título em português, forte e jornalístico.
- Não copie literalmente a manchete original.
- Não invente fatos.
- Use apenas as informações claramente sustentadas pela manchete e pelo trecho fornecido.
- Se o conteúdo extraído estiver fraco ou insuficiente, faça um texto curto e conservador.
- Linguagem natural, humana e jornalística.
- Máximo de 450 palavras.
- Gere também:
  - uma categoria
  - 3 a 5 tags

FORMATO EXATO DA RESPOSTA:

TITULO: ...
CATEGORIA: ...
TAGS: tag1, tag2, tag3
TEXTO:
<p>Primeiro parágrafo...</p>
<p>Segundo parágrafo...</p>

<p><strong>Fonte:</strong> {noticia['link']}</p>
"""

    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )
    return resp.output_text


def extrair_partes(texto):
    titulo = ""
    categoria = "Geral"
    tags = []
    conteudo = texto

    linhas = texto.splitlines()

    for linha in linhas:
        linha_limpa = linha.strip()

        if linha_limpa.startswith("TITULO:"):
            titulo = linha_limpa.replace("TITULO:", "", 1).strip()
        elif linha_limpa.startswith("CATEGORIA:"):
            categoria = linha_limpa.replace("CATEGORIA:", "", 1).strip() or "Geral"
        elif linha_limpa.startswith("TAGS:"):
            bruto = linha_limpa.replace("TAGS:", "", 1).strip()
            tags = [t.strip() for t in bruto.split(",") if t.strip()]

    return titulo, categoria, tags, conteudo


def buscar_categoria_por_nome(nome):
    try:
        url = f"{WP_URL}/wp-json/wp/v2/categories"
        resp = requests.get(
            url,
            auth=(WP_USERNAME, WP_APP_PASSWORD),
            params={"search": nome, "per_page": 20},
            timeout=20
        )
        if resp.status_code != 200:
            return None

        for item in resp.json():
            if item.get("name", "").strip().lower() == nome.strip().lower():
                return item["id"]
        return None
    except Exception as e:
        print(f"Erro ao buscar categoria: {e}")
        return None


def criar_categoria(nome):
    categoria_id = buscar_categoria_por_nome(nome)
    if categoria_id:
        return categoria_id

    try:
        url = f"{WP_URL}/wp-json/wp/v2/categories"
        resp = requests.post(
            url,
            auth=(WP_USERNAME, WP_APP_PASSWORD),
            json={"name": nome},
            timeout=20
        )

        if resp.status_code in [200, 201]:
            return resp.json()["id"]

        return None
    except Exception as e:
        print(f"Erro ao criar categoria: {e}")
        return None


def buscar_tag_por_nome(nome):
    try:
        url = f"{WP_URL}/wp-json/wp/v2/tags"
        resp = requests.get(
            url,
            auth=(WP_USERNAME, WP_APP_PASSWORD),
            params={"search": nome, "per_page": 20},
            timeout=20
        )
        if resp.status_code != 200:
            return None

        for item in resp.json():
            if item.get("name", "").strip().lower() == nome.strip().lower():
                return item["id"]
        return None
    except Exception as e:
        print(f"Erro ao buscar tag: {e}")
        return None


def criar_tag(nome):
    tag_id = buscar_tag_por_nome(nome)
    if tag_id:
        return tag_id

    try:
        url = f"{WP_URL}/wp-json/wp/v2/tags"
        resp = requests.post(
            url,
            auth=(WP_USERNAME, WP_APP_PASSWORD),
            json={"name": nome},
            timeout=20
        )

        if resp.status_code in [200, 201]:
            return resp.json()["id"]

        return None
    except Exception as e:
        print(f"Erro ao criar tag: {e}")
        return None


def publicar_wp(titulo, conteudo, categoria, tags):
    categoria_id = criar_categoria(categoria)
    tag_ids = []

    for tag in tags[:5]:
        tag_id = criar_tag(tag)
        if tag_id:
            tag_ids.append(tag_id)

    payload = {
        "title": titulo,
        "content": conteudo,
        "status": "draft",
        "tags": tag_ids
    }

    if categoria_id:
        payload["categories"] = [categoria_id]

    url = f"{WP_URL}/wp-json/wp/v2/posts"

    resp = requests.post(
        url,
        auth=(WP_USERNAME, WP_APP_PASSWORD),
        json=payload,
        timeout=30
    )

    print("Publicação:", resp.status_code, resp.text[:300])


def main():
    noticias = coletar_noticias()

    for noticia in noticias:
        print(f"Processando: {noticia['titulo']}")

        conteudo_base = baixar_conteudo_noticia(noticia["link"])

        if len(conteudo_base) < 200:
            print("Conteúdo fraco, pulando.")
            continue

        texto = gerar_texto(noticia, conteudo_base)
        titulo, categoria, tags, conteudo = extrair_partes(texto)

        if not titulo:
            print("Sem título gerado, pulando.")
            continue

        if ja_existe_post_semelhante(titulo):
            print("Post semelhante já existe, pulando.")
            continue

        publicar_wp(titulo, conteudo, categoria, tags)


if __name__ == "__main__":
    main()
