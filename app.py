import streamlit as st
import pdfplumber
import re
import requests
import json
import difflib
import hashlib
import threading
from io import BytesIO

st.set_page_config(
    page_title="PAINEL DO LEILOEIRO PRO",
    page_icon="🐂",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== CONFIG DE LOTE (BATCH) ====================
BATCH_PAGINAS_PADRAO = 5   # páginas de catálogo por chamada ao DeepSeek
BATCH_LOTES_PADRAO = 8     # lotes por chamada ao DeepSeek na geração de conteúdo
QTD_PRE_CARREGAR = 3       # quantos lotes futuros pré-carregar em segundo plano

# ==================== CSS (OTIMIZADO PARA TABLET) ====================
css_code = """
<style>
    #MainMenu {visibility: hidden; display: none;}
    footer {visibility: hidden; display: none;}
    [data-testid="stToolbar"] {display: none;}
    .block-container {padding-top: 1rem; padding-bottom: 1rem;}

    .lote-destaque {
        background: linear-gradient(135deg, #1E3A8A 0%, #3B82F6 100%);
        color: white;
        padding: 16px;
        border-radius: 16px;
        text-align: center;
        font-size: 42px;
        font-weight: bold;
        margin-bottom: 10px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    .ordem-indicador {
        background: #16A34A;
        color: white;
        padding: 10px;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
        margin: 4px 0 10px 0;
        font-size: 18px;
    }
    .animal-info {
        background: #1E293B;
        color: white;
        padding: 12px;
        border-radius: 10px;
        margin: 4px 0;
        border: 1px solid #334155;
        min-height: 75px;
        text-align: center;
    }
    .nome-animal-box {
        background: #0284C7;
        color: white;
        padding: 12px;
        border-radius: 10px;
        margin-bottom: 10px;
        font-size: 22px;
        font-weight: bold;
        text-align: center;
    }
    .gatilho-card {
        background: linear-gradient(90deg, #EC4899 0%, #8B5CF6 100%);
        color: white;
        padding: 12px;
        border-radius: 10px;
        font-size: 16px;
        margin: 5px 0;
        font-weight: bold;
        box-shadow: 0 2px 6px rgba(0,0,0,0.2);
    }
    .abertura-box {
        background: linear-gradient(135deg, #065F46 0%, #047857 100%);
        color: white !important;
        padding: 14px;
        border-radius: 12px;
        margin-bottom: 12px;
        font-size: 18px !important;
        font-weight: bold;
        font-style: italic;
        border: 2px solid #10B981;
    }
    .canta-box {
        background-color: #1E1B4B !important;
        padding: 18px;
        border-radius: 12px;
        margin-bottom: 12px;
        border-left: 6px solid #818CF8;
        color: white !important;
        font-size: 16px;
        line-height: 1.5;
    }
    .parecer-box {
        background-color: #0F172A !important;
        padding: 16px;
        border-radius: 12px;
        margin-bottom: 12px;
        border-left: 6px solid #F59E0B;
        color: white !important;
        font-size: 15px;
        line-height: 1.4;
    }
    .catalogo-header {
        background: #F59E0B;
        color: white;
        padding: 8px;
        border-radius: 8px;
        text-align: center;
        font-weight: bold;
        font-size: 16px;
        margin-bottom: 8px;
    }
    .pedigree-card {
        background: #0F172A;
        color: white;
        padding: 12px;
        border-radius: 10px;
        margin: 4px 0;
        border: 1px solid #334155;
    }
    .pedigree-card table {
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
    }
    .pedigree-card td {
        padding: 4px 6px;
        border-bottom: 1px solid #1E293B;
    }
    .status-processamento {
        background: #0F172A;
        color: #94A3B8;
        padding: 10px;
        border-radius: 8px;
        font-size: 13px;
        margin-bottom: 8px;
        border: 1px solid #1E293B;
    }
</style>
"""
st.markdown(css_code, unsafe_allow_html=True)

# ==================== API KEYS (DEEPSEEK) ====================
def obter_api_keys():
    ds_keys = []
    try:
        if hasattr(st, "secrets"):
            for k in ["DEEPSEEK_API_KEY", "DEEPSEEK_API_KEYS"]:
                if k in st.secrets:
                    val = st.secrets[k]
                    if isinstance(val, (list, tuple)):
                        ds_keys.extend(val)
                    elif isinstance(val, str):
                        ds_keys.append(val)
    except Exception:
        pass
    return [str(x).strip().strip("'\"") for x in ds_keys if str(x).strip()]

# ==================== HELPERS ====================
def normalizar_lote(valor):
    if valor is None:
        return ""
    digitos = re.sub(r"\D", "", str(valor))
    return str(int(digitos)) if digitos else ""

def hash_bytes(b):
    return hashlib.md5(b).hexdigest() if b else ""

def extrair_json(texto):
    """Extrai o primeiro objeto/array JSON válido de um texto que pode vir
    com ```json ... ``` ou com texto antes/depois."""
    if not texto:
        return None
    limpo = re.sub(r"```json|```", "", texto).strip()
    try:
        return json.loads(limpo)
    except Exception:
        pass
    match = re.search(r"(\{.*\}|\[.*\])", limpo, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None
    return None

# ==================== PROCESSAMENTO DA O.E. (SEM IA — TABELA) ====================
@st.cache_data(ttl=7200, show_spinner=False)
def extrair_ordem_entrada_tabela(file_bytes):
    sequencia = []
    mapa = {}

    if not file_bytes:
        return sequencia, mapa

    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        row_clean = [str(cell).strip() if cell else "" for cell in row]

                        if any(header in "".join(row_clean).upper() for header in ["CATEGORIA", "VENDEDOR", "PRODUTO"]):
                            if "LT" in "".join(row_clean).upper() or "O.E." in "".join(row_clean).upper():
                                continue

                        if len(row_clean) >= 2:
                            oe_raw = row_clean[0]
                            lt_raw = row_clean[1]

                            num_lt = normalizar_lote(lt_raw)

                            if num_lt:
                                posicao_texto = f"{oe_raw} A ENTRAR" if ("°" in oe_raw or "º" in oe_raw) else f"{oe_raw}º A ENTRAR"

                                categoria = row_clean[2] if len(row_clean) > 2 else ""
                                pelagem = row_clean[3] if len(row_clean) > 3 else ""
                                produto = row_clean[4] if len(row_clean) > 4 else ""
                                vendedor = row_clean[5] if len(row_clean) > 5 else ""

                                if num_lt not in mapa:
                                    sequencia.append(num_lt)

                                mapa[num_lt] = {
                                    "lote": num_lt,
                                    "oe": oe_raw,
                                    "posicao": posicao_texto,
                                    "categoria": categoria,
                                    "pelagem": pelagem,
                                    "nome_animal": produto,
                                    "produto": produto,
                                    "vendedor": vendedor,
                                    "qtd": "1"
                                }
    except Exception as e:
        st.error(f"Erro ao extrair tabela da O.E.: {str(e)}")

    return sequencia, mapa

# ==================== RENDERIZAR IMAGEM DO CATÁLOGO ====================
@st.cache_data(ttl=7200, show_spinner=False)
def contar_paginas_pdf(file_bytes):
    if not file_bytes:
        return 0
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            return len(pdf.pages)
    except Exception:
        return 0

@st.cache_data(ttl=7200, show_spinner=False)
def obter_imagem_bytes_pagina(file_bytes, num_pagina, resolucao=150):
    if not file_bytes or num_pagina < 0:
        return None
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            if 0 <= num_pagina < len(pdf.pages):
                img = pdf.pages[num_pagina].to_image(resolution=resolucao).original
                buffer = BytesIO()
                img.convert("RGB").save(buffer, format="JPEG", quality=85)
                return buffer.getvalue()
    except Exception:
        return None
    return None

def _prefetch_paginas_worker(file_bytes, paginas):
    """Roda em thread separada: só esquenta o cache de obter_imagem_bytes_pagina
    pra quando o usuário clicar em 'Próximo', a imagem já estar pronta."""
    for p in paginas:
        try:
            obter_imagem_bytes_pagina(file_bytes, p)
        except Exception:
            pass

def pre_carregar_lotes_vizinhos(file_bytes_cat, lista_lotes, idx_atual, mapa_oe, indice_catalogo, qtd=QTD_PRE_CARREGAR):
    """Pré-carrega em segundo plano a imagem da página dos lotes vizinhos —
    tanto os próximos quanto os anteriores — pra navegar em qualquer direção
    (Próximo ou Anterior) sem esperar renderização."""
    if not file_bytes_cat or not indice_catalogo:
        return
    paginas_vizinhas = []
    offsets = list(range(-qtd, 0)) + list(range(1, qtd + 1))  # anteriores e próximos
    for offset in offsets:
        idx_vizinho = idx_atual + offset
        if idx_vizinho < 0 or idx_vizinho >= len(lista_lotes):
            continue
        lt_vizinho = lista_lotes[idx_vizinho]
        dados_lote_vizinho = mapa_oe.get(lt_vizinho, {})
        dados_cat_vizinho = encontrar_no_indice(lt_vizinho, dados_lote_vizinho.get("nome_animal", ""), indice_catalogo)
        if dados_cat_vizinho:
            pagina = dados_cat_vizinho.get("_pagina", -1)
            if pagina >= 0:
                paginas_vizinhas.append(pagina)
    if paginas_vizinhas:
        threading.Thread(
            target=_prefetch_paginas_worker,
            args=(file_bytes_cat, paginas_vizinhas),
            daemon=True
        ).start()

@st.cache_data(ttl=7200, show_spinner=False)
def extrair_textos_paginas(file_bytes, max_paginas):
    """Extrai o texto de cada página do catálogo uma única vez (cacheado)."""
    paginas_extraidas = []
    if not file_bytes:
        return paginas_extraidas
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            total = min(len(pdf.pages), max_paginas)
            for i in range(total):
                txt = pdf.pages[i].extract_text() or ""
                paginas_extraidas.append((i, txt))
    except Exception:
        pass
    return paginas_extraidas

# ==================== INDEXAÇÃO DO CATÁLOGO VIA DEEPSEEK (EM LOTE) ====================
def deepseek_indexar_paginas_lote(bloco_paginas, _ds_keys):
    """bloco_paginas: lista de (num_pagina, texto). Manda VÁRIAS páginas numa
    única chamada e recebe um array de resultados na mesma ordem — reduz
    drasticamente o número de chamadas em relação a 1 por página."""
    if not bloco_paginas or not _ds_keys:
        return [None] * len(bloco_paginas), "sem páginas ou sem chave"

    corpo_paginas = ""
    for pos, (num_pag, txt) in enumerate(bloco_paginas):
        trecho = (txt or "").strip()[:2500]
        if not trecho:
            trecho = "(página sem texto extraível)"
        corpo_paginas += f"\n=== PÁGINA {pos + 1} (pág. real {num_pag + 1}) ===\n{trecho}\n"

    prompt = f"""Estas são {len(bloco_paginas)} páginas de um CATÁLOGO de leilão, na
ordem PÁGINA 1, PÁGINA 2, etc. Cada página pode ser a capa, uma página de
regras/informações, ou a ficha de UM animal/lote específico.
{corpo_paginas}

Para CADA página, na mesma ordem, extraia (se for ficha de lote):
numero_lote, nome_animal, registro, raca, sexo, nascimento, pelagem, vendedor,
pai, mae, avo_paterno, avo_paterna, avo_materno, avo_materna, observacoes.

Se a página NÃO for ficha de lote (capa, regras, índice, sem texto), retorne
"numero_lote": null e os outros campos vazios — mas AINDA ASSIM inclua um
objeto pra ela no array, na posição correta.

Retorne APENAS um JSON válido, sem texto antes ou depois, no formato:
{{
  "paginas": [
    {{
      "pagina_ordem": 1,
      "numero_lote": "01" ou null,
      "nome_animal": "", "registro": "", "raca": "", "sexo": "",
      "nascimento": "", "pelagem": "", "vendedor": "",
      "pai": "", "mae": "", "avo_paterno": "", "avo_paterna": "",
      "avo_materno": "", "avo_materna": "", "observacoes": ""
    }}
  ]
}}

O array "paginas" DEVE ter exatamente {len(bloco_paginas)} itens, um por página.
"""

    url = "https://api.deepseek.com/chat/completions"
    ultimo_erro = ""
    for api_key in _ds_keys:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            res_json = response.json()
            if response.status_code == 200 and 'choices' in res_json:
                dados = extrair_json(res_json['choices'][0]['message']['content'])
                if not dados or "paginas" not in dados:
                    ultimo_erro = "DeepSeek respondeu, mas não veio JSON válido"
                    continue
                paginas = dados["paginas"]
                while len(paginas) < len(bloco_paginas):
                    paginas.append(None)
                return paginas[:len(bloco_paginas)], None
            else:
                ultimo_erro = f"HTTP {response.status_code}: {res_json.get('error', res_json)}"
        except Exception as e:
            ultimo_erro = str(e)

    return [None] * len(bloco_paginas), ultimo_erro

@st.cache_data(ttl=7200, show_spinner=False)
def construir_indice_catalogo(file_bytes_cat, hash_arquivo, _ds_keys, max_paginas, tamanho_lote):
    indice = {}
    erros = []
    if not file_bytes_cat or not _ds_keys:
        return indice, 0, ["sem catálogo ou sem DEEPSEEK_API_KEY"]

    paginas_extraidas = extrair_textos_paginas(file_bytes_cat, max_paginas)
    if not paginas_extraidas:
        return indice, 0, ["não foi possível extrair texto do catálogo"]

    grupos = [paginas_extraidas[i:i + tamanho_lote] for i in range(0, len(paginas_extraidas), tamanho_lote)]

    progresso = st.progress(0, text="🤖 DeepSeek indexando o catálogo...")
    for g_idx, grupo in enumerate(grupos):
        # pula grupos 100% vazios (economia real — não gasta chamada à toa)
        if not any((txt or "").strip() for _, txt in grupo):
            progresso.progress((g_idx + 1) / len(grupos), text=f"🤖 Indexando catálogo... grupo {g_idx + 1}/{len(grupos)}")
            continue

        resultados, erro = deepseek_indexar_paginas_lote(grupo, _ds_keys)
        if erro:
            paginas_reais = [p + 1 for p, _ in grupo]
            erros.append(f"Páginas {paginas_reais}: {erro}")

        for pos, (num_pag, _txt) in enumerate(grupo):
            if pos >= len(resultados):
                continue
            dados = resultados[pos]
            if dados and dados.get("numero_lote"):
                chave = normalizar_lote(dados["numero_lote"])
                if chave:
                    dados["_pagina"] = num_pag
                    indice[chave] = dados

        progresso.progress((g_idx + 1) / len(grupos), text=f"🤖 Indexando catálogo... grupo {g_idx + 1}/{len(grupos)}")

    progresso.empty()
    return indice, len(paginas_extraidas), erros

def encontrar_no_indice(num_lote_oe, nome_animal_oe, indice):
    chave = normalizar_lote(num_lote_oe)
    if chave in indice:
        return indice[chave]

    if nome_animal_oe:
        melhor_match = None
        melhor_score = 0.0
        for dados in indice.values():
            nome_cat = dados.get("nome_animal", "")
            if nome_cat:
                score = difflib.SequenceMatcher(None, nome_animal_oe.upper(), nome_cat.upper()).ratio()
                if score > melhor_score:
                    melhor_score = score
                    melhor_match = dados
        if melhor_match and melhor_score > 0.55:
            return melhor_match

    return None

# ==================== DEEPSEEK CRUZA E GERA CONTEÚDO (POR LOTE — ORIGINAL, MANTIDA) ====================
@st.cache_data(ttl=7200, show_spinner=False)
def deepseek_gerar_conteudo_cached(num_lote, dados_ordem_str, dados_catalogo_str, ds_keys_tuple):
    ds_keys = list(ds_keys_tuple)
    dados_ordem = json.loads(dados_ordem_str)
    dados_catalogo = json.loads(dados_catalogo_str) if dados_catalogo_str else {}

    if not ds_keys:
        return None

    prompt = f"""
    Você é um leiloeiro rural de elite. Monte a canta do LOTE {num_lote} (Entrada O.E.: {dados_ordem.get('oe', '')}).

    DADOS DA ORDEM DE ENTRADA:
    {json.dumps(dados_ordem, ensure_ascii=False, indent=2)}

    DADOS DO CATÁLOGO (se disponível):
    {json.dumps(dados_catalogo, ensure_ascii=False, indent=2)}

    Gere um JSON completo com:
    1. "abertura": Frase de impacto curta (máx. 25 palavras) para começar o leilão com energia.
    2. "apresentacao_detalhada": Texto fluído de canta para o leiloeiro ler na pista, descrevendo o animal, vendedor, categoria e potenciais virtudes.
    3. "parecer_ia": Análise comercial e técnica do lote para valorizar o produto na pista (1 parágrafo).
    4. "encartes": Lista com 3 encartes para tela (ex: CATEGORIA, PELAGEM, VENDEDOR).
    5. "gatilhos": 4 a 5 gatilhos de pista curtos, agressivos e impactantes para soltar durante os lances.

    Retorne APENAS um JSON no formato:
    {{
        "abertura": "...",
        "apresentacao_detalhada": "...",
        "parecer_ia": "...",
        "encartes": [
            {{"titulo": "CATEGORIA", "valor": "..."}},
            {{"titulo": "PELAGEM", "valor": "..."}},
            {{"titulo": "VENDEDOR", "valor": "..."}}
        ],
        "gatilhos": ["Gatilho 1", "Gatilho 2", "Gatilho 3", "Gatilho 4"]
    }}
    """

    url = "https://api.deepseek.com/chat/completions"
    for api_key in ds_keys:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.4
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            res_json = response.json()
            if response.status_code == 200 and 'choices' in res_json:
                return json.loads(res_json['choices'][0]['message']['content'])
        except Exception:
            continue

    return None

def deepseek_gerar_conteudo(num_lote, dados_ordem, dados_catalogo, ds_keys):
    return deepseek_gerar_conteudo_cached(
        num_lote,
        json.dumps(dados_ordem, sort_keys=True),
        json.dumps(dados_catalogo or {}, sort_keys=True),
        tuple(ds_keys)
    )

# ==================== NOVO: GERA CONTEÚDO PRA VÁRIOS LOTES DE UMA VEZ (BATCH) ====================
def deepseek_gerar_conteudo_batch(lotes_bloco, _ds_keys):
    """lotes_bloco: lista de dicts {"lote":..., "ordem":..., "catalogo":...}.
    Uma única chamada gera abertura/apresentação/parecer/encartes/gatilhos
    pra vários lotes ao mesmo tempo — mesmo formato de campos da função
    individual, só que em lote."""
    if not lotes_bloco or not _ds_keys:
        return {}, "sem lotes ou sem chave"

    prompt = f"""
    Você é um leiloeiro rural de elite. Para CADA lote abaixo, monte a canta
    completa (mesmo padrão de sempre).

    LOTES (JSON):
    {json.dumps(lotes_bloco, ensure_ascii=False, indent=2)}

    Para cada lote gere:
    1. "abertura": Frase de impacto curta (máx. 25 palavras).
    2. "apresentacao_detalhada": Texto fluído de canta pra pista (animal, vendedor, categoria, virtudes).
    3. "parecer_ia": Análise comercial/técnica em 1 parágrafo.
    4. "encartes": 3 encartes pra tela (ex: CATEGORIA, PELAGEM, VENDEDOR).
    5. "gatilhos": 4 a 5 gatilhos curtos de pista.

    Retorne APENAS JSON:
    {{
      "resultados": [
        {{
          "lote": "01",
          "abertura": "...",
          "apresentacao_detalhada": "...",
          "parecer_ia": "...",
          "encartes": [{{"titulo": "CATEGORIA", "valor": "..."}}],
          "gatilhos": ["...", "...", "...", "..."]
        }}
      ]
    }}
    """

    url = "https://api.deepseek.com/chat/completions"
    ultimo_erro = ""
    for api_key in _ds_keys:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.4
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            res_json = response.json()
            if response.status_code == 200 and 'choices' in res_json:
                dados = extrair_json(res_json['choices'][0]['message']['content'])
                if not dados or "resultados" not in dados:
                    ultimo_erro = "DeepSeek respondeu, mas não veio JSON válido"
                    continue
                mapa = {}
                for r in dados["resultados"]:
                    lt = r.get("lote")
                    if lt:
                        mapa[normalizar_lote(lt)] = r
                return mapa, None
            else:
                ultimo_erro = f"HTTP {response.status_code}: {res_json.get('error', res_json)}"
        except Exception as e:
            ultimo_erro = str(e)

    return {}, ultimo_erro

@st.cache_data(ttl=7200, show_spinner=False)
def preparar_todos_conteudos(lista_lotes, mapa_oe, indice_catalogo, _ds_keys, tamanho_lote):
    """Pré-gera o conteúdo de TODOS os lotes de uma vez, em lotes (batches),
    e cacheia o resultado inteiro. Depois disso, navegar entre lotes é só
    lookup em dicionário — sem nova chamada de IA. Se algum lote não vier
    no lote (ex: resposta truncada), a função individual já cacheada
    (deepseek_gerar_conteudo) continua servindo de fallback automático."""
    resultado_final = {}
    erros = []

    if not lista_lotes or not _ds_keys:
        return resultado_final, ["sem lotes ou sem chave"]

    lotes_bloco = []
    for num_lote in lista_lotes:
        dados_ordem = mapa_oe.get(num_lote, {})
        dados_cat = encontrar_no_indice(num_lote, dados_ordem.get("nome_animal", ""), indice_catalogo)
        lotes_bloco.append({
            "lote": num_lote,
            "ordem": dados_ordem,
            "catalogo": {k: v for k, v in (dados_cat or {}).items() if k != "_pagina"}
        })

    grupos = [lotes_bloco[i:i + tamanho_lote] for i in range(0, len(lotes_bloco), tamanho_lote)]

    progresso = st.progress(0, text="🧠 Preparando a canta de todos os lotes...")
    for g_idx, grupo in enumerate(grupos):
        mapa_resultado, erro = deepseek_gerar_conteudo_batch(grupo, _ds_keys)
        if erro:
            erros.append(f"Grupo lotes {[g['lote'] for g in grupo]}: {erro}")
        resultado_final.update(mapa_resultado)
        progresso.progress((g_idx + 1) / len(grupos), text=f"🧠 Preparando a canta... grupo {g_idx + 1}/{len(grupos)}")
    progresso.empty()

    return resultado_final, erros

def renderizar_pedigree(dados_catalogo):
    if not dados_catalogo:
        return
    p, m = dados_catalogo.get("pai", ""), dados_catalogo.get("mae", "")
    ap, apm = dados_catalogo.get("avo_paterno", ""), dados_catalogo.get("avo_paterna", "")
    am, amm = dados_catalogo.get("avo_materno", ""), dados_catalogo.get("avo_materna", "")

    if not any([p, m, ap, apm, am, amm]):
        return

    html = '<div class="pedigree-card"><table>'
    html += f'<tr><td><strong>PAI:</strong> {p or "-"}</td><td><strong>AVÔ PATERNO:</strong> {ap or "-"}</td></tr>'
    html += f'<tr><td></td><td><strong>AVÓ PATERNA:</strong> {apm or "-"}</td></tr>'
    html += f'<tr><td><strong>MÃE:</strong> {m or "-"}</td><td><strong>AVÔ MATERNO:</strong> {am or "-"}</td></tr>'
    html += f'<tr><td></td><td><strong>AVÓ MATERNA:</strong> {amm or "-"}</td></tr>'
    html += '</table></div>'
    st.markdown(html, unsafe_allow_html=True)

# ==================== MAIN ====================
def run():
    ds_keys = obter_api_keys()

    with st.sidebar:
        st.header("📂 Arquivos")
        file_oe = st.file_uploader("Ordem de Entrada (PDF) *Obrigatório*", type="pdf", key="oe")
        file_cat = st.file_uploader("Catálogo (PDF) *Opcional*", type="pdf", key="cat")

        st.markdown("---")
        modo_ordenacao = st.radio("Ordem de Exibição:", ["ORDEM DE ENTRADA (O.E.)", "ORDEM NUMÉRICA (LT)"], index=0)
        max_paginas_catalogo = st.number_input(
            "Máx. páginas catálogo", min_value=1, max_value=300, value=60
        )

        with st.expander("⚙️ Desempenho (avançado)"):
            tamanho_lote_paginas = st.number_input(
                "Páginas de catálogo por chamada", min_value=1, max_value=10, value=BATCH_PAGINAS_PADRAO
            )
            tamanho_lote_conteudo = st.number_input(
                "Lotes por chamada (canta/gatilhos)", min_value=1, max_value=20, value=BATCH_LOTES_PADRAO
            )
            if st.button("🔄 Reprocessar tudo (limpar cache)", use_container_width=True):
                construir_indice_catalogo.clear()
                preparar_todos_conteudos.clear()
                deepseek_gerar_conteudo_cached.clear()
                st.rerun()

    file_bytes_oe = file_oe.getvalue() if file_oe else None
    file_bytes_cat = file_cat.getvalue() if file_cat else None

    sequencia_oe, mapa_oe = extrair_ordem_entrada_tabela(file_bytes_oe)

    if not sequencia_oe:
        st.warning("👈 Abra a barra lateral e carregue o PDF da Ordem de Entrada para começar!")
        st.stop()

    indice_catalogo = {}
    total_paginas_cat = 0
    erros_indice = []
    if file_bytes_cat and ds_keys:
        indice_catalogo, total_paginas_cat, erros_indice = construir_indice_catalogo(
            file_bytes_cat, hash_bytes(file_bytes_cat), tuple(ds_keys),
            max_paginas_catalogo, tamanho_lote_paginas
        )

    # pré-gera a canta de TODOS os lotes de uma vez (roda 1x, fica em cache)
    dados_finais_todos = {}
    erros_conteudo = []
    if ds_keys:
        dados_finais_todos, erros_conteudo = preparar_todos_conteudos(
            tuple(sequencia_oe), mapa_oe, indice_catalogo, tuple(ds_keys), tamanho_lote_conteudo
        )

    if erros_indice or erros_conteudo:
        with st.expander("🛠️ Status do processamento (debug)"):
            st.markdown(
                f'<div class="status-processamento">'
                f'Lotes na O.E.: {len(sequencia_oe)} | '
                f'Páginas do catálogo indexadas: {len(indice_catalogo)} de {total_paginas_cat} | '
                f'Lotes com canta pronta: {len(dados_finais_todos)}'
                f'</div>', unsafe_allow_html=True
            )
            if erros_indice:
                st.error("Erros na indexação do catálogo:")
                for e in erros_indice:
                    st.text(f"• {e}")
            if erros_conteudo:
                st.error("Erros ao gerar a canta/gatilhos:")
                for e in erros_conteudo:
                    st.text(f"• {e}")

    if modo_ordenacao == "ORDEM NUMÉRICA (LT)":
        lista_lotes = sorted(sequencia_oe, key=lambda x: int(re.sub(r"\D", "", x) or 0))
    else:
        lista_lotes = sequencia_oe.copy()

    if 'lote_idx' not in st.session_state:
        st.session_state.lote_idx = 0
    if st.session_state.lote_idx >= len(lista_lotes):
        st.session_state.lote_idx = 0

    num_lote = lista_lotes[st.session_state.lote_idx]
    dados_lote = mapa_oe.get(num_lote, {})

    st.markdown(
        f'<div class="ordem-indicador">{dados_lote.get("posicao", "")} | LOTE {num_lote} ({st.session_state.lote_idx + 1} de {len(lista_lotes)})</div>',
        unsafe_allow_html=True
    )

    col_prev, col_next = st.columns(2)
    with col_prev:
        if st.button("⬅️ ANTERIOR", use_container_width=True):
            st.session_state.lote_idx = max(0, st.session_state.lote_idx - 1)
            st.rerun()
    with col_next:
        if st.button("PRÓXIMO ➡️", use_container_width=True):
            st.session_state.lote_idx = min(len(lista_lotes) - 1, st.session_state.lote_idx + 1)
            st.rerun()

    opcoes_dropdown = [f"LOTE {lt} ({mapa_oe[lt].get('oe', '')} a entrar)" for lt in lista_lotes]
    idx_selecionado = st.selectbox(
        "Ir diretamente para o Lote:",
        range(len(lista_lotes)),
        format_func=lambda i: opcoes_dropdown[i],
        index=st.session_state.lote_idx
    )
    if idx_selecionado != st.session_state.lote_idx:
        st.session_state.lote_idx = idx_selecionado
        st.rerun()

    dados_catalogo = encontrar_no_indice(num_lote, dados_lote.get("nome_animal", ""), indice_catalogo) if indice_catalogo else None
    pagina_detectada = dados_catalogo.get("_pagina", -1) if dados_catalogo else -1

    # pré-carrega em segundo plano a imagem dos próximos lotes (cache warming)
    pre_carregar_proximos_lotes(file_bytes_cat, lista_lotes, st.session_state.lote_idx, mapa_oe, indice_catalogo)

    # 1) tenta pegar do lote pré-processado (sem chamada de IA);
    # 2) se não achou (ex: erro pontual no batch), cai no cálculo individual
    #    já cacheado — continua funcionando igual antes, só que como reserva.
    dados_finais = dados_finais_todos.get(normalizar_lote(num_lote))
    if not dados_finais and ds_keys:
        with st.spinner("🧠 DeepSeek preparando a pista..."):
            dados_finais = deepseek_gerar_conteudo(num_lote, dados_lote, dados_catalogo, ds_keys)

    # ==================== RENDERIZAÇÃO DE LAYOUT ====================

    # CASO 1: TEM CATÁLOGO CARREGADO
    if file_bytes_cat:
        col_esquerda, col_direita = st.columns([1, 1])

        # COLUNA ESQUERDA: CATÁLOGO ELEVADO + GATILHOS LOGO ABAIXO
        with col_esquerda:
            if pagina_detectada < 0:
                pagina_manual = st.number_input(
                    "Página do catálogo:", min_value=1, max_value=max(1, total_paginas_cat),
                    value=1, key=f"pag_{num_lote}"
                )
                pagina_detectada = pagina_manual - 1

            if pagina_detectada >= 0:
                st.markdown(f'<div class="catalogo-header">📖 CATÁLOGO - PÁGINA {pagina_detectada + 1} DE {total_paginas_cat}</div>', unsafe_allow_html=True)
                img_bytes = obter_imagem_bytes_pagina(file_bytes_cat, pagina_detectada)
                if img_bytes:
                    st.image(img_bytes, use_container_width=True)

            if dados_catalogo:
                with st.expander("📖 Dados do Catálogo (JSON)"):
                    st.json({k: v for k, v in dados_catalogo.items() if k != "_pagina"})

            # GATILHOS DE PISTA MOVIDOS PARA DEBAIXO DO CATÁLOGO
            st.markdown("### 🎤 GATILHOS DE PISTA")
            if dados_finais and dados_finais.get("gatilhos"):
                for g in dados_finais["gatilhos"]:
                    st.markdown(f'<div class="gatilho-card">🔥 {g}</div>', unsafe_allow_html=True)

        # COLUNA DIREITA: INFORMAÇÕES E CANTA DO LEILOEIRO
        with col_direita:
            st.markdown(f'<div class="lote-destaque">LOTE {num_lote}<br><span style="font-size: 24px;">{dados_lote.get("posicao", "")}</span></div>', unsafe_allow_html=True)

            nome_exibir = (dados_catalogo or {}).get("nome_animal") or dados_lote.get("nome_animal", "")
            if nome_exibir:
                st.markdown(f'<div class="nome-animal-box">🐴 {nome_exibir}</div>', unsafe_allow_html=True)

            if dados_finais and dados_finais.get("abertura"):
                st.markdown(f'<div class="abertura-box">🎙️ "{dados_finais["abertura"]}"</div>', unsafe_allow_html=True)

            st.markdown("### 📋 INFORMAÇÕES DA O.E.")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f'<div class="animal-info"><strong>CATEGORIA:</strong><br>{dados_lote.get("categoria", "-")}</div>', unsafe_allow_html=True)
            with col2:
                st.markdown(f'<div class="animal-info"><strong>PELAGEM:</strong><br>{dados_lote.get("pelagem", "-")}</div>', unsafe_allow_html=True)
            with col3:
                st.markdown(f'<div class="animal-info"><strong>VENDEDOR:</strong><br>{dados_lote.get("vendedor", "-")}</div>', unsafe_allow_html=True)

            if dados_finais and dados_finais.get("apresentacao_detalhada"):
                st.markdown("### 📢 CANTA DO LEILOEIRO")
                st.markdown(f'<div class="canta-box">{dados_finais["apresentacao_detalhada"]}</div>', unsafe_allow_html=True)

            if dados_catalogo:
                st.markdown("### 🧬 GENEALOGIA")
                renderizar_pedigree(dados_catalogo)

    # CASO 2: SEM CATÁLOGO (LAYOUT COMPLETO / FULL SCREEN)
    else:
        st.markdown(f'<div class="lote-destaque">LOTE {num_lote} | {dados_lote.get("posicao", "")}</div>', unsafe_allow_html=True)

        nome_exibir = dados_lote.get("nome_animal", "")
        if nome_exibir:
            st.markdown(f'<div class="nome-animal-box">🐴 {nome_exibir}</div>', unsafe_allow_html=True)

        if dados_finais and dados_finais.get("abertura"):
            st.markdown(f'<div class="abertura-box">🎙️ ABERTURA DE PISTA: "{dados_finais["abertura"]}"</div>', unsafe_allow_html=True)

        st.markdown("### 📋 INFORMAÇÕES DO LOTE (ORDEM DE ENTRADA)")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f'<div class="animal-info"><strong>LOTE:</strong><br>{num_lote}</div>', unsafe_allow_html=True)
        with col2:
            st.markdown(f'<div class="animal-info"><strong>CATEGORIA:</strong><br>{dados_lote.get("categoria", "-")}</div>', unsafe_allow_html=True)
        with col3:
            st.markdown(f'<div class="animal-info"><strong>PELAGEM:</strong><br>{dados_lote.get("pelagem", "-")}</div>', unsafe_allow_html=True)
        with col4:
            st.markdown(f'<div class="animal-info"><strong>VENDEDOR:</strong><br>{dados_lote.get("vendedor", "-")}</div>', unsafe_allow_html=True)

        col_esq, col_dir = st.columns([1.2, 1])

        with col_esq:
            if dados_finais and dados_finais.get("apresentacao_detalhada"):
                st.markdown("### 📢 CANTA COMPLETA DO LEILOEIRO")
                st.markdown(f'<div class="canta-box">{dados_finais["apresentacao_detalhada"]}</div>', unsafe_allow_html=True)

            if dados_finais and dados_finais.get("parecer_ia"):
                st.markdown("### 🧠 PARECER TÉCNICO & COMERCIAL DA IA")
                st.markdown(f'<div class="parecer-box">{dados_finais["parecer_ia"]}</div>', unsafe_allow_html=True)

        with col_dir:
            st.markdown("### 🎤 GATILHOS DE PISTA (DEEPSEEK)")
            if dados_finais and dados_finais.get("gatilhos"):
                for g in dados_finais["gatilhos"]:
                    st.markdown(f'<div class="gatilho-card">🔥 {g}</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    run()
