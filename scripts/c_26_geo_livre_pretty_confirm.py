"""
c_26_geo_livre_pretty_confirm.py

UX: hoje a confirmação ANTES do SIM em ALTERAR_GEO via texto livre mostra
o texto cru do usuário, ex:
  'Confirma trocar geo de "AP 7..." → Brasilandia, São Paulo SP raio de 3km? Manda SIM ou NÃO.'

Causa: process_gestao_step só grava {tipo:'geo_livre', descricao:'<texto>'}
sem parsear cidade/UF/raio. A extração só acontece depois do SIM, no
extrator_partial (LLM).

Fix: parsing local com regex (rápido, sem custo de LLM) no
build_gestao_response. Extrai cidade + UF + raio do texto livre e mostra
formatado.

Exemplos:
  "Brasilandia, São Paulo SP raio de 3km"  → "Brasilândia/SP, raio 3km"
  "Vila Madalena SP 2km"                   → "Vila Madalena/SP, raio 2km"
  "Pinheiros 5"                            → "Pinheiros, raio 5km"
  "centro de Curitiba PR raio 10"          → "centro de Curitiba/PR, raio 10km"
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

NEW = """\
  else if (verbo === 'ALTERAR_GEO') {
    // Parse local: pega cidade + UF + raio do que veio (estruturado OU texto livre)
    function parseGeoLivre(s) {
      const txt = String(s || '').trim();
      // 1) Raio: número antes de 'km' (ou no fim isolado)
      let raio = null;
      const mRaio = txt.match(/(\\d+(?:[.,]\\d+)?)\\s*km/i) || txt.match(/(\\d+(?:[.,]\\d+)?)\\s*$/);
      if (mRaio) raio = Math.max(1, Math.min(80, parseFloat(mRaio[1].replace(',', '.'))));
      // 2) UF: 2 letras maiúsculas isoladas (não confundir com palavra colada)
      let uf = null;
      const mUF = txt.match(/(?:^|[\\s,\\/])([A-Z]{2})(?=[\\s,\\/]|$)/);
      if (mUF) uf = mUF[1];
      // 3) Cidade: texto antes do raio (ou do UF se anterior), limpando ruídos
      let cidade = txt;
      // remove sufixo de raio (ex: ", raio de 3km")
      cidade = cidade.replace(/[,]?\\s*raio\\s*(de\\s*)?\\d+(?:[.,]\\d+)?\\s*km\\s*$/i, '');
      // remove sufixo de raio puro
      cidade = cidade.replace(/[,]?\\s*\\d+(?:[.,]\\d+)?\\s*km\\s*$/i, '');
      cidade = cidade.replace(/[,]?\\s*\\d+(?:[.,]\\d+)?\\s*$/, '');
      // remove UF do fim (ex: "Pinheiros SP" → "Pinheiros")
      if (uf) cidade = cidade.replace(new RegExp('[,\\\\s\\\\/]+' + uf + '\\\\s*$'), '');
      // remove prefixo "bairro:" / "localização:" / "regiao:" etc
      cidade = cidade.replace(/^(bairro|localiza[çc][aã]o|regi[aã]o|cidade)\\s*:\\s*/i, '');
      // remove vírgula trailing
      cidade = cidade.replace(/[,\\s]+$/, '').trim();
      return { cidade: cidade || txt, uf, raio };
    }

    let cidade_display, uf_display, raio_display;
    if (nv?.tipo === 'geo_estruturado') {
      cidade_display = nv?.cidade || 'nova localização';
      uf_display = nv?.estado || null;
      raio_display = (typeof nv?.raio_km === 'number') ? nv.raio_km : null;
    } else {
      const parsed = parseGeoLivre(nv?.descricao || '');
      cidade_display = parsed.cidade;
      uf_display = parsed.uf;
      raio_display = parsed.raio;
    }

    const loc = uf_display ? `${cidade_display}/${uf_display}` : cidade_display;
    if (raio_display != null) {
      resumo = `trocar geo de "${sel.nome}" → ${loc}, raio ${raio_display}km`;
    } else {
      resumo = `trocar geo de "${sel.nome}" → ${loc}`;
    }
  }"""

for node in wf['nodes']:
    if node['name'] != 'build_gestao_response':
        continue
    code = node['parameters']['jsCode']
    if OLD in code:
        node['parameters']['jsCode'] = code.replace(OLD, NEW)
        fixes_applied.append('build_gestao_response: parsing local de geo_livre (cidade/UF/raio)')
    else:
        fixes_failed.append('build_gestao_response: bloco antigo não encontrado')
    break

print("=== FIXES APLICADOS ===")
for f in fixes_applied: print(f"  ✅ {f}")
print("\n=== FIXES FALHADOS ===")
for f in fixes_failed: print(f"  ❌ {f}")

if not fixes_failed:
    clean = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'],
                    connections=wf['connections'], settings=clean)
    print("\n✅ Workflow atualizado.")
else:
    sys.exit(1)
