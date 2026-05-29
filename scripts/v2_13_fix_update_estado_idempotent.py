#!/usr/bin/env python3
"""Fix: update_estado_etapa precisa ser idempotente — não mexer em etapas terminais.

Bug: no fluxo CONFIRMAR, depois de persist_estado_apos_meta (que seta falhou_dado/ativa),
update_estado_etapa rodava e via etapa=coletando_info (do load_estado, snapshot antigo),
recalculava como coletando_info e sobrescrevia o que persist_estado_apos_meta tinha gravado.

Fix:
1. update_estado_etapa lê SE persist_estado_apos_meta rodou — se sim, usa o estado pós-meta
2. Não mexe em etapas terminais (ativa, falhou_dado, falhou_infra, subindo)
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


NEW_CODE = """// Determina nova etapa preservando etapas terminais
let estado = $('load_estado').first().json.estado;

// Se persist_estado_apos_meta rodou, lê o estado de check_meta_results (já calculado)
let etapaAposMeta = null;
try {
  const cmr = $('check_meta_results').first().json;
  if (cmr) {
    etapaAposMeta = cmr.ok ? 'ativa' : (cmr.classe === 'infra' ? 'falhou_infra' : 'falhou_dado');
    // Reconstrói estado com etapa terminal + ultima_tentativa
    estado = { ...estado, etapa_atual: etapaAposMeta, ultima_tentativa: {
      timestamp: new Date().toISOString(),
      resultado: cmr.ok ? 'ok' : ('erro_' + cmr.classe),
      motivo: cmr.motivo,
      campaign_id: cmr.campaign_id,
      adset_id: cmr.adset_id,
      creative_id: cmr.creative_id,
      ad_id: cmr.ad_id,
      tentativas_count: cmr.tentativas_count
    }};
  }
} catch(e) { /* check_meta_results não rodou — fluxo OUTRO */ }

// Se validate barrou (erro_validacao no fluxo CONFIRMAR), persiste motivo como ultima_tentativa
if (!etapaAposMeta) {
  try {
    const v = $('validate').first().json;
    if (v && v.ok === false) {
      estado.ultima_tentativa = {
        timestamp: new Date().toISOString(),
        resultado: 'erro_validacao',
        motivo: (v.motivos || []).join('; '),
        tentativas_count: (estado.ultima_tentativa?.tentativas_count || 0)
      };
    }
  } catch(e) { /* validate não rodou */ }
}

// Etapas terminais: não recalcular
const terminais = ['ativa', 'falhou_dado', 'falhou_infra', 'subindo'];
if (terminais.includes(estado.etapa_atual)) {
  return [{ json: { estado, etapa_terminal: true } }];
}

// Recalcula etapa baseado em brief + criativo
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


PERSIST_FULL_QUERY = """UPDATE auto_ads.conversas
SET estado_json = jsonb_set(
  jsonb_set(
    estado_json,
    '{etapa_atual}',
    to_jsonb('{{ $('update_estado_etapa').item.json.estado.etapa_atual }}'::text)
  ),
  '{ultima_tentativa}',
  COALESCE('{{ JSON.stringify($('update_estado_etapa').item.json.estado.ultima_tentativa || null).replace(/'/g, "''") }}'::jsonb, 'null'::jsonb)
)
WHERE telefone = '{{ $('normalize_phone').item.json.telefone_normalizado }}'"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    nb['update_estado_etapa']['parameters']['jsCode'] = NEW_CODE
    print('  ↻ update_estado_etapa preserva etapas terminais + sintetiza ultima_tentativa')

    nb['persist_estado_etapa']['parameters']['query'] = PERSIST_FULL_QUERY
    print('  ↻ persist_estado_etapa persiste etapa + ultima_tentativa')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Fix aplicado')


if __name__ == '__main__':
    main()
