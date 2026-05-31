#!/usr/bin/env python3
"""
Fix: agente pedia CONFIRMAR antes de criativo quando estado vazava de
campanha anterior (etapa=ativa).

Bug observado (sequência real do Renan):
1. Cliente subiu campanha (etapa virou 'ativa', criativo URL persistiu)
2. Cliente mandou brief de NOVA campanha sem dizer "nova campanha"
3. Sistema carregou estado anterior → brief preenchido + criativo presente
4. Agente foi pra "tudo pronto, manda CONFIRMAR" — antes de pedir criativo novo

Fix em 2 camadas:

1. classify_intent v4: se etapa=ativa E intent seria OUTRO E msg > 5 chars,
   força intent=NOVA_CAMPANHA (cliente provavelmente está começando outra)

2. build_agente_body: quando intent=NOVA_CAMPANHA, ignora estado/histórico
   antigos e monta system prompt com estado COMPLETAMENTE LIMPO + nota
   no fim do estadoBlock instruindo o agente a:
   - Tratar como primeira interação
   - Capturar dados que o cliente JÁ mencionou na mensagem
   - NÃO mencionar campanha anterior

Validado: sequência simulada terminou com bot pedindo perfil + orçamento
+ criativo novo — sem mencionar a campanha anterior.
"""
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


CLASSIFY_INTENT_V4 = """const msg = String($('normalize_phone').first().json?.mensagem_texto || '').trim();
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

// AUTO-RESET: estado vazou de campanha anterior; trata como NOVA_CAMPANHA
if (intent === 'OUTRO' && etapaAtual === 'ativa' && msg.length > 5) {
  intent = 'NOVA_CAMPANHA';
}

return [{ json: { intent, mensagem_texto: msg } }];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    nb['classify_intent']['parameters']['jsCode'] = CLASSIFY_INTENT_V4
    print('  ↻ classify_intent v4: auto-NOVA_CAMPANHA em etapa=ativa')

    # build_agente_body atualizado tem lógica de reset quando intent=NOVA_CAMPANHA
    # (código embed grande — ver código aplicado no n8n via debug)

    sys_template = open('/Users/renanreal/quirk_auto_ads/prompts/agente_principal.md').read()
    sys_template_q = json.dumps(sys_template)
    NEW_BUILD = f"""const systemTemplate = {sys_template_q};
const intent = $('classify_intent').first().json.intent || 'OUTRO';
const novaMsg = String($('normalize_phone').first().json.mensagem_texto || '').trim();

let estado = $('load_estado').first().json.estado;
let historico = String($('load_estado').first().json.historico || '').trim();

if (intent === 'NOVA_CAMPANHA') {{
  estado = {{
    etapa_atual: 'coletando_info',
    criativo: {{recebido: false, url: null, mimetype: null, recebido_em: null}},
    brief: {{}},
    ultima_tentativa: null,
    gestao: null
  }};
  historico = '';
}}

let brief = estado.brief || {{}};
let criativo = estado.criativo || {{}};
let etapa_efetiva = estado.etapa_atual;
let ult = estado.ultima_tentativa;

try {{
  const mb = $('merge_brief').first().json;
  if (mb?.estado?.brief) brief = mb.estado.brief;
}} catch(e) {{}}

let metaResult = null;
try {{ metaResult = $('check_meta_results').first().json; }} catch(e) {{}}

if (metaResult) {{
  if (estado.criativo?.url) criativo = estado.criativo;
  else criativo = {{recebido: true, url: '(criativo enviado)'}};
  if (metaResult.ok) {{
    etapa_efetiva = 'ativa';
    ult = {{resultado: 'ok', motivo: '', campaign_id: metaResult.campaign_id, adset_id: metaResult.adset_id, creative_id: metaResult.creative_id, ad_id: metaResult.ad_id, tentativas_count: metaResult.tentativas_count}};
  }} else {{
    etapa_efetiva = metaResult.classe === 'infra' ? 'falhou_infra' : 'falhou_dado';
    ult = {{resultado: 'erro_' + (metaResult.classe || 'dado'), motivo: metaResult.motivo || '', tentativas_count: metaResult.tentativas_count}};
  }}
}}

const obrig = ['campanha', 'objetivo', 'faixa_valor', 'conjunto', 'anuncio', 'targeting_meta'];
const preenchidos = obrig.filter(k => !!brief[k]);
const faltantes = obrig.filter(k => !brief[k]);

let estadoBlock = `Etapa atual: ${{etapa_efetiva}}
Criativo recebido: ${{criativo?.recebido ? 'sim (' + (criativo.url || '') + ')' : 'não'}}
Brief preenchido: ${{preenchidos.join(', ') || '(nada)'}}
Brief faltante: ${{faltantes.join(', ') || '(nada)'}}
Última tentativa: ${{ult ? (ult.resultado + (ult.motivo ? ': ' + ult.motivo : '')) : 'nenhuma'}}
Tentativas count: ${{ult?.tentativas_count || 0}}
Intent detectado (msg atual): ${{intent}}`;

if (etapa_efetiva === 'ativa' && ult?.campaign_id) {{
  estadoBlock += `\\nCampanha ATIVA: campaign_id=${{ult.campaign_id}}`;
  if (ult.ad_id) estadoBlock += ` | ad_id=${{ult.ad_id}}`;
  estadoBlock += ` | Status: PAUSED no Meta (cliente ativa manualmente no Ads Manager)`;
}}

if (intent === 'NOVA_CAMPANHA') {{
  estadoBlock += `\\n\\n[NOVA CAMPANHA INICIADA] Cliente está começando uma campanha nova do zero. Trate como primeira interação — peça brief novo (tipo, valor, região, objetivo, perfil) começando pela parte que ele JÁ MENCIONOU na mensagem atual. NÃO mencione campanha anterior.`;
}}

const system = systemTemplate.replace('{{{{ESTADO_BLOCK}}}}', estadoBlock);

let userContent;
if (historico) userContent = `Histórico da conversa até agora:\\n${{historico}}\\n\\nNova mensagem do cliente: ${{novaMsg}}`;
else userContent = novaMsg;

return [{{json: {{model: "claude-sonnet-4-5", max_tokens: 1500, temperature: 0.3, system, messages: [{{role: "user", content: userContent}}]}}}}];
"""
    nb['build_agente_body']['parameters']['jsCode'] = NEW_BUILD
    print('  ↻ build_agente_body: NOVA_CAMPANHA reseta estado + histórico')

    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    n8n_api.update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'], settings=clean_settings)
    print('\n✓ Auto-NOVA_CAMPANHA implementado')


if __name__ == '__main__':
    main()
