#!/usr/bin/env python3
"""Adiciona em_gestao_valido (IF) + process_gestao_step (Code)."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


PROCESS_GESTAO_STEP_CODE = """// Roteador por estado.gestao.passo + valida input
const estado = $('load_estado').first().json.estado;
const gestao = estado.gestao;
const msg = String($('normalize_phone').first().json?.mensagem_texto || '').trim();

if (!gestao || !gestao.passo) {
  return [{ json: { acao: 'reset', motivo: 'gestao_vazio' } }];
}

if (/^(cancelar|cancela|deixa\\s+pra\\s+l[áa])[!.?]*$/i.test(msg)) {
  return [{ json: { acao: 'reset', motivo: 'cancelado_pelo_cliente' } }];
}

const passo = gestao.passo;
const verbo = gestao.verbo;

if (passo === 'selecao') {
  const num = parseInt(msg);
  if (isNaN(num) || num < 1 || num > (gestao.lista_candidatas || []).length) {
    return [{ json: { acao: 'erro_input', motivo: 'numero_invalido', proximo_passo: 'selecao', gestao, estado } }];
  }
  const selecionada = gestao.lista_candidatas[num - 1];
  gestao.selecionada = selecionada;
  if (['PAUSAR', 'REATIVAR', 'ENCERRAR'].includes(verbo)) {
    gestao.passo = 'confirmacao';
  } else {
    gestao.passo = 'coleta_valor';
  }
  return [{ json: { acao: 'avanca', estado, gestao } }];
}

if (passo === 'coleta_valor') {
  let novo_valor = null;
  let erro = null;

  if (verbo === 'ALTERAR_VERBA') {
    const n = parseInt(msg);
    if (isNaN(n) || n < 10 || n > 100) {
      erro = 'verba_fora_faixa';
    } else {
      novo_valor = { tipo: 'verba_diaria', valor: n };
    }
  } else if (verbo === 'ALTERAR_PUBLICO') {
    const num = parseInt(msg);
    if (!isNaN(num) && num >= 1 && num <= 20) {
      novo_valor = { tipo: 'publico_estruturado', numero: num };
    } else if (msg.length >= 4) {
      novo_valor = { tipo: 'publico_livre', descricao: msg };
    } else {
      erro = 'publico_input_invalido';
    }
  } else if (verbo === 'ALTERAR_GEO') {
    const m = msg.match(/^(.+?)\\s+(\\d+)$/);
    if (m) {
      novo_valor = { tipo: 'geo_estruturado', cidade: m[1].trim(), raio_km: parseInt(m[2]) };
    } else if (msg.length >= 4) {
      novo_valor = { tipo: 'geo_livre', descricao: msg };
    } else {
      erro = 'geo_input_invalido';
    }
  }

  if (erro) {
    return [{ json: { acao: 'erro_input', motivo: erro, proximo_passo: 'coleta_valor', gestao, estado } }];
  }
  gestao.novo_valor = novo_valor;
  gestao.passo = 'confirmacao';
  return [{ json: { acao: 'avanca', estado, gestao } }];
}

if (passo === 'confirmacao') {
  if (/^(sim|s|confirma|confirmar|confirmado)[!.?]*$/i.test(msg)) {
    return [{ json: { acao: 'executa', estado, gestao } }];
  }
  if (/^(n[aã]o|n)[!.?]*$/i.test(msg)) {
    return [{ json: { acao: 'reset', motivo: 'cancelado_no_confirma' } }];
  }
  return [{ json: { acao: 'erro_input', motivo: 'confirma_invalido', proximo_passo: 'confirmacao', gestao, estado } }];
}

return [{ json: { acao: 'reset', motivo: 'passo_desconhecido' } }];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    if 'em_gestao_valido' not in nb:
        wf['nodes'].append({
            'id': 'em_gestao_valido', 'name': 'em_gestao_valido',
            'type': 'n8n-nodes-base.if', 'typeVersion': 2,
            'position': [1350, 100],
            'parameters': {
                'conditions': {
                    'options': {'caseSensitive': True, 'typeValidation': 'loose'},
                    'combinator': 'and',
                    'conditions': [
                        {
                            'leftValue': "={{ $('load_estado').item.json.estado.gestao !== null && $('load_estado').item.json.estado.gestao !== undefined ? 'true' : 'false' }}",
                            'rightValue': 'true',
                            'operator': {'type': 'string', 'operation': 'equals'}
                        },
                        {
                            'leftValue': "={{ Date.now() - new Date($('load_estado').item.json.estado.gestao?.iniciado_em || 0).getTime() }}",
                            'rightValue': 600000,
                            'operator': {'type': 'number', 'operation': 'smaller'}
                        }
                    ]
                }
            }
        })
        print('  + em_gestao_valido adicionado')

    if 'process_gestao_step' not in nb:
        wf['nodes'].append({
            'id': 'process_gestao_step', 'name': 'process_gestao_step',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [1550, 50],
            'parameters': {'language': 'javaScript', 'jsCode': PROCESS_GESTAO_STEP_CODE}
        })
        print('  + process_gestao_step adicionado')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 3 aplicada')


if __name__ == '__main__':
    main()
