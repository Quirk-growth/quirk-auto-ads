#!/usr/bin/env python3
"""Refatora node validate pra ler de estado_json.brief (via merge_brief)."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


VALIDATE_V2_CODE = """const cliente = $('select_cliente').first().json;
const estado = $('merge_brief').first().json.estado;
const json = estado.brief;
const errors = [];

if (!json || Object.keys(json).length === 0) {
  errors.push('brief vazio (parse falhou ou extrator não rodou)');
  return [{ json: { ok: false, motivos: errors, estado } }];
}

const verba = parseInt(json.campanha?.verba_diaria);
if (isNaN(verba) || verba < 10) errors.push('verba_diaria < 10');
if (verba > 100) errors.push('verba_diaria > 100');
if (!json.campanha?.objetivo_meta) errors.push('objetivo_meta vazio');
if (!json.conjunto?.geo) errors.push('geo vazio');
if (!json.publico_escolhido) errors.push('publico_escolhido vazio');
if (!estado.criativo?.recebido || !estado.criativo?.url) errors.push('criativo_url vazio');
if (!cliente?.ad_account_id) errors.push('ad_account_id vazio');
if (!json.targeting_meta) errors.push('targeting_meta vazio');
if (!json.targeting_meta?.geo_locations) errors.push('geo_locations vazio');

const conversaLike = {
  telefone: $('normalize_phone').first().json.telefone_normalizado,
  criativo_url: estado.criativo?.url || ''
};

return [{
  json: {
    ok: errors.length === 0,
    motivos: errors,
    json_extrator: json,
    cliente,
    conversa: conversaLike,
    estado,
    verba_em_centavos: Math.max((verba || 30) * 100, 1000)
  }
}];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    if 'validate' not in nb:
        print('ERRO: node validate não existe')
        sys.exit(1)
    nb['validate']['parameters']['jsCode'] = VALIDATE_V2_CODE
    print('  ↻ validate refatorado pra v2')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 5 aplicada')


if __name__ == '__main__':
    main()
