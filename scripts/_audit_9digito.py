# scripts/_audit_9digito.py
# Guarda do 9o digito. Checa o que e CONFIAVEL e importa:
#   1) os pontos de canonicalizacao (entrada texto, entrada midia, escrita/gateway)
#   2) as buscas tolerantes de cliente
#   3) o invariante no banco (nenhum telefone BR sem o 9)
#   4) a CHECK constraint ativa
#
# NAO tenta auditar no por no: rastrear a procedencia do telefone em cadeias de $json
# no n8n nao e confiavel estaticamente. Isso e desnecessario porque a constraint rejeita
# qualquer gravacao fora do padrao, venha de onde vier.
#
#   python3 _audit_9digito.py     -> sai 0 se tudo ok, 1 se algo regrediu
import json, sys, n8n_api, psycopg2

ok = True
print("=" * 70)
print("GUARDA DO 9o DIGITO")
print("=" * 70)

# 1) pontos de canonicalizacao
print("\n[1] Pontos de canonicalizacao (devem aplicar a regra com9)")
PONTOS = [
    ("fBUin1UPt5xJEp6g", "normalize_phone",       "entrada TEXTO"),
    ("fBUin1UPt5xJEp6g", "media_normalize_phone", "entrada MIDIA"),
    ("2ZnZqb4wFous4uEs", "parse_payment",         "ESCRITA (gateway Asaas)"),
]
for wid, node, papel in PONTOS:
    try:
        jc = {n["name"]: n for n in n8n_api.get_workflow(wid)["nodes"]}[node]["parameters"].get("jsCode", "")
        tem = ("com9(" in jc) or ("Canonicaliza BR" in jc)
        print(f"  {'✅' if tem else '❌'} {node:<24} {papel}")
        ok = ok and tem
    except Exception as e:
        print(f"  ❌ {node:<24} erro: {str(e)[:50]}"); ok = False

# 2) buscas tolerantes
print("\n[2] Buscas de cliente (devem casar qualquer variante)")
for wid, node in [("fBUin1UPt5xJEp6g", "select_cliente"), ("fBUin1UPt5xJEp6g", "media_select_cliente")]:
    try:
        p = json.dumps({n["name"]: n for n in n8n_api.get_workflow(wid)["nodes"]}[node]["parameters"], ensure_ascii=False)
        tem = "telefone IN (" in p or "telefone_variantes" in p
        print(f"  {'✅' if tem else '❌'} {node:<24} tolerante ao 9")
        ok = ok and tem
    except Exception as e:
        print(f"  ❌ {node:<24} erro: {str(e)[:50]}"); ok = False

# 3) invariante no banco
print("\n[3] Banco — nenhum telefone BR fora do padrao canonico")
u = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')
cur = psycopg2.connect(u).cursor()
for t in ["clientes", "conversas", "campanhas"]:
    cur.execute(f"""SELECT count(*) FROM auto_ads.{t}
                    WHERE telefone ~ '^55' AND telefone !~ '^55[0-9]{{2}}9[0-9]{{8}}$'""")
    fora = cur.fetchone()[0]
    cur.execute(f"SELECT count(*) FROM auto_ads.{t}")
    print(f"  {'✅' if fora == 0 else '❌'} {t:<12} total={cur.fetchone()[0]:<4} fora do padrao={fora}")
    ok = ok and fora == 0

# 4) constraint
print("\n[4] Trava no banco")
cur.execute("""SELECT 1 FROM pg_constraint
               WHERE conrelid='auto_ads.clientes'::regclass AND conname='clientes_telefone_canonico'""")
tem = cur.fetchone() is not None
print(f"  {'✅' if tem else '❌'} constraint clientes_telefone_canonico {'ativa' if tem else 'AUSENTE'}")
ok = ok and tem

print("\n" + "=" * 70)
print("RESULTADO: ✅ TUDO OK" if ok else "RESULTADO: ❌ REGRESSAO DETECTADA")
sys.exit(0 if ok else 1)
