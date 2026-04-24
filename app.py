import os
import re
import time
import html
import requests
from urllib.parse import urljoin
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

MAX_TOTAL_NOTICIAS = 3
PAUSA_ENTRE_POSTS = 90

titulos_usados = set()
links_usados = set()

fontes = [
    {"url": "https://g1.globo.com/rj/norte-fluminense/", "categoria": "Norte Fluminense", "auto": True, "limite": 3},
    {"url": "https://g1.globo.com/rj/regiao-dos-lagos/", "categoria": "Região dos Lagos", "auto": True, "limite": 3},

    {"url": "https://macae.rj.gov.br/noticias", "categoria": "Macaé", "auto": False, "limite": 3},
    {"url": "https://www.riodasostras.rj.gov.br/noticias/", "categoria": "Rio das Ostras", "auto": False, "limite": 3},
    {"url": "https://www.sjb.rj.gov.br/site/noticias", "categoria": "São João da Barra", "auto": False, "limite": 3},
    {"url": "https://www.campos.rj.gov.br/ultimas-noticias.php", "categoria": "Campos", "auto": False, "limite": 3},

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
        "privacy", "politica-de-privacidade", "termos",
        "lps.infomoney", "docs.google.com", "leismunicipais",
        "planner", "formulario", "formulário", "mapa-do-site",
        "servicosdigitais", "dados-municipais", "mapas-municipais",
        "orgaosmunicipais", "acessibilidade"
    ]

    for bloqueio in bloqueios:
        if bloqueio in link_lower:
            return False

    if link_lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf", ".mp4")):
        return False

    return link.startswith("http")


def titulo_valido(titulo):
    if not titulo:
        return False

    t = titulo.lower().strip()

    if len(t) < 18:
        return False

    ruins = [
        "menu", "buscar", "pesquisar", "compartilhar", "facebook",
        "instagram", "youtube", "newsletter", "publicidade",
        "home", "início", "politica de privacidade",
        "pular para o conteúdo", "últimas notícias", "ultimas noticias",
        "bom dia", "inter tv", "rota inter", "inter tv rural",
        "acessibilidade", "contatos", "órgãos", "orgaosmunicipais",
        "vídeos", "videos", "mapa do site", "cadastro",
        "licitações", "licitacoes", "planner gratuito",
        "dinheiro diário", "metropoles.com", "cnnbrasil.com.br",
        "região dos lagos", "norte fluminense", "aplicação visual",
        "estrutura pmm", "concursos públicos", "alto contraste",
        "poder executivo", "ir para a busca", "lista de leis municipais",
        "avisos e editais", "cadastro de fornecedores",
        "serviços digitais", "servicos digitais", "dados municipais",
        "mapas municipais", "horário eleitoral", "jovem pan contra o crime",
        "minhas finanças", "cotações e indicadores", "viagem & gastronomia",
        "distrito federal", "brasil/política/economia"
    ]

    for ruim in ruins:
        if ruim in t:
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

        candidatos = []

        seletores = [
            "article", "main", "[role='main']",
            ".mc-article-body", ".content-text", ".entry-content",
            ".post-content", ".article-content", ".news-content",
            ".materia-conteudo", ".texto", ".conteudo"
        ]

        for seletor in seletores:
            for item in soup.select(seletor):
                texto = limpar_texto(item.get_text(" ", strip=True))
                if len(texto) > 200:
                    candidatos.append(texto)

        if candidatos:
            candidatos.sort(key=len, reverse=True)
            return candidatos[0][:4500]

        texto_total = limpar_texto(soup.get_text(" ", strip=True))
        return texto_total[:3500]

    except Exception as e:
        print("Erro ao extrair conteúdo:", url, e)
        return ""


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
            wp_title = BeautifulSoup(
                post.get("title", {}).get("rendered", ""),
                "lxml"
            ).get_text().lower().strip()

            if titulo_limpo == wp_title:
                return True

        return False

    except Exception as e:
        print("Erro ao verificar duplicado:", e)
        return False


def publicar(titulo, conteudo, categoria, auto):
    status = "publish" if auto else "draft"

    payload = {
        "title": titulo,
        "content": conteudo,
        "status": status
    }

    tentativas = 4

    for tentativa in range(tentativas):
        try:
            response = requests.post(
                f"{WP_URL}/wp-json/wp/v2/posts",
                auth=(WP_USERNAME, WP_APP_PASSWORD),
                json=payload,
                timeout=20
            )

            print(f"Tentativa {tentativa + 1}: {response.status_code}")

            if response.status_code in [200, 201]:
                print("Publicado com sucesso")
                return True

            if response.status_code == 429:
                espera = 90
                print(f"Bloqueado por limite 429. Aguardando {espera}s...")
                time.sleep(espera)
                continue

            print("Erro ao publicar:", response.status_code, response.text[:200])
            return False

        except Exception as e:
            print("Erro ao publicar:", e)
            time.sleep(20)

    return False


def processar_noticia(item):
    titulo_original = item["titulo"]
    link = item["link"]
    categoria = item["categoria"]
    auto = item["auto"]

    print("Processando:", titulo_original)
    print("Link:", link)

    conteudo_base = extrair_conteudo(link)

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

    return publicar(manchete, conteudo_final, categoria, auto)


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

            time.sleep(PAUSA_ENTRE_POSTS)

    print("Finalizado. Total:", total)


if __name__ == "__main__":
    main()
