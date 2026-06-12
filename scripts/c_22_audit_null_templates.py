"""
c_22_audit_null_templates.py

Auditoria sistemática de templates `{{ $json.X }}` em SQL/string que
poderiam virar a string literal "null" quando X é JS null/undefined.

Investiguei 10 templates suspeitos (sem fallback explícito nem proteção
COALESCE/NULLIF). Conclusões:

  RISCO DE CORRUPÇÃO (vira 'null' string e fica gravado):
    - prep_persist_gestao: etapa_atual no fallback final pode ser
      cur.etapa_atual=null → vira 'null' em INSERT/UPDATE de
      auto_ads.conversas.estado_json.etapa_atual.
    → APLICAR FIX (defensive default)

  SEGUROS (verificados):
    - upsert_conversa.telefone: vem de normalize_phone, sempre preenchido
      antes pelo if_cadastrado.
    - upsert_conversa.historico_atualizado.replace(): se null, .replace()
      lança erro de runtime — falha visível, não corrupção silenciosa.
    - persist_estado_gestao.telefone: idem.
    - persist_estado_gestao.gestao_json.replace(): idem.
    - persist_estado_gestao.etapa_atual: vem de prep_persist_gestao (fix
      acima cobre).
    - update_db_campanha.verbo: verbo é sempre setado em check_gestao_result
      e prep_update_db; se virasse 'null', cairia no CASE...ELSE preservando
      json_extrator (não corrompe nada).

Fix único aplicado: blindar prep_persist_gestao.etapa_atual.
"""

import sys
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow

WF_ID = 'fBUin1UPt5xJEp6g'
wf = get_workflow(WF_ID)

fixes_applied = []
fixes_failed = []

# ─────────────────────────────────────────────────────────────
# prep_persist_gestao: defensive default no return
# ─────────────────────────────────────────────────────────────

OLD = """\
return [{
  json: {
    telefone: $('normalize_phone').first().json.telefone_normalizado,
    gestao_json: JSON.stringify(gestao),
    etapa_atual
  }
}];"""

NEW = """\
// Blindagem: etapa_atual nunca pode chegar null/undefined no SQL (vira string 'null')
const etapa_atual_safe = (etapa_atual && String(etapa_atual).trim() !== '' && String(etapa_atual) !== 'null')
  ? etapa_atual
  : 'em_gestao';

return [{
  json: {
    telefone: $('normalize_phone').first().json.telefone_normalizado,
    gestao_json: JSON.stringify(gestao || null),
    etapa_atual: etapa_atual_safe
  }
}];"""

for node in wf['nodes']:
    if node['name'] != 'prep_persist_gestao':
        continue
    code = node['parameters']['jsCode']
    if OLD in code:
        node['parameters']['jsCode'] = code.replace(OLD, NEW)
        fixes_applied.append('prep_persist_gestao: blindagem de etapa_atual contra null')
    else:
        fixes_failed.append('prep_persist_gestao: bloco de return não encontrado')
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
    print(f"\n✅ Workflow '{WF_ID}' atualizado.")
else:
    sys.exit(1)
