-- Cadastro do telefone de teste do Renan (founder Quirk Growth)
-- Necessário pra qualquer teste end-to-end funcionar
-- Aplicar após 001_init_schema.sql

INSERT INTO auto_ads.clientes (telefone, ad_account_id, page_id, wa_link, nome_cliente)
VALUES (
  '5511980838409',
  '3771507593117364',
  '687786881077238',
  'https://wa.me/5511952136200',
  'Renan Real (teste interno)'
)
ON CONFLICT (telefone) DO UPDATE SET
  ad_account_id = EXCLUDED.ad_account_id,
  page_id = EXCLUDED.page_id,
  wa_link = EXCLUDED.wa_link,
  nome_cliente = EXCLUDED.nome_cliente;

INSERT INTO auto_ads.conversas (telefone, historico, criativo_url)
VALUES ('5511980838409', '', '')
ON CONFLICT (telefone) DO NOTHING;
