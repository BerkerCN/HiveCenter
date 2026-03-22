"""HiveCenter SQL Admin: Ajanın shell kurulumları yapmadan direkt DB ile konuşmasını sağlar."""
import os

def execute_sql(db_url: str, query: str) -> str:
    # 1. Yerleşik SQLite desteği (Ek bir pakete ihtiyaç duymaz)
    if db_url.startswith("sqlite://"):
        import sqlite3
        path = db_url.replace("sqlite://", "").replace("sqlite:///", "")
        
        # Eğer yol lokal ise, absolute path olmasını varsayalım veya olduğu gibi bırakalım
        try:
            conn = sqlite3.connect(path)
            cursor = conn.cursor()
            cursor.execute(query)
            
            if query.strip().upper().startswith("SELECT") or query.strip().upper().startswith("PRAGMA"):
                rows = cursor.fetchall()
                cols = [desc[0] for desc in cursor.description] if cursor.description else []
                res = f"Columns: {', '.join(cols)}\n"
                for r in rows:
                    res += str(r) + "\n"
                conn.commit()
                conn.close()
                return res if rows else "Sorgu başarılı, sıfır satır döndü."
            else:
                conn.commit()
                rowcount = cursor.rowcount
                conn.close()
                return f"SUCCESS. Etkilenen satır sayısı: {rowcount}"
        except Exception as e:
            return f"SQL Error (SQLite): {str(e)}"
            
    # 2. Harici Veritabanları (Postgres, MySQL vb. -> SQLAlchemy kullanır)
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(db_url)
        with engine.begin() as conn: # Otomatik commit
            result = conn.execute(text(query))
            if result.returns_rows:
                rows = result.fetchall()
                cols = result.keys()
                res = f"Columns: {', '.join(cols)}\n"
                for r in rows:
                    res += str(r) + "\n"
                return res if rows else "Sorgu başarılı, sıfır satır döndü."
            else:
                return f"SUCCESS. Etkilenen satır sayısı: {result.rowcount}"
    except ImportError:
        return "SQL Error: PostgreSQL/MySQL sorguları için 'sqlalchemy' gereklidir. Önce [SHELL: pip install sqlalchemy psycopg2-binary] komutunu kullanın."
    except Exception as e:
        return f"SQL Error: {str(e)}"
