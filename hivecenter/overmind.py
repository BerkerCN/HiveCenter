"""
V6.0 AGI Feature: OVERMIND (AST/LSP Sync)
Allows the agent to perceive code files not as text strings, but as structural hierarchies (Classes, Methods, Arguments) automatically.
"""
import ast

def parse_file_to_ast_tree(filepath: str) -> str:
    """
    Reads a python file and returns its architectural skeleton without the body code.
    Helps the LLM understand the entire file in 1/10th of the tokens.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
            
        tree = ast.parse(source)
        
        output = [f"--- AST Skeleton for {filepath} ---"]
        
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                output.append(f"class {node.name}:")
                for sub_node in node.body:
                    if isinstance(sub_node, ast.FunctionDef):
                        args = [a.arg for a in sub_node.args.args]
                        output.append(f"    def {sub_node.name}({', '.join(args)}):")
                        if ast.get_docstring(sub_node):
                            ds = ast.get_docstring(sub_node).replace('\n', ' ')
                            output.append(f"        # Doc: {ds}")
            elif isinstance(node, ast.FunctionDef):
                args = [a.arg for a in node.args.args]
                output.append(f"def {node.name}({', '.join(args)}):")
                if ast.get_docstring(node):
                    ds = ast.get_docstring(node).replace('\n', ' ')
                    output.append(f"    # Doc: {ds}")
                    
        return "\n".join(output)
    except Exception as e:
        return f"[OVERMIND ERROR] Could not parse AST for {filepath}: {e}"

def inject_ast_context(filepaths: list[str]) -> str:
    res = []
    for fp in filepaths:
        res.append(parse_file_to_ast_tree(fp))
    return "\\n\\n".join(res)
