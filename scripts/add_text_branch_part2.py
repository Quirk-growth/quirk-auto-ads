#!/usr/bin/env python3
"""
Branch TEXTO parte 2 — após agente_principal:
  classifier (Anthropic) →
  build_historico (Code) →
  upsert_conversa (Postgres) →
  send_resposta (HTTP UAZAPI) →
  if_confirmado (IF) →
    ├── false → END
    └── true → extrator (Anthropic) → parse_extrator (Code) → validate (Code)
                                                                ├── ok=false → audit + alerta + END
                                                                └── ok=true [→ continua na parte 3 com D.1-D.4]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api
import config

WF_ID = config.get_workflow_id()
wf = n8n_api.get_workflow(WF_ID)

new_nodes = [
    # ──────────────────────────────────────────────
    # 7. Classifier (decide CONFIRMADO/PENDENTE)
    # ──────────────────────────────────────────────
    {
        "id": "classifier",
        "name": "classifier",
        "type": "n8n-nodes-base.anthropic",
        "typeVersion": 1,
        "position": [1780, 100],
        "parameters": {
            "resource": "message",
            "operation": "create",
            "model": "claude-sonnet-4-5",
            "messages": {
                "values": [
                    {
                        "role": "user",
                        "content": "Mensagem do cliente: {{ $('normalize_phone').item.json.mensagem_texto }}\n\nResposta do agente: {{ $('agente_principal').item.json.message?.content?.[0]?.text || $('agente_principal').item.json.content?.[0]?.text || '' }}"
                    }
                ]
            },
            "options": {
                "system": config.load_prompt("classifier"),
                "maxTokens": 20,
                "temperature": 0
            }
        },
        "credentials": {"anthropicApi": config.ANTHROPIC_CRED},
    },
    # ──────────────────────────────────────────────
    # 8. Build histórico (concatena nova troca + trunca em 20 turnos)
    # ──────────────────────────────────────────────
    {
        "id": "build_historico",
        "name": "build_historico",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2000, 100],
        "parameters": {
            "language": "javaScript",
            "jsCode": """const histAtual = $('select_conversa').first().json.historico || '';
const userMsg = $('normalize_phone').first().json.mensagem_texto || '';
const agentResp = $('agente_principal').first().json.message?.content?.[0]?.text
                 || $('agente_principal').first().json.content?.[0]?.text
                 || '';
const classResp = ($('classifier').first().json.message?.content?.[0]?.text
                 || $('classifier').first().json.content?.[0]?.text
                 || 'PENDENTE').trim();

const novoTurn = `|||TURN|||Cliente: ${userMsg}\\nClaude: ${agentResp}`;
const completo = histAtual + novoTurn;
// Trunca em últimos 20 turnos
const turns = completo.split('|||TURN|||');
const ultimos20 = turns.slice(-20).join('|||TURN|||');

return [{
  json: {
    historico_atualizado: ultimos20,
    classifier_result: classResp,
    agente_resposta: agentResp,
    telefone: $('normalize_phone').first().json.telefone_normalizado
  }
}];"""
        },
    },
    # ──────────────────────────────────────────────
    # 9. UPSERT conversa
    # ──────────────────────────────────────────────
    {
        "id": "upsert_conversa",
        "name": "upsert_conversa",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.6,
        "position": [2220, 100],
        "parameters": {
            "operation": "executeQuery",
            "query": """INSERT INTO auto_ads.conversas (telefone, historico)
VALUES ($1, $2)
ON CONFLICT (telefone) DO UPDATE
  SET historico = EXCLUDED.historico,
      ultima_atualizacao = NOW()""",
            "options": {
                "queryReplacement": "={{ $json.telefone }},{{ $json.historico_atualizado }}"
            }
        },
        "credentials": {"postgres": config.POSTGRES_CRED},
    },
    # ──────────────────────────────────────────────
    # 10. Send resposta ao cliente
    # ──────────────────────────────────────────────
    {
        "id": "send_resposta",
        "name": "send_resposta",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2440, 100],
        "parameters": {
            "method": "POST",
            "url": f"{config.UAZAPI_BASE}/send/text",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "token", "value": "={{ $env.UAZAPI_TOKEN }}"},
                    {"name": "Content-Type", "value": "application/json"}
                ]
            },
            "sendBody": True,
            "contentType": "json",
            "bodyParameters": {
                "parameters": [
                    {"name": "number", "value": "={{ $('build_historico').item.json.telefone }}"},
                    {"name": "text", "value": "={{ $('build_historico').item.json.agente_resposta }}"}
                ]
            },
            "options": {}
        },
    },
    # ──────────────────────────────────────────────
    # 11. IF classifier === CONFIRMADO
    # ──────────────────────────────────────────────
    {
        "id": "if_confirmado",
        "name": "if_confirmado",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [2660, 100],
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": False, "leftValue": "", "typeValidation": "loose"},
                "conditions": [{
                    "id": "1",
                    "leftValue": "={{ $('build_historico').item.json.classifier_result.toUpperCase() }}",
                    "rightValue": "CONFIRMADO",
                    "operator": {"type": "string", "operation": "equals"}
                }],
                "combinator": "and"
            },
            "options": {}
        },
    },
    # ──────────────────────────────────────────────
    # 12. Extrator (Anthropic) - true branch do IF
    # ──────────────────────────────────────────────
    {
        "id": "extrator",
        "name": "extrator",
        "type": "n8n-nodes-base.anthropic",
        "typeVersion": 1,
        "position": [2880, 50],
        "parameters": {
            "resource": "message",
            "operation": "create",
            "model": "claude-sonnet-4-5",
            "messages": {
                "values": [
                    {
                        "role": "user",
                        "content": "={{ $('build_historico').item.json.historico_atualizado }}"
                    }
                ]
            },
            "options": {
                "system": config.load_prompt("extrator"),
                "maxTokens": 3000,
                "temperature": 0
            }
        },
        "credentials": {"anthropicApi": config.ANTHROPIC_CRED},
    },
    # ──────────────────────────────────────────────
    # 13. Parse JSON do extrator
    # ──────────────────────────────────────────────
    {
        "id": "parse_extrator",
        "name": "parse_extrator",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [3100, 50],
        "parameters": {
            "language": "javaScript",
            "jsCode": """// Extrai JSON da resposta do extrator (pode vir embrulhado em markdown ```json...```)
const raw = $('extrator').first().json.message?.content?.[0]?.text
         || $('extrator').first().json.content?.[0]?.text
         || '';

let cleaned = raw.trim();
// Remove blocos de código markdown
cleaned = cleaned.replace(/^```(?:json)?\\s*/i, '').replace(/```\\s*$/, '').trim();
// Procura primeiro { e último } pra ser tolerante
const firstBrace = cleaned.indexOf('{');
const lastBrace = cleaned.lastIndexOf('}');
if (firstBrace >= 0 && lastBrace > firstBrace) {
  cleaned = cleaned.substring(firstBrace, lastBrace + 1);
}

let parsed;
try {
  parsed = JSON.parse(cleaned);
} catch (e) {
  return [{json: {parse_error: e.message, raw: raw.substring(0, 500), json_extrator: null}}];
}

return [{json: {json_extrator: parsed, parse_ok: true}}];"""
        },
    },
    # ──────────────────────────────────────────────
    # 14. Validate (9 condições da Fase C)
    # ──────────────────────────────────────────────
    {
        "id": "validate",
        "name": "validate",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [3320, 50],
        "parameters": {
            "language": "javaScript",
            "jsCode": """const cliente = $('select_cliente').first().json;
const conversa = $('select_conversa').first().json;
const json = $('parse_extrator').first().json.json_extrator;
const errors = [];

if (!json) {
  errors.push('json_extrator é null (parse falhou)');
  return [{json: {ok: false, motivos: errors}}];
}

const verba = parseInt(json.campanha?.verba_diaria);
if (isNaN(verba) || verba < 10) errors.push('verba_diaria < 10');
if (verba > 100) errors.push('verba_diaria > 100');
if (!json.campanha?.objetivo_meta) errors.push('objetivo_meta vazio');
if (!json.conjunto?.geo) errors.push('geo vazio');
if (!json.publico_escolhido) errors.push('publico_escolhido vazio');
if (!conversa?.criativo_url) errors.push('criativo_url vazio');
if (!cliente?.ad_account_id) errors.push('ad_account_id vazio');
if (!json.targeting_meta) errors.push('targeting_meta vazio');
if (!json.targeting_meta?.geo_locations) errors.push('geo_locations vazio');

return [{
  json: {
    ok: errors.length === 0,
    motivos: errors,
    json_extrator: json,
    cliente,
    conversa,
    verba_em_centavos: Math.max(verba * 100, 1000)
  }
}];"""
        },
    },
    # ──────────────────────────────────────────────
    # 15. IF validate.ok (gate antes de chamar Meta)
    # ──────────────────────────────────────────────
    {
        "id": "if_valid",
        "name": "if_valid",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [3540, 50],
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                "conditions": [{
                    "id": "1",
                    "leftValue": "={{ $json.ok }}",
                    "rightValue": True,
                    "operator": {"type": "boolean", "operation": "true"}
                }],
                "combinator": "and"
            },
            "options": {}
        },
    },
    # ──────────────────────────────────────────────
    # 16. Audit log erro de validação (false branch)
    # ──────────────────────────────────────────────
    {
        "id": "audit_validacao_falhou",
        "name": "audit_validacao_falhou",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.6,
        "position": [3760, 230],
        "parameters": {
            "operation": "executeQuery",
            "query": "INSERT INTO auto_ads.audit_log (telefone, evento, detalhes) VALUES ($1, 'erro_validacao', $2)",
            "options": {
                "queryReplacement": "={{ $('build_historico').item.json.telefone }},{{ JSON.stringify({motivos: $('validate').item.json.motivos, json: $('validate').item.json.json_extrator}) }}"
            }
        },
        "credentials": {"postgres": config.POSTGRES_CRED},
    },
]

# Idempotência
existing_names = {n["name"] for n in wf["nodes"]}
for n in new_nodes:
    if n["name"] not in existing_names:
        wf["nodes"].append(n)
        print(f"  + {n['name']}")
    else:
        print(f"  = {n['name']} (já existia)")

# Conexões
wf["connections"]["agente_principal"] = {"main": [[{"node": "classifier", "type": "main", "index": 0}]]}
wf["connections"]["classifier"] = {"main": [[{"node": "build_historico", "type": "main", "index": 0}]]}
wf["connections"]["build_historico"] = {"main": [[{"node": "upsert_conversa", "type": "main", "index": 0}]]}
wf["connections"]["upsert_conversa"] = {"main": [[{"node": "send_resposta", "type": "main", "index": 0}]]}
wf["connections"]["send_resposta"] = {"main": [[{"node": "if_confirmado", "type": "main", "index": 0}]]}
# if_confirmado: true → extrator
wf["connections"]["if_confirmado"] = {
    "main": [
        [{"node": "extrator", "type": "main", "index": 0}],
        []  # false: END
    ]
}
wf["connections"]["extrator"] = {"main": [[{"node": "parse_extrator", "type": "main", "index": 0}]]}
wf["connections"]["parse_extrator"] = {"main": [[{"node": "validate", "type": "main", "index": 0}]]}
wf["connections"]["validate"] = {"main": [[{"node": "if_valid", "type": "main", "index": 0}]]}
# if_valid: true → próxima parte (D.1-D.4), false → audit_validacao_falhou
wf["connections"]["if_valid"] = {
    "main": [
        [],  # true → preenchido na parte 3
        [{"node": "audit_validacao_falhou", "type": "main", "index": 0}]
    ]
}

n8n_api.update_workflow(
    WF_ID,
    name=wf["name"],
    nodes=wf["nodes"],
    connections=wf["connections"],
    settings=wf.get("settings", {"executionOrder": "v1"}),
)
print(f"\n✓ Workflow atualizado: {WF_ID}")
print(f"  Nodes totais: {len(wf['nodes'])}")
