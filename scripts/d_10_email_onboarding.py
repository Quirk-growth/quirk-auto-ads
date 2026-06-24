"""
d_10_email_onboarding.py

Adiciona envio de EMAIL de onboarding no workflow gateway (2ZnZqb4wFous4uEs),
em paralelo ao push de WhatsApp. Resolve a fragilidade de depender só do
push (WhatsApp limita mensagens business-initiated pra números frios).

Após pagamento confirmado, o cliente recebe:
  - WhatsApp (push, se uazapi conectada) — boas-vindas + prints
  - EMAIL (sempre) — confirmação + botão "Ativar no WhatsApp" + link do guia

Componentes:
  - build_email_body (Code): monta HTML on-brand, lê email de parse_payment.
    Se não tem email, retorna skip_email=true (não dá erro).
  - if_tem_email (IF): só envia se skip_email=false.
  - send_email (Gmail, gmailOAuth2 "Gmail Quirk" LhaU03ZBvdRKahBA):
    sendTo, subject, message=HTML, appendAttribution=false.

Conexão: switch_router[0] (welcome) → [build_welcome_msgs, build_email_body]
         build_email_body → if_tem_email → send_email

Bugs corrigidos nesta rodada (descobertos no teste):
  1. switch_action lia $input (= asaas_set_group no-op com skip:true) →
     sempre caía em action=skip. Corrigido pra ler $('upsert_cliente').
  2. send_welcome tinha "delay": {{ $json.delay_ms }} mas build_welcome_msgs
     (d_09) não envia mais delay_ms → JSON inválido travava o workflow.
     Removido o campo delay.
  3. send_welcome perdeu continueOnFail na reconstrução → erro do uazapi
     (Service unavailable) travava antes do email. continueOnFail=True
     restaurado em send_welcome/send_welcome_media/send_email/mark_onboarding.

Validado: pagamento fake R$497 com email → email HTML entregue via Gmail Quirk.
"""

# Este script é registro/documentação. As alterações já foram aplicadas
# ao vivo via subscripts inline. Para reproduzir do zero, ver o histórico
# de comandos no transcript ou reconstruir o nó build_email_body com o
# HTML on-brand (confirmação + CTA WhatsApp + link onboarding.html).

print("Registro: email de onboarding adicionado ao gateway 2ZnZqb4wFous4uEs.")
print("Nós: build_email_body, if_tem_email, send_email (Gmail Quirk).")
print("Ver d_10_email_onboarding.py docstring para detalhes e bugs corrigidos.")
