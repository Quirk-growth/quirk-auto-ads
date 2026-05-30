#!/usr/bin/env python3
"""classify_intent v3 — adiciona 7 verbos de gestão preservando os 4 do A."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


CLASSIFY_INTENT_V3 = """// Detecta intenção do cliente por regex no texto da msg
const msg = String($('normalize_phone').first().json?.mensagem_texto || '').trim();

let intent = 'OUTRO';

// Verbos do sub-projeto A (preservados)
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

// Verbos do sub-projeto B (novos)
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

return [{ json: { intent, mensagem_texto: msg } }];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    nb['classify_intent']['parameters']['jsCode'] = CLASSIFY_INTENT_V3
    print('  ↻ classify_intent v3: 7 verbos novos (PAUSAR, REATIVAR, ENCERRAR, ALTERAR_*, CANCELAR)')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 2 aplicada')


if __name__ == '__main__':
    main()
