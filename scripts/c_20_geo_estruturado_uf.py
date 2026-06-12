"""
c_20_geo_estruturado_uf.py

Melhora o parsing de geo_estruturado em process_gestao_step.

Antes:
  - Regex: /^(.+?)\\s+(\\d+)$/   ex: "São Paulo 25"
  - Não captura UF nem raio decimal.
  - "Brasilândia SP 5" → cai em geo_livre (LLM extrai estado, OK, mas é mais lento e caro)

Depois (em ordem de tentativa):
  - "CIDADE UF RAIO"    → ex: "Brasilândia SP 5"     → {cidade, estado:'SP', raio_km:5}
  - "CIDADE/UF RAIO"    → ex: "Brasilândia/SP 5"     → {cidade, estado:'SP', raio_km:5}
  - "CIDADE, UF RAIO"   → ex: "Brasilândia, SP 5"    → {cidade, estado:'SP', raio_km:5}
  - "CIDADE RAIO"       → ex: "São Paulo 25"         → {cidade, raio_km:25}
  - Aceita raio decimal/vírgula: "5", "5.5", "5,5"
  - Caso contrário → geo_livre (fallback LLM)

Também atualiza a mensagem do build_gestao_response (passo coleta_valor)
pra mostrar o novo formato como sugestão.
"""

import sys
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow

WF_ID = 'fBUin1UPt5xJEp6g'
wf = get_workflow(WF_ID)

fixes_applied = []
fixes_failed = []

# ─────────────────────────────────────────────────────────────
# FIX A — process_gestao_step: regex + parser
# ─────────────────────────────────────────────────────────────

OLD_GESTAO_REGEX = """\
  } else if (verbo === 'ALTERAR_GEO') {
    const m = msg.match(/^(.+?)\\s+(\\d+)$/);
    if (m) novo_valor = { tipo: 'geo_estruturado', cidade: m[1].trim(), raio_km: parseInt(m[2]) };
    else if (msg.length >= 4) novo_valor = { tipo: 'geo_livre', descricao: msg };
    else erro = 'geo_input_invalido';
  }"""

NEW_GESTAO_REGEX = """\
  } else if (verbo === 'ALTERAR_GEO') {
    // Ordem das tentativas (do mais específico ao mais genérico)
    const m_uf = msg.match(/^(.+?)[\\s,\\/]+([A-Za-z]{2})\\s+(\\d+(?:[.,]\\d+)?)$/);
    const m_simples = msg.match(/^(.+?)\\s+(\\d+(?:[.,]\\d+)?)$/);
    if (m_uf) {
      novo_valor = {
        tipo: 'geo_estruturado',
        cidade: m_uf[1].trim(),
        estado: m_uf[2].toUpperCase(),
        raio_km: parseFloat(m_uf[3].replace(',', '.'))
      };
    } else if (m_simples) {
      novo_valor = {
        tipo: 'geo_estruturado',
        cidade: m_simples[1].trim(),
        raio_km: parseFloat(m_simples[2].replace(',', '.'))
      };
    } else if (msg.length >= 4) {
      novo_valor = { tipo: 'geo_livre', descricao: msg };
    } else {
      erro = 'geo_input_invalido';
    }
  }"""

# ─────────────────────────────────────────────────────────────
# FIX B — build_gestao_response: msg do passo coleta_valor
# ─────────────────────────────────────────────────────────────

OLD_PROMPT_TEXT = (
    "Geo atual de \"${sel.nome}\": ${sel.geo_cidade_atual} raio ${sel.geo_raio_atual}km. "
    "Manda \"CIDADE raio_km\" (ex: \"São Paulo 25\") OU descreve, ou CANCELAR."
)
NEW_PROMPT_TEXT = (
    "Geo atual de \"${sel.nome}\": ${sel.geo_cidade_atual} raio ${sel.geo_raio_atual}km. "
    "Manda \"CIDADE UF raio_km\" (ex: \"Brasilândia SP 5\" ou \"São Paulo 25\") "
    "OU descreve em texto livre, ou CANCELAR."
)

for node in wf['nodes']:
    name = node['name']
    code = node['parameters'].get('jsCode')
    if not code:
        continue

    if name == 'process_gestao_step':
        if OLD_GESTAO_REGEX in code:
            node['parameters']['jsCode'] = code.replace(OLD_GESTAO_REGEX, NEW_GESTAO_REGEX)
            fixes_applied.append('process_gestao_step: regex aceita CIDADE UF RAIO e raio decimal')
        else:
            fixes_failed.append('process_gestao_step: regex antiga não encontrada')

    elif name == 'build_gestao_response':
        if OLD_PROMPT_TEXT in code:
            node['parameters']['jsCode'] = code.replace(OLD_PROMPT_TEXT, NEW_PROMPT_TEXT)
            fixes_applied.append('build_gestao_response: msg coleta_valor sugere novo formato')
        else:
            fixes_failed.append('build_gestao_response: msg coleta_valor não encontrada')


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
