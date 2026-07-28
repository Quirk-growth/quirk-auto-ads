# scripts/g_17_retry_gestao_seguro.py
# Partes 1b + 2a + 2b: erro de gestao seguro + retry pela palavra SIM (sem intent novo).
#   1) check_gestao_result.classify: rate limit (#613) e transitorios -> classe 'infra'
#   2) prep_update_db: expoe manter_gestao = (!ok && classe==='infra')
#   3) reset_gestao SQL: se manter_gestao, NAO limpa o estado (mantem passo confirmacao)
#   4) build_gestao_confirmation_msg: mensagens sem "SUBIR DENOVO"; infra pede SIM de novo
#
#   python3 g_17_retry_gestao_seguro.py          -> dry-run (+ node --check)
#   python3 g_17_retry_gestao_seguro.py deploy   -> aplica (backup antes)
import json, subprocess, sys, n8n_api

WF = "fBUin1UPt5xJEp6g"
DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"

# --- Edit 1: check_gestao_result classify infra ---
C_ANCHOR = ("if (/Request failed with status code 5\\d\\d/i.test(msg) || /timeout/i.test(msg) "
            "|| /is_transient.{1,5}true/i.test(msg) || /ECONN/i.test(msg)) {")
C_NEW = ("if (/status code 5\\d\\d/i.test(msg) || /timeout/i.test(msg) "
         "|| /is_transient.{1,5}true/i.test(msg) || /ECONN/i.test(msg) "
         "|| /\\(#613\\)/.test(msg) || /rate limit/i.test(msg) "
         "|| /\"code\":\\s*(1|2|4|17|341|613|80004)\\b/.test(msg)) {")

# --- Edit 2: prep_update_db flag ---
P_ANCHOR = "    ok: r.ok,\n    classe: r.classe || '',"
P_NEW = "    ok: r.ok,\n    classe: r.classe || '',\n    manter_gestao: (r.ok === false && r.classe === 'infra'),"

# --- Edit 3: reset_gestao SQL condicional ---
R_ANCHOR = """UPDATE auto_ads.conversas
SET estado_json = jsonb_set(
  jsonb_set(estado_json, '{gestao}', 'null'::jsonb),
  '{etapa_atual}',
  '"ativa"'::jsonb
)
WHERE telefone = '{{ $('prep_update_db').item.json.telefone }}'"""
R_NEW = """UPDATE auto_ads.conversas
SET estado_json = CASE
  WHEN {{ $('prep_update_db').item.json.manter_gestao ? 'true' : 'false' }} THEN estado_json
  ELSE jsonb_set(
    jsonb_set(estado_json, '{gestao}', 'null'::jsonb),
    '{etapa_atual}',
    '"ativa"'::jsonb
  )
END
WHERE telefone = '{{ $('prep_update_db').item.json.telefone }}'"""

# --- Edit 4: build_gestao_confirmation_msg mensagens ---
M_ANCHOR = ("""  if (classe === 'infra') {
    text = `⚠️ Problema técnico do Meta. Tenta de novo daqui a alguns minutos com "SUBIR DENOVO" ou CANCELAR.`;
  } else {
    text = `⚠️ Não consegui executar: ${motivo}\\n\\nManda SUBIR DENOVO pra tentar novamente OU CANCELAR.`;
  }""")
M_NEW = ("""  if (classe === 'infra') {
    text = `⚙️ Deu um engasgo no Meta (nada de errado com seu pedido). Manda *SIM* de novo daqui a 1 min que eu repito, ou *CANCELAR*.`;
  } else {
    text = `⚠️ Não consegui: ${motivo}\\n\\nMe manda o dado certo, ou *CANCELAR*.`;
  }""")

wf = n8n_api.get_workflow(WF)
N = {n["name"]: n for n in wf["nodes"]}

def repl(node, anchor, new, is_sql=False):
    key = "query" if is_sql else "jsCode"
    src = N[node]["parameters"][key]
    c = src.count(anchor)
    if c != 1:
        print(f"ABORTAR [{node}]: ancora {c}x (esperava 1)\n  {anchor[:80]!r}"); sys.exit(1)
    out = src.replace(anchor, new, 1)
    if not is_sql:
        open("/tmp/_chk.js","w").write("function $(){return{first:()=>({json:{}})}}\nasync function _w(){\n"+out+"\n}\n")
        r = subprocess.run(["node","--check","/tmp/_chk.js"], capture_output=True, text=True)
        print(f"  {node}: syntax", "OK" if r.returncode==0 else "FALHOU")
        if r.returncode: print(r.stderr[:500]); sys.exit(1)
    else:
        print(f"  {node}: SQL trocado")
    return out

j_check = repl("check_gestao_result", C_ANCHOR, C_NEW)
j_prep  = repl("prep_update_db", P_ANCHOR, P_NEW)
q_reset = repl("reset_gestao", R_ANCHOR, R_NEW, is_sql=True)
j_msg   = repl("build_gestao_confirmation_msg", M_ANCHOR, M_NEW)

if not DEPLOY:
    print("\n[DRY-RUN]"); sys.exit(0)

json.dump(wf, open("../n8n_workflow/backup_main_pre_retry_seguro.json","w"), ensure_ascii=False, indent=2)
N["check_gestao_result"]["parameters"]["jsCode"] = j_check
N["prep_update_db"]["parameters"]["jsCode"] = j_prep
N["reset_gestao"]["parameters"]["query"] = q_reset
N["build_gestao_confirmation_msg"]["parameters"]["jsCode"] = j_msg
n8n_api.update_workflow(WF, nodes=wf["nodes"], connections=wf["connections"],
                        settings={"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")})
print("\nDEPLOYADO. Backup: n8n_workflow/backup_main_pre_retry_seguro.json")
