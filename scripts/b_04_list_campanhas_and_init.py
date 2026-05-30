#!/usr/bin/env python3
"""list_campanhas + init_gestao + build_gestao_response + persist_estado_gestao."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


LIST_CAMPANHAS_QUERY = """SELECT
  id AS campanha_id_db,
  nome_campanha AS nome,
  ad_account_id,
  campaign_id AS campaign_id_meta,
  adset_id AS adset_id_meta,
  status,
  json_extrator,
  ultima_alteracao
FROM auto_ads.campanhas
WHERE telefone = '{{ $('normalize_phone').item.json.telefone_normalizado }}'
  AND status = ANY(CASE
    WHEN '{{ $('classify_intent').item.json.intent }}' = 'PAUSAR' THEN ARRAY['CREATED_PAUSED','ACTIVE']
    WHEN '{{ $('classify_intent').item.json.intent }}' = 'REATIVAR' THEN ARRAY['PAUSED','CREATED_PAUSED']
    WHEN '{{ $('classify_intent').item.json.intent }}' = 'ENCERRAR' THEN ARRAY['CREATED_PAUSED','ACTIVE','PAUSED']
    ELSE ARRAY['CREATED_PAUSED','ACTIVE','PAUSED']
  END)
ORDER BY criada_em DESC
LIMIT 10"""


INIT_GESTAO_CODE = """// Popula estado.gestao com lista + verbo + passo='selecao' + timestamp
const estado = $('load_estado').first().json.estado;
const verbo = $('classify_intent').first().json.intent;
const linhas = $('list_campanhas').all().map(r => r.json);

if (linhas.length === 0) {
  return [{ json: { acao: 'sem_campanhas', verbo, estado } }];
}

const lista_candidatas = linhas.map((row, i) => ({
  posicao: i + 1,
  campanha_id_db: row.campanha_id_db,
  campaign_id_meta: row.campaign_id_meta,
  adset_id_meta: row.adset_id_meta,
  nome: row.nome,
  status: row.status,
  verba_atual_centavos: row.json_extrator?.campanha?.verba_diaria ? row.json_extrator.campanha.verba_diaria * 100 : null,
  verba_atual_reais: row.json_extrator?.campanha?.verba_diaria || null,
  publico_atual: row.json_extrator?.publico_escolhido || null,
  geo_cidade_atual: row.json_extrator?.conjunto?.geo_cidade || null,
  geo_raio_atual: row.json_extrator?.conjunto?.geo_raio_km || null,
  json_extrator_completo: row.json_extrator
}));

estado.gestao = {
  verbo,
  passo: 'selecao',
  iniciado_em: new Date().toISOString(),
  lista_candidatas,
  selecionada: null,
  novo_valor: null
};
estado.etapa_atual = 'em_gestao';

return [{ json: { acao: 'inicia_selecao', estado, gestao: estado.gestao } }];
"""


BUILD_GESTAO_RESPONSE_CODE = """// Monta texto do passo atual
const upstream = $input.first().json;
const estado = upstream.estado || $('load_estado').first().json.estado;
const acao = upstream.acao || 'avanca';
const gestao = upstream.gestao || estado.gestao;

if (acao === 'sem_campanhas') {
  const v = upstream.verbo;
  const map = {
    PAUSAR: 'Você não tem campanhas ativas pra pausar.',
    REATIVAR: 'Você não tem campanhas pausadas pra reativar.',
    ENCERRAR: 'Você não tem campanhas pra encerrar.',
    ALTERAR_VERBA: 'Você não tem campanhas ativas pra alterar verba.',
    ALTERAR_PUBLICO: 'Você não tem campanhas ativas pra alterar público.',
    ALTERAR_GEO: 'Você não tem campanhas ativas pra alterar geo.'
  };
  return [{ json: { text: map[v] || 'Você não tem campanhas.', telefone: $('normalize_phone').first().json.telefone_normalizado } }];
}

if (acao === 'erro_input') {
  const motivo = upstream.motivo;
  let text;
  if (motivo === 'numero_invalido') text = `Número inválido. Manda entre 1 e ${gestao.lista_candidatas.length} ou CANCELAR.`;
  else if (motivo === 'verba_fora_faixa') text = 'Verba inválida. Manda número entre 10 e 100, ou CANCELAR.';
  else if (motivo === 'publico_input_invalido') text = 'Não entendi. Manda número da lista (1-20) OU descreve em texto, ou CANCELAR.';
  else if (motivo === 'geo_input_invalido') text = 'Não entendi. Manda "CIDADE raio_km" (ex: São Paulo 25) ou descreve, ou CANCELAR.';
  else if (motivo === 'confirma_invalido') text = 'Manda SIM ou NÃO. Ou CANCELAR.';
  else text = 'Input inválido. CANCELAR pra sair.';
  return [{ json: { text, telefone: $('normalize_phone').first().json.telefone_normalizado } }];
}

const passo = gestao.passo;
const verbo = gestao.verbo;

if (passo === 'selecao') {
  const linhas = gestao.lista_candidatas.map(c => {
    const status_label = c.status === 'ACTIVE' ? 'ativa' : c.status === 'PAUSED' ? 'pausada' : c.status === 'CREATED_PAUSED' ? 'paused (criação)' : c.status;
    const verba = c.verba_atual_reais ? `R$ ${c.verba_atual_reais}/dia` : '';
    return `${c.posicao}. ${c.nome} (${status_label}${verba ? ', ' + verba : ''})`;
  }).join('\\n');
  const verboLabel = { PAUSAR: 'pausar', REATIVAR: 'reativar', ENCERRAR: 'encerrar', ALTERAR_VERBA: 'alterar verba', ALTERAR_PUBLICO: 'alterar público', ALTERAR_GEO: 'alterar geo' }[verbo];
  return [{ json: { text: `Você tem ${gestao.lista_candidatas.length} pra ${verboLabel}. Qual?\\n\\n${linhas}\\n\\nResponde com o número ou CANCELAR.`, telefone: $('normalize_phone').first().json.telefone_normalizado } }];
}

if (passo === 'coleta_valor') {
  const sel = gestao.selecionada;
  if (verbo === 'ALTERAR_VERBA') {
    return [{ json: { text: `Verba atual de "${sel.nome}": R$ ${sel.verba_atual_reais}/dia. Manda só o número novo (entre 10 e 100), ou CANCELAR.`, telefone: $('normalize_phone').first().json.telefone_normalizado } }];
  }
  if (verbo === 'ALTERAR_PUBLICO') {
    const pubs = ['Pub Quirk 0','Pub Quirk 1','Pub Quirk 1.1','Pub Quirk 1.2','Pub Quirk 1.3','Pub Quirk 1.4','Pub Quirk 1.5','Pub Quirk 2','Pub Quirk 3','Pub Quirk 4','Pub Quirk 5','Pub Quirk 6','Pub Quirk 7','Pub Quirk Invest','Pub Quirk Invest + Intermediário','Pub Quirk Invest + Alto valor','Pub Quirk Profissões','Pub Quirk Profissões + Intermediário','Pub Quirk Profissões + Alto valor','Pub Corretores #1'];
    const lista = pubs.map((p, i) => `${i+1}. ${p}`).join('\\n');
    return [{ json: { text: `Público atual: ${sel.publico_atual}. Escolhe um número da lista OU descreve em texto (ex: "investidor casado alto valor"):\\n\\n${lista}\\n\\nOu CANCELAR.`, telefone: $('normalize_phone').first().json.telefone_normalizado } }];
  }
  if (verbo === 'ALTERAR_GEO') {
    return [{ json: { text: `Geo atual de "${sel.nome}": ${sel.geo_cidade_atual} raio ${sel.geo_raio_atual}km. Manda "CIDADE raio_km" (ex: "São Paulo 25") OU descreve, ou CANCELAR.`, telefone: $('normalize_phone').first().json.telefone_normalizado } }];
  }
}

if (passo === 'confirmacao') {
  const sel = gestao.selecionada;
  const nv = gestao.novo_valor;
  let resumo;
  if (verbo === 'PAUSAR') resumo = `pausar "${sel.nome}"`;
  else if (verbo === 'REATIVAR') resumo = `reativar "${sel.nome}"`;
  else if (verbo === 'ENCERRAR') resumo = `ENCERRAR "${sel.nome}" (irreversível — vai pro histórico arquivado)`;
  else if (verbo === 'ALTERAR_VERBA') resumo = `mudar verba de "${sel.nome}" de R$ ${sel.verba_atual_reais}/dia → R$ ${nv.valor}/dia`;
  else if (verbo === 'ALTERAR_PUBLICO') resumo = `trocar público de "${sel.nome}" (${sel.publico_atual} → novo)`;
  else if (verbo === 'ALTERAR_GEO') resumo = `trocar geo de "${sel.nome}" (${sel.geo_cidade_atual} ${sel.geo_raio_atual}km → novo)`;
  return [{ json: { text: `Confirma ${resumo}? Manda SIM ou NÃO.`, telefone: $('normalize_phone').first().json.telefone_normalizado } }];
}

return [{ json: { text: 'Passo desconhecido. CANCELAR pra sair.', telefone: $('normalize_phone').first().json.telefone_normalizado } }];
"""


PERSIST_ESTADO_GESTAO_QUERY = """UPDATE auto_ads.conversas
SET estado_json = jsonb_set(
  jsonb_set(estado_json, '{etapa_atual}', to_jsonb('{{ $('init_gestao').item.json.estado?.etapa_atual || $('process_gestao_step').item.json.estado?.etapa_atual || $('load_estado').item.json.estado.etapa_atual }}'::text)),
  '{gestao}',
  '{{ JSON.stringify($('init_gestao').item.json.gestao || $('process_gestao_step').item.json.gestao || $('load_estado').item.json.estado.gestao || null).replace(/'/g, "''") }}'::jsonb
)
WHERE telefone = '{{ $('normalize_phone').item.json.telefone_normalizado }}'"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    if 'list_campanhas' not in nb:
        wf['nodes'].append({
            'id': 'list_campanhas', 'name': 'list_campanhas',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [1750, 200],
            'parameters': {'operation': 'executeQuery', 'query': LIST_CAMPANHAS_QUERY, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + list_campanhas adicionado')

    if 'init_gestao' not in nb:
        wf['nodes'].append({
            'id': 'init_gestao', 'name': 'init_gestao',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [1950, 200],
            'parameters': {'language': 'javaScript', 'jsCode': INIT_GESTAO_CODE}
        })
        print('  + init_gestao adicionado')

    if 'build_gestao_response' not in nb:
        wf['nodes'].append({
            'id': 'build_gestao_response', 'name': 'build_gestao_response',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [2150, 200],
            'parameters': {'language': 'javaScript', 'jsCode': BUILD_GESTAO_RESPONSE_CODE}
        })
        print('  + build_gestao_response adicionado')

    if 'persist_estado_gestao' not in nb:
        wf['nodes'].append({
            'id': 'persist_estado_gestao', 'name': 'persist_estado_gestao',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [2350, 200],
            'parameters': {'operation': 'executeQuery', 'query': PERSIST_ESTADO_GESTAO_QUERY, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + persist_estado_gestao adicionado')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 4 aplicada')


if __name__ == '__main__':
    main()
