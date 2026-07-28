# scripts/g_21_unique_assets.py
# Blindagem multi-tenant: nenhum asset (ad_account_id / page_id) pode pertencer a dois
# clientes ao mesmo tempo. Fecha a race de dois onboardings simultaneos ("contas
# trocadas") e QUALQUER dupla-atribuicao (erro manual, bug de deteccao): o commit em
# update_cliente_ativo do 2o cliente falha de forma VISIVEL em vez de cruzar dados.
# indice parcial (WHERE NOT NULL) -> permite varios NULL (nao atribuidos ainda).
#   python3 g_21_unique_assets.py          -> so checa pre-condicao (dry-run)
#   python3 g_21_unique_assets.py deploy   -> cria os indices
import sys, psycopg2

DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"
u = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')
conn = psycopg2.connect(u); cur = conn.cursor()

IDX = [
    ("clientes_ad_account_id_uniq", "ad_account_id"),
    ("clientes_page_id_uniq", "page_id"),
]

# pre-condicao: sem duplicados
abortar = False
for _, col in IDX:
    cur.execute(f"""SELECT {col}, count(*) FROM auto_ads.clientes
                    WHERE {col} IS NOT NULL GROUP BY {col} HAVING count(*) > 1""")
    dups = cur.fetchall()
    print(f"  {col}: duplicados =", dups if dups else "nenhum")
    if dups: abortar = True
if abortar:
    print("ABORTAR: resolva os duplicados antes de criar o indice."); sys.exit(1)

if not DEPLOY:
    print("[DRY-RUN] pre-condicao OK — rode com 'deploy' pra criar os indices."); sys.exit(0)

for nome, col in IDX:
    cur.execute(f"""CREATE UNIQUE INDEX IF NOT EXISTS {nome}
                    ON auto_ads.clientes ({col}) WHERE {col} IS NOT NULL""")
    print(f"  índice criado: {nome} ({col})")
conn.commit()
conn.close()
print("OK — assets agora são únicos por cliente.")
