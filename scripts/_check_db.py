import sqlite3

con = sqlite3.connect(r"c:\Users\w6485\Desktop\AI 量化\信号聚合AI\dev.db")
print("--- strategies ---")
for r in con.execute("select id, trader_id, display_name, status from strategies").fetchall():
    print(r)
print("--- api_keys ---")
for r in con.execute("select id, user_id, exchange, status from api_keys").fetchall():
    print(r)
print("--- users 9999/10000 ---")
for r in con.execute("select id, email, role from users where id in (9999,10000)").fetchall():
    print(r)
con.close()
