# scripts/_audit_erros_conversa.py
# Guarda das 5 blindagens de erro/conversa (Parte 5). Exit 0 se tudo ok, 1 se regrediu.
#   python3 _audit_erros_conversa.py
import sys, n8n_api

WF = "fBUin1UPt5xJEp6g"
N = {n["name"]: n for n in n8n_api.get_workflow(WF)["nodes"]}
conns = n8n_api.get_workflow(WF)["connections"]
ok = True
def check(cond, msg):
    global ok
    print(("  ✅ " if cond else "  ❌ ") + msg)
    ok = ok and cond

print("="*68); print("GUARDA — blindagem de erros e conversa"); print("="*68)

print("\n[1] Status legível no relatório")
f = N["format_status_response"]["parameters"]["jsCode"]
check("MAPA_STATUS" in f and "No ar" in f, "format_status_response traduz status")
check("Status no Meta: ' + d.status_atual" not in f, "não mostra mais o status cru")

print("\n[2] Gate do SUBIR_DENOVO")
check("gate_subir_denovo" in N, "nó gate_subir_denovo existe")
check([c["node"] for c in conns["switch_intent"]["main"][1]] == ["gate_subir_denovo"], "switch_intent[SUBIR_DENOVO] -> gate")
g = N.get("gate_subir_denovo", {}).get("parameters", {}).get("jsCode", "")
check("pronta_pra_subir" in g, "gate só libera em pronta_pra_subir")

print("\n[3] Erro transitório do Meta = infra + retry por SIM")
c = N["check_gestao_result"]["parameters"]["jsCode"]
check("#613" in c and "rate limit" in c, "classify reconhece rate limit (#613)")
r = N["reset_gestao"]["parameters"]["query"]
check("manter_gestao" in r and "CASE" in r, "reset_gestao preserva estado no retry")
p = N["prep_update_db"]["parameters"]["jsCode"]
check("manter_gestao" in p, "prep_update_db expõe manter_gestao")

print("\n[4] Nenhuma mensagem de gestão manda 'SUBIR DENOVO'")
gestao_nodes = ["build_gestao_confirmation_msg", "build_gestao_response", "build_gestao_msg_cancelado"]
sujos = [n for n in gestao_nodes if "SUBIR DENOVO" in N[n]["parameters"].get("jsCode","").upper()]
check(not sujos, f"limpo (sujos: {sujos})")

print("\n[5] Perguntar antes de trocar de contexto")
ps = N["process_gestao_step"]["parameters"]["jsCode"]
check("pareceComando" in ps, "process_gestao_step tem pareceComando")
check("aguardando_troca" in ps, "trata aguardando_troca")
br = N["build_gestao_response"]["parameters"]["jsCode"]
check("aguardando_troca" in br, "build_gestao_response renderiza a pergunta")

print("\n[6] Rede de segurança: erro de criação não vira loop mudo")
cm = N["check_meta_results"]["parameters"].get("jsCode","")
check("ok" in cm, "check_meta_results classifica resultado")

print("\n[7] Lookups vazios não estancam a cadeia em silêncio")
for nome in ["list_campanhas", "load_meta_token", "load_meta_token_criacao", "load_meta_token_revisao"]:
    check(N[nome].get("alwaysOutputData") is True, f"{nome} tem alwaysOutputData")
check("filter(r => r && r.campanha_id_db" in N["init_gestao"]["parameters"]["jsCode"],
      "init_gestao filtra o item-sentinela (0 campanhas -> sem_campanhas)")

print("\n" + "="*68)
print("RESULTADO: ✅ TUDO OK" if ok else "RESULTADO: ❌ REGREDIU")
sys.exit(0 if ok else 1)
