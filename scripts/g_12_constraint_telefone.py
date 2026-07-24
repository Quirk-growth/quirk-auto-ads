# scripts/g_12_constraint_telefone.py
# Parte B: CHECK constraint em auto_ads.clientes.telefone exigindo a forma canonica BR.
# conversas e campanhas herdam via FK -> nao precisam de constraint propria.
#   python3 g_12_constraint_telefone.py          -> so verifica a pre-condicao
#   python3 g_12_constraint_telefone.py deploy   -> cria a constraint
import sys, psycopg2

DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"
REGEX = r"^55[0-9]{2}9[0-9]{8}$"
u = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')
conn = psycopg2.connect(u); cur = conn.cursor()

cur.execute("SELECT telefone FROM auto_ads.clientes WHERE NOT (telefone !~ '^55' OR telefone ~ %s)", [REGEX])
ruins = cur.fetchall()
print("linhas que violariam:", ruins if ruins else "nenhuma")
if ruins:
    print("ABORTAR: corrija esses telefones antes."); sys.exit(1)

if not DEPLOY:
    print("[DRY-RUN] pré-condição OK — rode com 'deploy' pra criar a constraint."); sys.exit(0)

cur.execute("""
ALTER TABLE auto_ads.clientes
  ADD CONSTRAINT clientes_telefone_canonico
  CHECK (telefone !~ '^55' OR telefone ~ '^55[0-9]{2}9[0-9]{8}$')
""")
conn.commit()
print("CONSTRAINT criada: clientes_telefone_canonico")
conn.close()
