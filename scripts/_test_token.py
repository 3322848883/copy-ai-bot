import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///c:/Users/w6485/Desktop/AI 量化/信号聚合AI/dev.db"

from api.core.security import create_token, decode_token
from api.core.config import get_settings

token = create_token("10000", audience="web")
print("token:", token)
print("audience:", get_settings().jwt_audience)
try:
    payload = decode_token(token, get_settings().jwt_audience)
    print("decoded:", payload)
except Exception as e:
    print("DECODE ERROR:", type(e).__name__, e)
