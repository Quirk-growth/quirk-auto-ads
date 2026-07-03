# scripts/f_00_admin_passphrase.py
# Insere/atualiza admin_passphrase e admin_email em auto_ads.config.
# Uso: python3 f_00_admin_passphrase.py '<passphrase>' ['<admin_email>']
import sys, psycopg2

db_url = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')

PASS = sys.argv[1] if len(sys.argv) > 1 else None
EMAIL = sys.argv[2] if len(sys.argv) > 2 else 'contato@quirkgrowth.com.br'
if not PASS:
    print("uso: python3 f_00_admin_passphrase.py '<passphrase>' ['<admin_email>']"); sys.exit(1)

conn = psycopg2.connect(db_url); cur = conn.cursor()
cur.execute(
    """INSERT INTO auto_ads.config (chave, valor) VALUES
           ('admin_passphrase', %s),
           ('admin_email', %s)
       ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor""",
    [PASS, EMAIL],
)
conn.commit(); conn.close()
print("admin_passphrase e admin_email definidos.")
