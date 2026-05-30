#!/usr/bin/env python3
"""Aplica sql/005_ultima_alteracao.sql via psycopg2."""
import os, sys
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    sql_path = '/Users/renanreal/quirk_auto_ads/sql/005_ultima_alteracao.sql'
    with open(sql_path) as f:
        sql = f.read()

    db_url = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip()
    db_url = db_url.replace('aws-0-', 'aws-1-')

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()

    cur.execute("""
        SELECT column_name, data_type, column_default
        FROM information_schema.columns
        WHERE table_schema='auto_ads' AND table_name='campanhas' AND column_name='ultima_alteracao'
    """)
    row = cur.fetchone()
    assert row is not None, "Coluna ultima_alteracao não foi criada"
    print(f'✓ Coluna criada: {row[0]} {row[1]} default={row[2]}')

    cur.execute("""SELECT count(*) FROM auto_ads.campanhas WHERE ultima_alteracao IS NULL""")
    null_count = cur.fetchone()[0]
    assert null_count == 0, f"Existem {null_count} linhas com ultima_alteracao NULL"
    print(f'  ✓ todas as linhas têm ultima_alteracao preenchido')

    conn.close()
    print('\n✓ Migration 005 aplicada')


if __name__ == '__main__':
    main()
