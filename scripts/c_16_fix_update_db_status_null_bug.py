"""
c_16_fix_update_db_status_null_bug.py

BUG CRÍTICO descoberto na exec 21167:

  update_db_campanha tinha:
    SET status = COALESCE(
      NULLIF('{{ $json.novo_status }}'::text, 'null'),
      NULLIF('{{ $json.novo_status }}'::text, ''),
      status
    )

  Quando novo_status é JS null (caso ALTERAR_VERBA, ALTERAR_PUBLICO, ALTERAR_GEO),
  o n8n renderiza como string "null". A query vira:

    COALESCE(
      NULLIF('null', 'null'),  -- NULL ✓
      NULLIF('null', ''),      -- 'null' (não é vazio!) ✗
      status                   -- pulado
    ) = 'null' (string literal de 4 chars!)

  Resultado: AP 7 ficou com status='null' (string) no DB. Não passou em
  nenhum filtro de list_campanhas (que espera PAUSED/ACTIVE/etc).

Fix: NULLIF aninhado — ambos 'null' E '' viram NULL antes do COALESCE:

    SET status = COALESCE(
      NULLIF(NULLIF('{{ $json.novo_status }}'::text, 'null'), ''),
      status
    )
"""

import sys
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow

WF_ID = 'fBUin1UPt5xJEp6g'
wf = get_workflow(WF_ID)

fixes_applied = []
fixes_failed = []

OLD_LINE = (
    "SET status = COALESCE("
    "NULLIF('{{ $json.novo_status }}'::text, 'null'), "
    "NULLIF('{{ $json.novo_status }}'::text, ''), "
    "status),"
)

NEW_LINE = (
    "SET status = COALESCE("
    "NULLIF(NULLIF('{{ $json.novo_status }}'::text, 'null'), ''), "
    "status),"
)

for node in wf['nodes']:
    if node['name'] != 'update_db_campanha':
        continue

    query = node['parameters'].get('query', '')

    if OLD_LINE in query:
        new_query = query.replace(OLD_LINE, NEW_LINE)
        node['parameters']['query'] = new_query
        fixes_applied.append('update_db_campanha: NULLIF aninhado corrige status="null" literal')
    else:
        fixes_failed.append('update_db_campanha: padrão antigo do COALESCE não encontrado')
    break


print("=== FIXES APLICADOS ===")
for f in fixes_applied:
    print(f"  ✅ {f}")

print("\n=== FIXES FALHADOS ===")
for f in fixes_failed:
    print(f"  ❌ {f}")

if not fixes_failed:
    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'],
                    connections=wf['connections'], settings=clean_settings)
    print(f"\n✅ Workflow '{WF_ID}' atualizado com sucesso.")
else:
    print(f"\n⚠️  {len(fixes_failed)} fix(es) falharam — workflow NÃO salvo.")
    sys.exit(1)
