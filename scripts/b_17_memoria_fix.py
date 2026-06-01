#!/usr/bin/env python3
"""
Fix de memória: cada msg estava sendo classificada como NOVA_CAMPANHA
(porque etapa=ativa nunca era resetada no DB), apagando o histórico.

Causa raiz:
1. classify_intent v4 disparava NOVA_CAMPANHA pra QUALQUER msg em etapa=ativa
2. reset_estado_nova fazia UPDATE pra coletando_info no DB
3. MAS update_estado_etapa lia estado de load_estado (cached ANTES do reset)
   e voltava pra ativa via persist_estado_etapa — o reset era anulado
4. Próxima msg: load_estado lia 'ativa' do DB → vira NOVA_CAMPANHA de novo
5. Loop infinito de reset histórico

Fix em 2 camadas:

1. classify_intent v5: NOVA_CAMPANHA só dispara se msg tem 2+ sinais de
   brief (palavras de imóvel + valor + região). Mensagens normais
   ('Boa tarde', 'Alcance', 'Já passei') ficam como OUTRO.

2. update_estado_etapa v3: quando intent=NOVA_CAMPANHA, força reset
   completo (etapa=coletando_info + brief={} + criativo limpo).
   persist_estado_etapa então grava o reset correto no DB.
"""
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


CLASSIFY_INTENT_V5 = """const msg = String($('normalize_phone').first().json?.mensagem_texto || '').trim();
const estado = $('load_estado').first().json?.estado || {};
const etapaAtual = estado.etapa_atual;

let intent = 'OUTRO';

if (/^(confirmar|confirmado|confirma)[!.?]*$/i.test(msg)) intent = 'CONFIRMAR';
else if (/^(sim,?\\s*subir|pode\\s*subir|sobe\\s*ai)[!.?]*$/i.test(msg)) intent = 'CONFIRMAR';
else if (/^subir\\s+denovo[!.?]*$/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/^subir\\s+de\\s+novo[!.?]*$/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/sub(ir|a)\\s+novamente/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/tent(e|a)r?\\s+(de\\s*novo|novamente)/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/^repetir$/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/^refazer$/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/^nova\\s+campanha$/i.test(msg)) intent = 'NOVA_CAMPANHA';
else if (/come[çc]ar\\s+(uma\\s+)?nova/i.test(msg)) intent = 'NOVA_CAMPANHA';
else if (/quero\\s+(criar\\s+)?(uma\\s+)?(outra|nova)\\s+campanha/i.test(msg)) intent = 'NOVA_CAMPANHA';
else if (/^(pausar|pausa)[!.?]*$/i.test(msg)) intent = 'PAUSAR';
else if (/pausar\\s+(minha\\s+)?campanha/i.test(msg)) intent = 'PAUSAR';
else if (/parar\\s+(minha\\s+)?campanha/i.test(msg)) intent = 'PAUSAR';
else if (/^(reativar|reativa|ativar)[!.?]*$/i.test(msg)) intent = 'REATIVAR';
else if (/voltar\\s+(minha\\s+)?campanha/i.test(msg)) intent = 'REATIVAR';
else if (/^(encerrar|arquivar)[!.?]*$/i.test(msg)) intent = 'ENCERRAR';
else if (/finalizar\\s+campanha/i.test(msg)) intent = 'ENCERRAR';
else if (/(alterar|mudar|trocar)\\s+verba/i.test(msg)) intent = 'ALTERAR_VERBA';
else if (/(alterar|mudar)\\s+p[uú]blico/i.test(msg)) intent = 'ALTERAR_PUBLICO';
else if (/(alterar|mudar)\\s+geo/i.test(msg)) intent = 'ALTERAR_GEO';
else if (/mudar\\s+(regi[aã]o|cidade)/i.test(msg)) intent = 'ALTERAR_GEO';
else if (/^(cancelar|cancela)[!.?]*$/i.test(msg)) intent = 'CANCELAR';
else if (/^deixa\\s+pra\\s+l[áa]/i.test(msg)) intent = 'CANCELAR';

// AUTO-RESET RESTRITO: só se etapa=ativa E msg parece BRIEF NOVO
if (intent === 'OUTRO' && etapaAtual === 'ativa') {
  const temImovel = /(apartamento|cobertura|casa|sobrado|terreno|lote|condom[íi]nio|ap\\s*\\d|kitnet|studio)/i.test(msg);
  const temValor = /(r\\$|reais|milh[ãa]o|mil\\b|k\\b|\\d{2,}\\s*mil)/i.test(msg);
  const temRegiao = /(bairro|regi[ãa]o|cidade|setor|jardim|vila|centro)/i.test(msg);
  const sinais = [temImovel, temValor, temRegiao].filter(Boolean).length;
  if (sinais >= 2) intent = 'NOVA_CAMPANHA';
}

return [{ json: { intent, mensagem_texto: msg } }];
"""


UPDATE_ESTADO_ETAPA_V3 = """const estado = $('load_estado').first().json.estado;
const intent = (() => { try { return $('classify_intent').first().json.intent; } catch(e){ return 'OUTRO'; } })();
const brief = estado.brief || {};
const tem_criativo = !!(estado.criativo?.recebido);

const obrig = ['campanha', 'objetivo', 'faixa_valor', 'conjunto', 'anuncio', 'targeting_meta'];
const briefCompleto = obrig.every(k => !!brief[k]);
const verbaOk = typeof brief.campanha?.verba_diaria === 'number' && brief.campanha.verba_diaria >= 10 && brief.campanha.verba_diaria <= 100;

let novaEtapa = estado.etapa_atual;

try {
  const cmr = $('check_meta_results').first().json;
  if (cmr?.ok) {
    estado.etapa_atual = 'ativa';
    return [{ json: { estado, brief_completo: true, tem_criativo: true } }];
  }
} catch(e) {}

if (intent === 'NOVA_CAMPANHA') {
  estado.etapa_atual = 'coletando_info';
  estado.brief = {};
  estado.criativo = {recebido: false, url: null, mimetype: null, recebido_em: null};
  estado.ultima_tentativa = null;
  return [{ json: { estado, brief_completo: false, tem_criativo: false } }];
}

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

    nb['classify_intent']['parameters']['jsCode'] = CLASSIFY_INTENT_V5
    print('  ↻ classify_intent v5: NOVA_CAMPANHA exige 2+ sinais de brief')

    nb['update_estado_etapa']['parameters']['jsCode'] = UPDATE_ESTADO_ETAPA_V3
    print('  ↻ update_estado_etapa v3: respeita intent=NOVA_CAMPANHA')

    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    n8n_api.update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'], settings=clean_settings)
    print('\n✓ Fix de memória aplicado')


if __name__ == '__main__':
    main()
