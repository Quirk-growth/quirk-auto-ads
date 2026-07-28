# scripts/g_18_pergunta_troca.py
# Parte 3: quando o cliente manda um COMANDO no meio de um fluxo de gestao (esperando
# numero/valor/sim), em vez de "numero invalido" o bot pergunta se quer CONTINUAR a
# anterior ou TROCAR pra nova. Sem mexer no switch: usa acao 'avanca' + flag
# gestao.aguardando_troca, e o render decide.
#   python3 g_18_pergunta_troca.py          -> dry-run (+ node --check)
#   python3 g_18_pergunta_troca.py deploy   -> aplica (backup antes)
import json, subprocess, sys, n8n_api

WF = "fBUin1UPt5xJEp6g"
DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"

# ---------- Edit 1: process_gestao_step ----------
# 1a) helper + tratamento de aguardando_troca, logo apos o check de cancelar
PS_ANCHOR = """if (/^(cancelar|cancela|deixa\\s+pra\\s+l[áa])[!.?]*$/i.test(msg)) {
  return [{ json: { acao: 'reset', motivo: 'cancelado_pelo_cliente' } }];
}"""
PS_NEW = """if (/^(cancelar|cancela|deixa\\s+pra\\s+l[áa])[!.?]*$/i.test(msg)) {
  return [{ json: { acao: 'reset', motivo: 'cancelado_pelo_cliente' } }];
}

function pareceComando(m) {
  const s = String(m || '').trim().toLowerCase();
  return /^(pausar|parar|reativar|ativar|encerrar|arquivar|status|relat[óo]rio|nova campanha|subir|tutorial|ajuda)\\b/.test(s)
      || /^(alterar|mudar|trocar)\\s+(verba|p[úu]blico|publico|geo|regi[ãa]o|regiao|cidade|bairro|localiza)/.test(s);
}

// Ja perguntou "continuar ou trocar?" no turno anterior -> resolve a decisao
if (gestao.aguardando_troca) {
  if (/^(continuar|continua|anterior|seguir|segue|1)\\b/i.test(msg)) {
    delete gestao.aguardando_troca;
    return [{ json: { acao: 'avanca', estado, gestao } }];
  }
  if (/^(trocar|troca|nova|desconsiderar|desconsidera|deixa|descarta|2)\\b/i.test(msg)) {
    return [{ json: { acao: 'reset', motivo: 'troca_confirmada' } }];
  }
  return [{ json: { acao: 'avanca', estado, gestao } }];
}"""

# 1b) selecao: no ramo de numero invalido, se pareceComando -> pergunta_troca
PS_SEL_ANCHOR = """  if (isNaN(num) || num < 1 || num > (gestao.lista_candidatas || []).length) {
    return [{ json: { acao: 'erro_input', motivo: 'numero_invalido', proximo_passo: 'selecao', gestao, estado } }];
  }"""
PS_SEL_NEW = """  if (isNaN(num) || num < 1 || num > (gestao.lista_candidatas || []).length) {
    if (pareceComando(msg)) { gestao.aguardando_troca = true; return [{ json: { acao: 'avanca', estado, gestao } }]; }
    return [{ json: { acao: 'erro_input', motivo: 'numero_invalido', proximo_passo: 'selecao', gestao, estado } }];
  }"""

# 1c) coleta_valor: ANTES de aceitar texto livre, se pareceComando -> pergunta_troca
PS_COL_ANCHOR = """  const passo = gestao.passo;
  const verbo = gestao.verbo;"""
# (o bloco coleta_valor comeca depois; injetamos a guarda no inicio do if coleta_valor)
PS_COL2_ANCHOR = "if (passo === 'coleta_valor') {\n  let novo_valor = null;"
PS_COL2_NEW = "if (passo === 'coleta_valor') {\n  if (pareceComando(msg)) { gestao.aguardando_troca = true; return [{ json: { acao: 'avanca', estado, gestao } }]; }\n  let novo_valor = null;"

# 1d) confirmacao: no ramo invalido, se pareceComando -> pergunta_troca
PS_CONF_ANCHOR = """  if (/^(n[aã]o|n)[!.?]*$/i.test(msg)) return [{ json: { acao: 'reset', motivo: 'cancelado_no_confirma' } }];
  return [{ json: { acao: 'erro_input', motivo: 'confirma_invalido', proximo_passo: 'confirmacao', gestao, estado } }];"""
PS_CONF_NEW = """  if (/^(n[aã]o|n)[!.?]*$/i.test(msg)) return [{ json: { acao: 'reset', motivo: 'cancelado_no_confirma' } }];
  if (pareceComando(msg)) { gestao.aguardando_troca = true; return [{ json: { acao: 'avanca', estado, gestao } }]; }
  return [{ json: { acao: 'erro_input', motivo: 'confirma_invalido', proximo_passo: 'confirmacao', gestao, estado } }];"""

# ---------- Edit 2: build_gestao_response — render da pergunta CONTINUAR/TROCAR ----------
BR_ANCHOR = "const passo = gestao?.passo;\nconst verbo = gestao?.verbo;"
BR_NEW = """const passo = gestao?.passo;
const verbo = gestao?.verbo;

if (gestao?.aguardando_troca) {
  const acaoLabel = { PAUSAR:'pausar uma campanha', REATIVAR:'reativar uma campanha', ENCERRAR:'encerrar uma campanha', ALTERAR_VERBA:'alterar a verba', ALTERAR_PUBLICO:'alterar o público', ALTERAR_GEO:'alterar a localização', STATUS:'ver status' }[verbo] || 'uma alteração';
  const nome = gestao?.selecionada?.nome ? ` na campanha "${gestao.selecionada.nome}"` : '';
  return [{ json: { text: `Você tem *${acaoLabel}*${nome} em andamento. Quer *CONTINUAR* ela, ou *TROCAR* pra atender seu novo pedido?`, telefone: $('normalize_phone').first().json.telefone_normalizado } }];
}"""

# ---------- Edit 3: build_gestao_msg_cancelado — mensagem do TROCAR ----------
MC_ANCHOR = "else if (motivo === 'gestao_vazio') text = 'Não tem operação em andamento.';"
MC_NEW = "else if (motivo === 'gestao_vazio') text = 'Não tem operação em andamento.';\nelse if (motivo === 'troca_confirmada') text = 'Beleza, deixei a alteração anterior de lado 👍. Me manda de novo o que você quer fazer agora.';"

wf = n8n_api.get_workflow(WF)
N = {n["name"]: n for n in wf["nodes"]}

def apply(node, pairs):
    jc = N[node]["parameters"]["jsCode"]
    for anchor, new in pairs:
        c = jc.count(anchor)
        if c != 1:
            print(f"ABORTAR [{node}]: ancora {c}x (esperava 1):\n  {anchor[:70]!r}"); sys.exit(1)
        jc = jc.replace(anchor, new, 1)
    open("/tmp/_chk.js","w").write("function $(){return{first:()=>({json:{estado:{},gestao:{},telefone_normalizado:'x'}})}}\nasync function _w(){\n"+jc+"\nreturn 0;}\n")
    r = subprocess.run(["node","--check","/tmp/_chk.js"], capture_output=True, text=True)
    print(f"  {node}: syntax", "OK" if r.returncode==0 else "FALHOU")
    if r.returncode: print(r.stderr[:600]); sys.exit(1)
    return jc

j_ps = apply("process_gestao_step", [
    (PS_ANCHOR, PS_NEW),
    (PS_SEL_ANCHOR, PS_SEL_NEW),
    (PS_COL2_ANCHOR, PS_COL2_NEW),
    (PS_CONF_ANCHOR, PS_CONF_NEW),
])
j_br = apply("build_gestao_response", [(BR_ANCHOR, BR_NEW)])
j_mc = apply("build_gestao_msg_cancelado", [(MC_ANCHOR, MC_NEW)])

if not DEPLOY:
    print("\n[DRY-RUN]"); sys.exit(0)

json.dump(wf, open("../n8n_workflow/backup_main_pre_pergunta_troca.json","w"), ensure_ascii=False, indent=2)
N["process_gestao_step"]["parameters"]["jsCode"] = j_ps
N["build_gestao_response"]["parameters"]["jsCode"] = j_br
N["build_gestao_msg_cancelado"]["parameters"]["jsCode"] = j_mc
n8n_api.update_workflow(WF, nodes=wf["nodes"], connections=wf["connections"],
                        settings={"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")})
print("\nDEPLOYADO. Backup: n8n_workflow/backup_main_pre_pergunta_troca.json")
