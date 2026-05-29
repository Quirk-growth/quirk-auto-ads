#!/usr/bin/env python3
"""
1. classify_intent: RETRY → SUBIR_DENOVO (regex + intent name)
2. agente_principal v2 prompt: regra usa "SUBIR DENOVO"
3. build_media_response: msg mostra "SUBIR DENOVO" em vez de "RETRY"
4. merge_brief: força advantage_audience=0 e remove qualquer Advantage+ residual
"""
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


CLASSIFY_INTENT_V2 = """// Detecta intenção do cliente por regex no texto da msg
const msg = String($('normalize_phone').first().json?.mensagem_texto || '').trim();

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

return [{ json: { intent, mensagem_texto: msg } }];
"""


# build_media_response v2 — "SUBIR DENOVO" no lugar de "RETRY"
BUILD_MEDIA_RESPONSE_V2 = """// Msg condicional baseada em estado anterior + brief completo
const d = $('decide_acao_media').first().json;
const estadoAntes = d.estadoAntes || {};
const brief = estadoAntes.brief || {};
const obrig = ['campanha', 'objetivo', 'faixa_valor', 'conjunto', 'anuncio', 'targeting_meta'];
const briefCompleto = obrig.every(k => !!brief[k]);

let text;
if (d.triggerRetry) {
  text = 'Recebi o novo criativo ✓ — manda SUBIR DENOVO pra tentar com ele.';
} else if (estadoAntes.etapa_atual === 'ativa') {
  text = 'Recebi o criativo ✓ — mas você já tem campanha ativa. Quer fazer NOVA CAMPANHA?';
} else if (estadoAntes.etapa_atual === 'falhou_dado') {
  const motivo = estadoAntes.ultima_tentativa?.motivo || 'algum problema';
  text = 'Recebi seu criativo ✓ — mas a última tentativa falhou por: ' + motivo + '. Corrige isso e manda SUBIR DENOVO.';
} else if (briefCompleto) {
  text = 'Recebi seu criativo ✓ — tudo pronto. Manda CONFIRMAR quando quiser subir.';
} else {
  const faltantes = obrig.filter(k => !brief[k]).join(', ');
  text = 'Recebi seu criativo ✓ — ainda preciso de: ' + faltantes + '. Me manda esses dados pra fechar.';
}

return [{
  json: {
    text,
    telefone: d.telefone
  }
}];
"""


# merge_brief v2 — força advantage_audience=0 e remove Advantage+ residual
MERGE_BRIEF_V2 = """// Mescla json_extrator no estado_json.brief + normaliza targeting
const estado = $('load_estado').first().json.estado;
const parsed = $('parse_extrator').first().json.json_extrator;

if (!parsed) {
  return [{ json: { estado, parse_ok: false } }];
}

// Clamp age
if (parsed.targeting_meta && typeof parsed.targeting_meta.age_min === 'number' && parsed.targeting_meta.age_min < 18) parsed.targeting_meta.age_min = 18;
if (parsed.targeting_meta && typeof parsed.targeting_meta.age_max === 'number' && parsed.targeting_meta.age_max > 65) parsed.targeting_meta.age_max = 65;

// Clamp city radius
const cities = parsed.targeting_meta?.geo_locations?.cities;
if (Array.isArray(cities)) {
  for (const c of cities) {
    if (typeof c.radius === 'number' && c.radius < 17) c.radius = 17;
    if (typeof c.radius === 'number' && c.radius > 80) c.radius = 80;
    if (!c.distance_unit) c.distance_unit = 'kilometer';
  }
}

// REGRA DE NEGÓCIO: Quirk não usa Advantage+ audiences
if (parsed.targeting_meta) {
  parsed.targeting_meta.targeting_automation = { advantage_audience: 0 };
  // Remove qualquer hint de Advantage+ Custom Audience
  if (parsed.targeting_meta.custom_audiences) delete parsed.targeting_meta.custom_audiences;
}

estado.brief = { ...estado.brief, ...parsed };

return [{ json: { estado, parse_ok: true } }];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    nb['classify_intent']['parameters']['jsCode'] = CLASSIFY_INTENT_V2
    print('  ↻ classify_intent: RETRY → SUBIR_DENOVO')

    nb['build_media_response']['parameters']['jsCode'] = BUILD_MEDIA_RESPONSE_V2
    print('  ↻ build_media_response: mensagens com SUBIR DENOVO')

    nb['merge_brief']['parameters']['jsCode'] = MERGE_BRIEF_V2
    print('  ↻ merge_brief: força advantage_audience=0')

    # Atualizar switch_intent — branch "RETRY" agora se chama "SUBIR_DENOVO"
    sw = nb.get('switch_intent')
    if sw:
        rules = sw['parameters']['rules']['values']
        for r in rules:
            for c in r['conditions']['conditions']:
                if c['rightValue'] == 'RETRY':
                    c['rightValue'] = 'SUBIR_DENOVO'
                    r['outputKey'] = 'SUBIR_DENOVO'
                    print('  ↻ switch_intent: branch RETRY → SUBIR_DENOVO')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Rename + no-advantage aplicado')


if __name__ == '__main__':
    main()
