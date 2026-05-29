#!/usr/bin/env python3
"""check_meta_results v2 (classifica infra/dado) + wait_30s + if_pode_retry_infra."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


CHECK_META_V2_CODE = """function getRespOrNull(node) {
  try {
    const r = $(node).first().json;
    if (r?.error) return { error: r.error };
    return { id: r?.id || null };
  } catch (e) { return { error: { message: e.message } }; }
}

function classify(node) {
  const r = getRespOrNull(node);
  if (r.id) return { ok: true, id: r.id, classe: null, motivo: null };
  const err = r.error || {};
  const msg = err.message || '';
  if (/Request failed with status code 5\\d\\d/i.test(msg) || /timeout/i.test(msg) || /is_transient.{1,5}true/i.test(msg) || /ECONN/i.test(msg)) {
    return { ok: false, classe: 'infra', motivo: msg.slice(0, 200), id: null };
  }
  const matchUser = msg.match(/error_user_msg\\\\?\\":\\\\?\\"([^\\"]+)/);
  let motivo = matchUser ? matchUser[1].replace(/\\\\u([0-9a-f]{4})/gi, (_, h) => String.fromCharCode(parseInt(h, 16))) : msg.slice(0, 200);
  return { ok: false, classe: 'dado', motivo, id: null };
}

const d1 = classify('meta_d1_campaign');
const d2 = classify('meta_d2_adset');
const d3 = classify('meta_d3_creative');
const d4 = classify('meta_d4_ad');

const allOk = d1.ok && d2.ok && d3.ok && d4.ok;
let failed_step = null;
let classe = null;
let motivo = null;
if (!d1.ok) { failed_step = 'd1'; classe = d1.classe; motivo = d1.motivo; }
else if (!d2.ok) { failed_step = 'd2'; classe = d2.classe; motivo = d2.motivo; }
else if (!d3.ok) { failed_step = 'd3'; classe = d3.classe; motivo = d3.motivo; }
else if (!d4.ok) { failed_step = 'd4'; classe = d4.classe; motivo = d4.motivo; }

const estado = $('validate').first().json.estado;
const tentativas_count = (estado?.ultima_tentativa?.tentativas_count || 0) + 1;

return [{
  json: {
    ok: allOk,
    failed_step,
    classe,
    motivo,
    campaign_id: d1.id,
    adset_id: d2.id,
    creative_id: d3.id,
    ad_id: d4.id,
    tentativas_count,
    telefone: $('normalize_phone').first().json.telefone_normalizado,
    json_extrator: estado.brief,
    estado
  }
}];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    if 'check_meta_results' not in nb:
        print('ERRO: check_meta_results não existe — rode fixes anteriores antes')
        sys.exit(1)
    nb['check_meta_results']['parameters']['jsCode'] = CHECK_META_V2_CODE
    print('  ↻ check_meta_results v2 (classifica infra/dado + failed_step)')

    if 'wait_30s' not in nb:
        wf['nodes'].append({
            'id': 'wait_30s', 'name': 'wait_30s',
            'type': 'n8n-nodes-base.wait', 'typeVersion': 1,
            'position': [4980, 200],
            'parameters': {'amount': 30, 'unit': 'seconds'},
        })
        print('  + wait_30s adicionado')

    if 'if_pode_retry_infra' not in nb:
        wf['nodes'].append({
            'id': 'if_pode_retry_infra', 'name': 'if_pode_retry_infra',
            'type': 'n8n-nodes-base.if', 'typeVersion': 2,
            'position': [4880, 100],
            'parameters': {
                'conditions': {
                    'options': {'caseSensitive': True, 'typeValidation': 'loose'},
                    'combinator': 'and',
                    'conditions': [
                        {
                            'leftValue': "={{ $('check_meta_results').item.json.classe }}",
                            'rightValue': 'infra',
                            'operator': {'type': 'string', 'operation': 'equals'}
                        },
                        {
                            'leftValue': "={{ $('check_meta_results').item.json.tentativas_count }}",
                            'rightValue': 2,
                            'operator': {'type': 'number', 'operation': 'smallerEqual'}
                        }
                    ]
                }
            }
        })
        print('  + if_pode_retry_infra adicionado')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 6 aplicada')


if __name__ == '__main__':
    main()
