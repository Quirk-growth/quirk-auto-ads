"""
c_17_migrate_status_null_corrupted.py

Migration corretiva: 3 campanhas tiveram status corrompido para a string
literal 'null' pelo bug do COALESCE/NULLIF no update_db_campanha (corrigido
em c_16). Status correto reconstituído via auto_ads.audit_log:

  id=31  Apartamento 2Q Setor Bueno (06-06 15:37, sem PAUSAR/REATIVAR)
         → CREATED_PAUSED
  id=32  AP 10 - Niver Nana 06.06 (último PAUSAR ok em 08-06 00:52)
         → PAUSED
  id=33  AP 7 - Yuri Vitória (último PAUSAR ok em 08-06 15:31)
         → PAUSED
"""

import psycopg2

FIXES = [
    (31, 'CREATED_PAUSED'),
    (32, 'PAUSED'),
    (33, 'PAUSED'),
]

db_url = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')

conn = psycopg2.connect(db_url)
cur = conn.cursor()

# Pré-check: confirmar que ainda estão corrompidas
cur.execute("SELECT id, status FROM auto_ads.campanhas WHERE id IN (31,32,33) ORDER BY id")
before = dict(cur.fetchall())
print("=== ANTES ===")
for cid, st in before.items():
    print(f"  id={cid}  status={st!r}")

unexpected = {cid: st for cid, st in before.items() if st != 'null'}
if unexpected:
    print(f"\n⚠️  Algum status já não é 'null': {unexpected}")
    print("   ABORTANDO pra evitar sobrescrever mudança feita manualmente.")
    conn.close()
    raise SystemExit(1)

# Aplica
print("\n=== APLICANDO ===")
for cid, novo_status in FIXES:
    cur.execute(
        "UPDATE auto_ads.campanhas SET status=%s, ultima_alteracao=NOW() WHERE id=%s",
        (novo_status, cid),
    )
    print(f"  id={cid} → status={novo_status}  ({cur.rowcount} row affected)")

# Audit
for cid, novo_status in FIXES:
    cur.execute(
        """INSERT INTO auto_ads.audit_log (telefone, evento, detalhes, ts)
           VALUES (
             (SELECT telefone FROM auto_ads.campanhas WHERE id=%s),
             'migration_status_null_fix',
             %s::jsonb,
             NOW()
           )""",
        (cid, f'{{"campanha_id_db": {cid}, "novo_status": "{novo_status}", "motivo": "bug_coalesce_nullif_c16", "migration": "c_17"}}'),
    )

conn.commit()

# Pós-check
cur.execute("SELECT id, status FROM auto_ads.campanhas WHERE id IN (31,32,33) ORDER BY id")
after = dict(cur.fetchall())
print("\n=== DEPOIS ===")
for cid, st in after.items():
    print(f"  id={cid}  status={st!r}")

# Verificação final: não pode mais existir status='null'
cur.execute("SELECT count(*) FROM auto_ads.campanhas WHERE status='null' OR status IS NULL OR status=''")
restantes = cur.fetchone()[0]
print(f"\n  Campanhas restantes com status corrompido: {restantes}")
assert restantes == 0, f"Ainda existem {restantes} corrompidas — investigar"

conn.close()
print("\n✅ Migration c_17 aplicada com sucesso.")
