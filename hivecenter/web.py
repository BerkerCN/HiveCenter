"""HiveCenter Web Ajanı: Advanced Scraper and Searcher using duckduckgo_search & markdownify"""
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
import markdownify
from duckduckgo_search import DDGS

def web_search(query: str, max_results: int = 5) -> str:
    """DuckDuckGo API üzerinden arama yapar ve özet sonuçları döndürür."""
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(f"Title: {r.get('title')}\nURL: {r.get('href')}\nSnippet: {r.get('body')}")
        
        return "\n\n".join(results) if results else "Arama sonucu bulunamadı."
    except Exception as e:
        # Fallback if DDGS fails
        return f"Web Search Error: {e}"

def web_read(url: str, query: str = None, max_chars: int = 20000) -> str:
    """Verilen URL'in içeriğini çeker ve temiz bir Markdown formatına çevirir. Eğer query verilirse RAG ile filtreler."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode('utf-8', errors='ignore')
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Gereksiz etiketleri sil
        for element in soup(["script", "style", "nav", "footer", "aside", "header"]):
            element.decompose()
            
        md_text = markdownify.markdownify(str(soup), heading_style="ATX").strip()
        import re
        md_text = re.sub(r'\n{3,}', '\n\n', md_text)
        
        if query:
            try:
                from hivecenter.embeddings import ollama_embed, cosine
                lines = md_text.split('\n')
                chunks = []
                curr = ""
                for line in lines:
                    curr += line + "\n"
                    if len(curr) > 1500:
                        chunks.append(curr)
                        curr = ""
                if curr: chunks.append(curr)
                
                q_emb = ollama_embed("nomic-embed-text", query)
                if q_emb:
                    scored = []
                    for chunk in chunks:
                        c_emb = ollama_embed("nomic-embed-text", chunk[:3000])
                        if c_emb:
                            s = cosine(q_emb, c_emb)
                            scored.append((s, chunk))
                    scored.sort(key=lambda x: -x[0])
                    top = [c for s, c in scored[:4]]
                    return f"--- {url} (RAG Filtered for '{query}') ---\n" + "\n...\n".join(top)
            except Exception as e:
                pass # Fallback to normal if RAG fails
                
        return md_text[:max_chars] + ("\n...[METİN KESİLDİ]" if len(md_text) > max_chars else "")
    except Exception as e:
        return f"Fetch URL Error: {e}"
