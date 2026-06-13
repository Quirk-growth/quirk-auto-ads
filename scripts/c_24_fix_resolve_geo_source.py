"""
c_24_fix_resolve_geo_source.py

Bug encontrado no teste E2E de criação (13/06/2026):
resolve_geo_criacao quebrava com "Cannot read properties of undefined
(reading 'brief')" porque lia $('persist_brief').first().json.estado,
mas persist_brief é um nó Postgres que retorna apenas {success: true}.

A fonte correta do estado é merge_brief — esse é o nó Code que monta
o estado.brief antes da persistência.

Fix: 1 char de mudança — persist_brief → merge_brief.
"""

import sys
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow

WF_ID = 'fBUin1UPt5xJEp6g'
wf = get_workflow(WF_ID)
applied = False
for n in wf['nodes']:
    if n['name'] == 'resolve_geo_criacao':
        code = n['parameters']['jsCode']
        new = code.replace("$('persist_brief').first().json.estado",
                           "$('merge_brief').first().json.estado")
        if new != code:
            n['parameters']['jsCode'] = new
            applied = True
        break

if applied:
    clean = {'executionOrder': wf.get('settings', {}).get('executionOrder','v1')}
    update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'],
                    connections=wf['connections'], settings=clean)
    print("✅ resolve_geo_criacao: estado lido de merge_brief")
else:
    print("ℹ️  fix já aplicado ao vivo (este script é só registro)")
