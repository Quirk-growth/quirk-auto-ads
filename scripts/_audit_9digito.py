# scripts/_audit_9digito.py
# Auditoria: TODOS os pontos onde o telefone e normalizado / buscado / gravado / usado
# pra enviar, em TODOS os workflows — e quais ja canonicalizam o 9o digito.
import json, re, n8n_api, psycopg2

WFS = {
    "fBUin1UPt5xJEp6g": "Quirk Auto Ads (principal)",
    "2ZnZqb4wFous4uEs": "Webhook Gateway (Asaas)",
    "aXuUHCG2YN2IVMN2": "Criar Cobranca",
    "7vhoapaFk2zY8ptL": "WhatsApp Cloud Inbound",
    "VgmLyPo5djHkUhLM": "Admin API",
}

def classify(name, params_json, node_type):
    """Classifica o papel do no em relacao a telefone."""
    p = params_json
    roles = []
    if "telefone_normalizado" in p and ("replace(" in p or "normalized" in p or "digits" in p):
        roles.append("NORMALIZA")
    if re.search(r"(SELECT|select).{0,200}?WHERE.{0,80}?telefone", p, re.S):
        roles.append("BUSCA")
    if re.search(r"(INSERT INTO|UPDATE)\s+auto_ads\.\w+", p) and "telefone" in p:
        roles.append("GRAVA")
    if '"to"' in p and "telefone" in p:
        roles.append("ENVIA")
    return roles

print("=" * 78)
print("AUDITORIA DO 9o DIGITO — pontos que tocam telefone")
print("=" * 78)

total_risco = []
for wid, label in WFS.items():
    try:
        wf = n8n_api.get_workflow(wid)
    except Exception as e:
        print(f"\n### {label} ({wid}) — ERRO: {e}"); continue
    print(f"\n### {label}  ({wid})")
    achou = False
    for n in wf["nodes"]:
        p = json.dumps(n.get("parameters", {}), ensure_ascii=False)
        if "telefone" not in p and "phone" not in p.lower():
            continue
        roles = classify(n["name"], p, n["type"])
        if not roles:
            continue
        achou = True
        # canonicaliza?
        canon = ("com9(" in p) or ("telefone_variantes" in p)
        tolerante = "telefone IN (" in p or "telefone_variantes" in p
        flag = "✅" if (canon or tolerante) else ("•" if "NORMALIZA" not in roles and "BUSCA" not in roles else "⚠️ ")
        print(f"  {flag} {n['name']:<28} {'/'.join(roles):<22} canon={canon} tolerante={tolerante}")
        if ("NORMALIZA" in roles or "BUSCA" in roles) and not (canon or tolerante):
            total_risco.append((label, n["name"], "/".join(roles)))
    if not achou:
        print("   (nenhum no toca telefone)")

print("\n" + "=" * 78)
print("PONTOS DE RISCO (normalizam ou buscam SEM canonicalizar/tolerar o 9):")
if total_risco:
    for w, n, r in total_risco:
        print(f"  ⚠️  [{w}] {n}  ({r})")
else:
    print("  nenhum ✅")

# DB: formatos de telefone atuais
print("\n" + "=" * 78)
print("BANCO — formatos de telefone armazenados")
u = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')
cur = psycopg2.connect(u).cursor()
for t in ["clientes", "conversas", "campanhas"]:
    try:
        cur.execute(f"SELECT telefone, length(telefone) FROM auto_ads.{t}")
        rows = cur.fetchall()
        com9 = [r[0] for r in rows if r[1] == 13]
        sem9 = [r[0] for r in rows if r[1] == 12]
        outros = [r[0] for r in rows if r[1] not in (12, 13)]
        print(f"  {t}: total={len(rows)} | com9(13)={len(com9)} | SEM9(12)={len(sem9)} {sem9[:3]} | outros={outros[:3]}")
    except Exception as e:
        print(f"  {t}: erro {e}")
