"""
c_18_fix_confirm_msg_raio.py

Bug: na mensagem de confirmação do ALTERAR_GEO, quando o user manda texto
livre (ex: "Bairro: Brasilândia em São Paulo, raio de 5 km"), o
process_gestao_step grava `nv = {tipo:'geo_livre', descricao:'...'}` sem
parsear raio_km. O extrator LLM só roda depois do SIM. Resultado: o
build_gestao_response caía no fallback `raio_display = 17` e mostrava
ao user "raio 17km" mesmo ele tendo pedido 5km no próprio texto.

Fix: regex no próprio build_gestao_response — extrai número antes de "km"
da descrição. Se a descrição já contém "Nkm", não duplica; se não tem,
adiciona "raio Xkm" usando o valor extraído (sem cair em 17 default).
"""

import sys
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow

WF_ID = 'fBUin1UPt5xJEp6g'
wf = get_workflow(WF_ID)

fixes_applied = []
fixes_failed = []

OLD = """\
  else if (verbo === 'ALTERAR_GEO') {
    const raio_pedido = nv?.raio_km;
    const nova_loc = nv?.cidade || nv?.descricao || 'nova localização';
    const raio_display = (typeof raio_pedido !== 'number') ? 17 : Math.max(1, Math.min(80, raio_pedido));
    resumo = `trocar geo de "${sel.nome}" → ${nova_loc}, raio ${raio_display}km`;
  }"""

NEW = """\
  else if (verbo === 'ALTERAR_GEO') {
    const raio_pedido = nv?.raio_km;
    const nova_loc = nv?.cidade || nv?.descricao || 'nova localização';
    // Extrai raio do número-antes-de-km na descrição quando raio_km não veio estruturado (geo_livre)
    let raio_display = null;
    if (typeof raio_pedido === 'number') {
      raio_display = Math.max(1, Math.min(80, raio_pedido));
    } else if (typeof nv?.descricao === 'string') {
      const m = nv.descricao.match(/(\\d+(?:[.,]\\d+)?)\\s*km/i);
      if (m) raio_display = Math.max(1, Math.min(80, parseFloat(m[1].replace(',', '.'))));
    }
    const jaTemKm = /\\d+\\s*km/i.test(String(nova_loc));
    if (raio_display != null && !jaTemKm) {
      resumo = `trocar geo de "${sel.nome}" → ${nova_loc}, raio ${raio_display}km`;
    } else {
      // Texto já contém raio (jaTemKm) ou raio desconhecido — não duplicar nem inventar 17
      resumo = `trocar geo de "${sel.nome}" → ${nova_loc}`;
    }
  }"""

for node in wf['nodes']:
    if node['name'] != 'build_gestao_response':
        continue
    code = node['parameters']['jsCode']
    if OLD in code:
        node['parameters']['jsCode'] = code.replace(OLD, NEW)
        fixes_applied.append('build_gestao_response: ALTERAR_GEO extrai raio da descrição (geo_livre)')
    else:
        fixes_failed.append('build_gestao_response: padrão antigo não encontrado')
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
