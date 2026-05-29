#!/usr/bin/env python3
"""Adiciona Code nodes merge_brief e update_estado_etapa."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


MERGE_BRIEF_CODE = """// Mescla json_extrator no estado_json.brief
const estado = $('load_estado').first().json.estado;
const parsed = $('parse_extrator').first().json.json_extrator;

if (!parsed) {
  return [{ json: { estado, parse_ok: false } }];
}

// Normaliza targeting_meta (clamp do raio, age min/max)
if (parsed.targeting_meta && typeof parsed.targeting_meta.age_min === 'number' && parsed.targeting_meta.age_min < 18) parsed.targeting_meta.age_min = 18;
if (parsed.targeting_meta && typeof parsed.targeting_meta.age_max === 'number' && parsed.targeting_meta.age_max > 65) parsed.targeting_meta.age_max = 65;
const cities = parsed.targeting_meta?.geo_locations?.cities;
if (Array.isArray(cities)) {
  for (const c of cities) {
    if (typeof c.radius === 'number' && c.radius < 17) c.radius = 17;
    if (typeof c.radius === 'number' && c.radius > 80) c.radius = 80;
    if (!c.distance_unit) c.distance_unit = 'kilometer';
  }
}

estado.brief = { ...estado.brief, ...parsed };

return [{ json: { estado, parse_ok: true } }];
"""

UPDATE_ESTADO_ETAPA_CODE = """// Determina nova etapa baseado em brief + criativo
const estado = $('load_estado').first().json.estado;
const brief = estado.brief || {};
const tem_criativo = !!(estado.criativo?.recebido);

const obrig = ['campanha', 'objetivo', 'faixa_valor', 'conjunto', 'anuncio', 'targeting_meta'];
const briefCompleto = obrig.every(k => !!brief[k]);
const verbaOk = typeof brief.campanha?.verba_diaria === 'number' && brief.campanha.verba_diaria >= 10 && brief.campanha.verba_diaria <= 100;

let novaEtapa = estado.etapa_atual;

if (estado.etapa_atual === 'coletando_info') {
  if (briefCompleto && verbaOk && !tem_criativo) novaEtapa = 'aguardando_criativo';
  else if (briefCompleto && verbaOk && tem_criativo) novaEtapa = 'pronta_pra_subir';
} else if (estado.etapa_atual === 'aguardando_criativo') {
  if (tem_criativo) novaEtapa = 'pronta_pra_subir';
  else if (!briefCompleto) novaEtapa = 'coletando_info';
}

estado.etapa_atual = novaEtapa;

return [{ json: { estado, brief_completo: briefCompleto, tem_criativo } }];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    if 'merge_brief' in nb:
        nb['merge_brief']['parameters']['jsCode'] = MERGE_BRIEF_CODE
        print('  ↻ merge_brief atualizado')
    else:
        wf['nodes'].append({
            'id': 'merge_brief', 'name': 'merge_brief',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [3100, 50],
            'parameters': {'language': 'javaScript', 'jsCode': MERGE_BRIEF_CODE}
        })
        print('  + merge_brief adicionado')

    if 'update_estado_etapa' in nb:
        nb['update_estado_etapa']['parameters']['jsCode'] = UPDATE_ESTADO_ETAPA_CODE
        print('  ↻ update_estado_etapa atualizado')
    else:
        wf['nodes'].append({
            'id': 'update_estado_etapa', 'name': 'update_estado_etapa',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [1600, 250],
            'parameters': {'language': 'javaScript', 'jsCode': UPDATE_ESTADO_ETAPA_CODE}
        })
        print('  + update_estado_etapa adicionado')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 4 aplicada')


if __name__ == '__main__':
    main()
