import streamlit as st
import pdfplumber
import re
import requests
import json
import difflib
import hashlib
from io import BytesIO

st.set_page_config(
    page_title="PAINEL DO LEILOEIRO PRO",
    page_icon="🐂",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== CSS ====================
css_code = """
<style>
    #MainMenu {visibility: hidden; display: none;}
    footer {visibility: hidden; display: none;}
    [data-testid="stToolbar"] {display: none;}
    .block-container {padding-top: 2.5rem; padding-bottom: 2rem;}

    .lote-destaque {
        background: linear-gradient(135deg, #1E3A8A 0%, #3B82F6 100%);
        color: white;
        padding: 20px;
        border-radius: 18px;
        text-align: center;
        font-size: 48px;
        font-weight: bold;
        margin-bottom: 12px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
    .ordem-indicador {
        background: #16A34A;
        color: white;
        padding: 12px;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
        margin: 8px 0;
        font-size: 20px;
    }
    .animal-info {
        background: #1E293B;
        color: white;
        padding: 15px;
        border-radius: 12px;
        margin: 5px 0;
        border: 1px solid #334155;
        min-height: 85px;
        text-align: center;
    }
    .nome-animal-box {
        background: #0284C7;
        color: white;
        padding: 16px;
        border-radius: 12px;
        margin-bottom: 12px;
        font-size: 24px;
        font-weight: bold;
        text-align: center;
    }
    .gatilho-card {
        background: linear-gradient(90deg, #EC4899 0%, #8B5CF6 100%);
        color: white;
        padding: 14px;
        border-radius: 12px;
        font-size: 17px;
        margin: 6px 0;
        font-weight: bold;
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    }
    .abertura-box {
        background: linear-gradient(135deg, #065F46 0%, #047857 100%);
        color: white !important;
        padding: 18px;
        border-radius: 14px;
        margin-bottom: 15px;
        font-size: 20px !important;
        font-weight: bold;
        font-style: italic;
        border: 2px solid #10B981;
    }
    .canta-box {
        background-color: #1E1B4B !important;
        padding: 22px;
        border-radius: 15px;
        margin-bottom: 15px;
        border-left: 8px solid #818CF8;
        color: white !important;
        font-size: 17px;
        line-height: 1.6;
    }
    .parecer-box {
        background-color: #0F172A !important;
        padding: 20px;
        border-radius: 15px;
        margin-bottom: 15px;
        border-left: 8px solid #F59E0B;
        color: white !important;
        font-size: 16px;
        line-height: 1.5;
    }
    .catalogo-header {
        background: #F59E0B;
        color: white;
        padding: 10px;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
        font-size: 18px;
        margin-bottom: 10px;
    }
    .pedigree-card {
        background: #0F172A;
        color: white;
        padding: 14px;
        border-radius: 12px;
        margin: 5px 0;
        border: 1px solid #334155;
    }
    .pedigree-card table {
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
    }
    .pedigree-card td {
        padding: 6px 8px;
        border-bottom: 1px solid #1E293B;
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

# ==================== PROCESSAMENTO DA O.E. ====================
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

# ==================== INDEXAÇÃO DO CATÁLOGO VIA DEEPSEEK ====================
def deepseek_indexar_pagina_catalogo(texto_pagina, ds_keys):
    if not texto_pagina or not ds_keys:
        return None

    prompt = f"""Esta é uma página de um CATÁLOGO de leilão.
TEXTO DA PÁGINA:
{texto_pagina[:4000]}

Se for a ficha de um lote, extraia em JSON:
- "numero_lote": (apenas número, ex: "100", "23", "01")
- "nome_animal": ""
- "registro": ""
- "raca": ""
- "sexo": ""
- "nascimento": ""
- "pelagem": ""
- "vendedor": ""
- "pai": ""
- "mae": ""
- "avo_paterno": ""
- "avo_paterna": ""
- "avo_materno": ""
- "avo_materna": ""
- "observacoes": ""

Se a página NÃO for a ficha de um lote, retorne "numero_lote": null.
Retorne APENAS um JSON válido.
"""

    url = "https://api.deepseek.com/chat/completions"
    for api_key in ds_keys:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=30).json()
            if 'choices' in res:
                content = res['choices'][0]['message']['content']
                return json.loads(content)
        except Exception:
            continue
    return None

@st.cache_data(ttl=7200, show_spinner=False)
def construir_indice_catalogo(file_bytes_cat, hash_arquivo, ds_keys, max_paginas=60):
    indice = {}
    if not file_bytes_cat or not ds_keys:
        return indice, 0

    paginas_extraidas = []
    try:
        with pdfplumber.open(BytesIO(file_bytes_cat)) as pdf:
            total = min(len(pdf.pages), max_paginas)
            for i in range(total):
                txt = pdf.pages[i].extract_text() or ""
                paginas_extraidas.append((i, txt))
    except Exception:
        return indice, 0

    progresso = st.progress(0, text="🤖 DeepSeek indexando o catálogo...")
    for idx, (num_pag, txt_pag) in enumerate(paginas_extraidas):
        if txt_pag.strip():
            dados = deepseek_indexar_pagina_catalogo(txt_pag, ds_keys)
            if dados and dados.get("numero_lote"):
                chave = normalizar_lote(dados["numero_lote"])
                if chave:
                    dados["_pagina"] = num_pag
                    indice[chave] = dados
        progresso.progress((idx + 1) / len(paginas_extraidas), text=f"🤖 DeepSeek indexando... página {idx + 1}/{len(paginas_extraidas)}")
    progresso.empty()
    return indice, len(paginas_extraidas)

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

# ==================== DEEPSEEK CRUZA E GERA CONTEÚDO ENRIQUECIDO ====================
@st.cache_data(ttl=7200, show_spinner=False)
def deepseek_gerar_conteudo_cached(num_lote, dados_ordem_str, dados_catalogo_str, ds_keys_tuple):
    ds_keys = list(ds_keys_tuple)
    dados_ordem = json.loads(dados_ordem_str)
    dados_catalogo = json.loads(dados_catalogo_str) if dados_catalogo_str else {}

    if not ds_keys:
        return None

    prompt = f"""
    Você é um leiloeiro rural de elite com anos de pista. Monte a canta do LOTE {num_lote} (Entrada O.E.: {dados_ordem.get('oe', '')}).

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

    file_bytes_oe = file_oe.getvalue() if file_oe else None
    file_bytes_cat = file_cat.getvalue() if file_cat else None

    sequencia_oe, mapa_oe = extrair_ordem_entrada_tabela(file_bytes_oe)

    if not sequencia_oe:
        st.warning("👈 Abra a barra lateral e carregue o PDF da Ordem de Entrada para começar!")
        st.stop()

    indice_catalogo = {}
    total_paginas_cat = 0
    if file_bytes_cat and ds_keys:
        indice_catalogo, total_paginas_cat = construir_indice_catalogo(
            file_bytes_cat, hash_bytes(file_bytes_cat), ds_keys, max_paginas_catalogo
        )

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

    # Barra superior de indicador do lote
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

    # Busca dados no catálogo se houver
    dados_catalogo = encontrar_no_indice(num_lote, dados_lote.get("nome_animal", ""), indice_catalogo) if indice_catalogo else None
    pagina_detectada = dados_catalogo.get("_pagina", -1) if dados_catalogo else -1

    # Gera conteúdo via IA DeepSeek
    dados_finais = None
    if ds_keys:
        with st.spinner("🧠 DeepSeek preparando a pista..."):
            dados_finais = deepseek_gerar_conteudo(num_lote, dados_lote, dados_catalogo, ds_keys)

    # ==================== RENDERIZAÇÃO DE LAYOUT ====================
    
    # CASO 1: TEM CATÁLOGO CARREGADO
    if file_bytes_cat:
        col_esquerda, col_direita = st.columns([1, 1])

        with col_esquerda:
            if pagina_detectada < 0:
                st.info(f"💡 Lote {num_lote} não localizado automaticamente no catálogo. Selecione a página:")
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
                    st.json(dados_catalogo)

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

            st.markdown("### 🎤 GATILHOS DE PISTA")
            if dados_finais and dados_finais.get("gatilhos"):
                for g in dados_finais["gatilhos"]:
                    st.markdown(f'<div class="gatilho-card">🔥 {g}</div>', unsafe_allow_html=True)

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
            else:
                st.info("Carregando gatilhos...")

if __name__ == "__main__":
    run()
