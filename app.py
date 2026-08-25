import streamlit as st
import pdfplumber
import requests
import json
import re
from io import BytesIO

# Importa a biblioteca para buscar na internet
try:
    from duckduckgo_search import DDGS
except ImportError:
    st.error("⚠️ Falta instalar o pacote de busca. Adicione 'duckduckgo-search' no seu requirements.txt")

# Configuração da Página
st.set_page_config(page_title="Painel Web Search", page_icon="🌐", layout="wide")

# ==================== CSS ====================
st.markdown("""
<style>
    .abertura { background: linear-gradient(135deg, #1E3A8A 0%, #3B82F6 100%); color: white; padding: 25px; border-radius: 15px; font-size: 26px; font-weight: bold; text-align: center; font-style: italic; margin-bottom: 20px;}
    .linha-oe { background: #1E293B; color: #34D399; padding: 15px; border-radius: 10px; font-family: monospace; font-size: 16px; border-left: 5px solid #34D399; margin-bottom: 20px;}
    .parecer { background: #0F172A; color: white; padding: 20px; border-radius: 10px; border: 1px solid #334155; font-size: 16px; line-height: 1.6;}
    .net-box { background: #451A03; color: #FDBA74; padding: 15px; border-radius: 10px; border-left: 5px solid #F97316; margin-bottom: 20px;}
    .gatilho { background: linear-gradient(90deg, #EC4899 0%, #8B5CF6 100%); color: white; padding: 12px; border-radius: 10px; font-weight: bold; font-size: 18px; margin-bottom: 10px;}
</style>
""", unsafe_allow_html=True)

# ==================== FUNÇÕES ====================
def obter_chave_deepseek():
    """Busca a chave da API do DeepSeek no st.secrets"""
    try:
        if "DEEPSEEK_API_KEY" in st.secrets:
            return st.secrets["DEEPSEEK_API_KEY"]
    except:
        pass
    return ""

@st.cache_data(show_spinner=False)
def ler_ordem_entrada(file_bytes, api_key):
    """Extrai texto do PDF e usa o DeepSeek para listar os lotes estruturados"""
    texto_completo = ""
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                texto_completo += (page.extract_text() or "") + "\n"
    except Exception as e:
        st.error(f"Erro ao abrir o PDF: {e}")
        return []

    prompt = f"""
    Extraia os lotes desta Ordem de Entrada.
    Retorne APENAS UM JSON com a lista 'lotes'. Para cada lote, extraia: 
    - "numero_lote": apenas o número (ex: "01")
    - "nome_animal": o nome limpo do animal
    - "linha_original": a linha inteira exatamente como está no PDF
    
    TEXTO: {texto_completo[:8000]}
    
    FORMATO JSON ESPERADO:
    {{
      "lotes": [
         {{"numero_lote": "01", "nome_animal": "NOME DO ANIMAL", "linha_original": "01 100% NOME DO ANIMAL..."}}
      ]
    }}
    """
    
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.1
    }
    
    try:
        res = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=60).json()
        dados = json.loads(res['choices'][0]['message']['content'])
        return dados.get("lotes", [])
    except Exception as e:
        st.error("Falha ao ler a Ordem com DeepSeek. Verifique o limite da sua API.")
        return []

@st.cache_data(show_spinner=False)
def buscar_na_internet(nome_animal):
    """Pesquisa o nome do animal no DuckDuckGo para encontrar pedigrees, premiações e histórico"""
    if not nome_animal or len(nome_animal) < 4:
        return "Nome muito curto para busca confiável."
    
    try:
        query = f'"{nome_animal}" (leilão OR pedigree OR abcz OR abccmm OR cavalo OR nelore)'
        resultados = DDGS().text(query, max_results=3)
        texto_web = " ".join([r['body'] for r in resultados])
        return texto_web if texto_web else "Nenhuma informação extra de destaque encontrada nos buscadores."
    except Exception as e:
        return f"A busca falhou ou bloqueou a conexão temporariamente."

@st.cache_data(show_spinner=False)
def analisar_lote_com_internet(lote_dados, info_web, api_key):
    """Gera a canta do leiloeiro e os gatilhos unindo a O.E. com as informações da Internet"""
    prompt = f"""
    Você é um leiloeiro mestre de elite.
    
    DADOS DA O.E.: {lote_dados.get('linha_original', '')}
    RESULTADO DA BUSCA NA INTERNET SOBRE '{lote_dados.get('nome_animal', '')}': {info_web}
    
    Gere um material focado em converter lances:
    1. "abertura": Frase de impacto para gritar na pista (comece a venda).
    2. "resumo_internet": O que achamos na internet sobre ele (seja honesto se não achou nada relevante, diga "Animal inédito...").
    3. "parecer": Seu parecer técnico como leiloeiro animando a plateia.
    4. "gatilhos": 3 gatilhos de venda curtos e explosivos.
    
    FORMATO JSON:
    {{
        "abertura": "...",
        "resumo_internet": "...",
        "parecer": "...",
        "gatilhos": ["...", "...", "..."]
    }}
    """
    
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.4
    }
    
    try:
        res = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=30).json()
        return json.loads(res['choices'][0]['message']['content'])
    except Exception:
        return None

# ==================== INTERFACE STREAMLIT ====================
def run():
    st.title("🌐 Painel do Leiloeiro (O.E. + Internet)")

    api_key = obter_chave_deepseek()
    if not api_key:
        st.warning("⚠️ Insira sua DEEPSEEK_API_KEY nos Secrets do Streamlit para o sistema funcionar.")
        st.stop()

    with st.sidebar:
        st.header("📂 Arquivo")
        arquivo_oe = st.file_uploader("Suba a Ordem de Entrada (PDF)", type=["pdf"])

    if not arquivo_oe:
        st.info("👈 Por favor, anexe o PDF da Ordem de Entrada na barra lateral.")
        st.stop()

    # Lê a O.E. apenas uma vez
    with st.spinner("🤖 DeepSeek organizando a Ordem de Entrada..."):
        lotes = ler_ordem_entrada(arquivo_oe.getvalue(), api_key)
    
    if not lotes:
        st.error("Não foi possível extrair os lotes ou o PDF não possui padrão textual.")
        st.stop()
        
    numeros = [str(l["numero_lote"]) for l in lotes]
    
    # Controle de Navegação de Lotes
    col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])
    with col_nav2:
        lote_selecionado = st.selectbox("🎯 Selecione o Lote para Investigar:", numeros)
        
    dados_lote_atual = next((l for l in lotes if str(l["numero_lote"]) == lote_selecionado), None)
    
    if dados_lote_atual:
        st.markdown(f"### LOTE {lote_selecionado} - {dados_lote_atual.get('nome_animal', 'SEM NOME')}")
        
        # MOSTRA A LINHA DA O.E.
        st.markdown("**📋 LINHA DESCRITA NA ORDEM DE ENTRADA:**")
        st.markdown(f"<div class='linha-oe'>{dados_lote_atual.get('linha_original', '')}</div>", unsafe_allow_html=True)
        
        nome_busca = dados_lote_atual.get("nome_animal", "")
        
        # BUSCA NA INTERNET
        with st.spinner(f"🌍 Vasculhando a internet por informações sobre '{nome_busca}'..."):
            info_web = buscar_na_internet(nome_busca)
            
        # GERA A APRESENTAÇÃO
        with st.spinner("🧠 Leiloeiro IA criando a apresentação..."):
            analise = analisar_lote_com_internet(dados_lote_atual, info_web, api_key)
            
        if analise:
            # ABERTURA
            st.markdown(f"<div class='abertura'>🎙️ \"{analise.get('abertura', '')}\"</div>", unsafe_allow_html=True)
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### 🌐 O que achei na Internet")
                st.markdown(f"<div class='net-box'>🛰️ {analise.get('resumo_internet', '')}</div>", unsafe_allow_html=True)
                
                st.markdown("### 🧠 Parecer do Leiloeiro")
                st.markdown(f"<div class='parecer'>{analise.get('parecer', '')}</div>", unsafe_allow_html=True)
                
            with col2:
                st.markdown("### 🔥 Gatilhos para a Pista")
                gatilhos = analise.get('gatilhos', [])
                if gatilhos:
                    for g in gatilhos:
                        st.markdown(f"<div class='gatilho'>🚀 {g}</div>", unsafe_allow_html=True)
                else:
                    st.info("Nenhum gatilho gerado.")

if __name__ == "__main__":
    run()
