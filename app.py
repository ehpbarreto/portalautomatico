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
Você é um redator de portal de notícias brasileiro.

Sua tarefa é escrever uma matéria jornalística em português do Brasil com base em uma manchete encontrada online.

DADOS DE ENTRADA:
- Manchete original: {noticia['titulo']}
- Link de referência: {noticia['link']}

INSTRUÇÕES OBRIGATÓRIAS:
- Escreva TUDO em português do Brasil.
- Não use inglês em nenhuma parte da resposta.
- Se a manchete original estiver em inglês, traduza o sentido e reescreva em português.
- Crie um novo título em português, natural e jornalístico.
- Não copie a manchete original literalmente.
- Não invente fatos que não estejam claramente indicados no tema.
- Escreva de forma objetiva, como portal de notícias.
- Máximo de 400 palavras.
- Ao final, escreva: Fonte: {noticia['link']}

FORMATO DA RESPOSTA:
Título: [crie um título em português]
Texto: [escreva a matéria completa em português]
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
