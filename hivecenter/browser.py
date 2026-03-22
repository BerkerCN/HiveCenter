from playwright.sync_api import sync_playwright
import time
import os

def run_browser_test(url: str, commands_text: str, ws: str) -> str:
    out = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            out.append(f"Navigating to {url}...")
            
            try:
                page.goto(url, wait_until="load", timeout=15000)
            except Exception as nav_e:
                out.append(f"Warning on navigation: {nav_e}")
            
            for line in commands_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split(" ", 1)
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else ""
                
                try:
                    if cmd == "click":
                        page.click(arg, timeout=5000)
                        out.append(f"CLICK: {arg}")
                    elif cmd == "type":
                        sub_parts = arg.split(" ", 1)
                        if len(sub_parts) == 2:
                            sel, txt = sub_parts
                            if txt.startswith('"') and txt.endswith('"'):
                                txt = txt[1:-1]
                            elif txt.startswith("'") and txt.endswith("'"):
                                txt = txt[1:-1]
                            page.fill(sel, txt, timeout=5000)
                            out.append(f"TYPE: {sel} <- {txt}")
                        else:
                            out.append(f"ERROR: type requires selector and text. '{arg}'")
                    elif cmd == "wait":
                        time.sleep(float(arg))
                        out.append(f"WAIT: {arg} seconds")
                    elif cmd == "text":
                        txt = page.locator(arg).text_content(timeout=5000)
                        out.append(f"TEXT ({arg}): {txt}")
                    elif cmd == "screenshot":
                        path = os.path.join(ws, "browser_test.png")
                        page.screenshot(path=path)
                        out.append(f"SCREENSHOT saved to {path} (Check workspace!)")
                    else:
                        out.append(f"UNKNOWN BROWSER COMMAND: {cmd}")
                except Exception as step_e:
                    out.append(f"ERROR ON '{line}': {step_e}")
                    
                    # AGI Yükseltmesi (V5.0): Bilişsel Görüş (DOM Auto-Healing)
                    if "Timeout" in str(step_e) or "waiting for" in str(step_e) or "not found" in str(step_e).lower():
                        try:
                            js_extract = """
                            () => {
                                function buildTree(node) {
                                    if (node.nodeType === Node.TEXT_NODE) {
                                        let text = node.textContent.trim();
                                        return text ? text : null;
                                    }
                                    if (node.nodeType !== Node.ELEMENT_NODE) return null;
                                    if (['SCRIPT', 'STYLE', 'SVG', 'NOSCRIPT', 'IFRAME'].includes(node.tagName)) return null;
                                    
                                    let tag = node.tagName.toLowerCase();
                                    let id = node.id ? '#' + node.id : '';
                                    let cls = node.className && typeof node.className === 'string' ? '.' + node.className.split(' ').join('.') : '';
                                    let name = tag + id + cls;
                                    
                                    let children = Array.from(node.childNodes).map(buildTree).filter(Boolean);
                                        
                                    if (children.length === 0) return `<${name}></${tag}>`;
                                    if (children.length === 1 && typeof children[0] === 'string' && !children[0].startsWith('<')) {
                                        return `<${name}>${children[0]}</${tag}>`;
                                    }
                                    return `<${name}>\n  ` + children.join('\n').replace(/\n/g, '\n  ') + `\n</${tag}>`;
                                }
                                return buildTree(document.body);
                            }
                            """
                            dom_tree = page.evaluate(js_extract)
                            out.append(f"\n[DOM AUTO-HEALING] Hedef element ekranda bulunamadı. İşte o anki sayfanın iskeleti (DOM Tree), hatanı bulup düzeltmen için çıkartıldı:\n{dom_tree[:3000]}")
                        except Exception as dom_e:
                            out.append(f"[DOM AUTO-HEALING ERROR]: İskelet çıkarılamadı: {dom_e}")
                    
            out.append("\nDOM Summary (Body text):")
            try:
                # Get a tiny snippet of the body text to prove it rendered
                body_text = page.locator("body").inner_text(timeout=3000)
                out.append(body_text[:1500] if body_text else "[Empty body]")
            except Exception as e2:
                out.append(f"Could not read body: {e2}")
                
            browser.close()
    except ImportError:
        out.append("CRITICAL ERROR: Playwright is not installed. Tell the Architect to run `pip install playwright`.")
    except Exception as e:
        out.append(f"BROWSER CRITICAL ERROR: {e}")
        
    return "\n".join(out)
