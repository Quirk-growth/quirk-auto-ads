import json, re, psycopg2, n8n_api

u = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')
c = psycopg2.connect(u).cursor()
c.execute("""
SELECT tc.table_name, kcu.column_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'auto_ads'
  AND ccu.table_name = 'clientes' AND ccu.column_name = 'telefone'
""")
print("FKs -> clientes.telefone:", c.fetchall())

wf = n8n_api.get_workflow('fBUin1UPt5xJEp6g')
N = {n['name']: n for n in wf['nodes']}
for nm in ['classify_status', 'select_conversa', 'load_estado', 'build_historico', 'upsert_conversa', 'persist_estado_etapa']:
    if nm not in N:
        continue
    raw = json.dumps(N[nm]['parameters'], ensure_ascii=False)
    # como o telefone entra nas queries/expressoes
    hits = re.findall(r"telefone[^\n]{0,45}", raw)
    print(f"\n[{nm}]")
    for h in hits[:4]:
        print("   ", h[:90])
