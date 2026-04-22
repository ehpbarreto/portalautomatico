import os
import requests
import feedparser
from openai import OpenAI

WP_URL = os.getenv("WP_URL")
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

feeds = [
    "https://news.google.com/rss/search?q=Campos+dos+Goytacazes",
    "https://news.google.com/rss/search?q=Macae",
    "https://news.google.com/rss/search?q=Regiao+dos+Lagos"
]

def coletar_noticias():
    noticias = []
    for feed_url in feeds:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:2]:
            noticias.append({
                "titulo": entry.get("title", ""),
                "link": entry.get("link", "")
            })
    return noticias[:3]

def gerar_texto(noticia):
    prompt = f"""
    Escreva uma notícia COMPLETAMENTE em português do Brasil.

    Traduza o título se estiver em outro idioma.

    Base:
    Título original: {noticia['titulo']}
    Link: {noticia['link']}

    Regras:
    - Texto 100% em português do Brasil
    - Nunca misturar inglês
    - Tom jornalístico profissional
    - Máximo 400 palavras
    - Não inventar fatos
    - Criar um NOVO título em português
    - No final colocar: Fonte: {noticia['link']}
    """

    Regras:
    - Português do Brasil
    - Tom jornalístico
    - Máximo 400 palavras
    - Não inventar fatos
    - No final colocar: Fonte: {noticia['link']}
    """

    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )

    return resp.output_text

def publicar_wp(titulo, conteudo):
    url = f"{WP_URL}/wp-json/wp/v2/posts"

    response = requests.post(
        url,
        auth=(WP_USERNAME, WP_APP_PASSWORD),
        json={
            "title": titulo,
            "content": conteudo,
            "status": "draft"
        }
    )

    print(response.status_code)

def main():
    noticias = coletar_noticias()

    for noticia in noticias:
        texto = gerar_texto(noticia)
        publicar_wp(noticia["titulo"], texto)

if __name__ == "__main__":
    main()
