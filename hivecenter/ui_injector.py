"""
V8.0 The Singularity: Canvas Injection (UI Bending)
Ajanın statik metin tabanlı sınırları aşıp, kullanıcının Dashboard'una doğrudan 
HTML/React/CSS veya 3D grafik bileşenleri basmasını sağlar.
"""

def prepare_ui_payload(code_content: str, component_type: str = "html") -> str:
    """
    Wraps the code in a special UI_BENDING_RENDER token so the Chrome App/Dashboard
    frontend can catch it and `dangerouslySetInnerHTML` or evaluate it as Mermaid/React.
    """
    
    # Secure or encode the payload logically for the frontend
    payload = code_content.strip()
    
    if component_type.lower() == "mermaid":
        # Format for mermaid renderer
        payload = f"<div class='mermaid'>{payload}</div>"
        
    wrapper = f"\\n\\n[[UI_BENDING_RENDER_START]]\\n{payload}\\n[[UI_BENDING_RENDER_END]]\\n\\n"
    
    return f"CANVAS INJECTION SUCCESSFUL: Sent a live {component_type.upper()} component to the user's screen!\\n" + wrapper
