"""本机代理中继：0.0.0.0:<listen> → 127.0.0.1:<upstream>。

用途：Clash 等代理仅监听 127.0.0.1 时，Docker 容器经 host.docker.internal 走主机代理。
浏览器采集（gate.com）与构建期加速均依赖此中继。

用法（Windows，detached）：
  Start-Process python -ArgumentList "scripts\proxy_relay.py" -WindowStyle Hidden
验证：
  curl.exe -x http://127.0.0.1:17897 -I https://www.gstatic.com/generate_204
"""
import asyncio
import os

LISTEN_PORT = int(os.environ.get("RELAY_LISTEN_PORT", "17897"))
UPSTREAM_HOST = os.environ.get("RELAY_UPSTREAM_HOST", "127.0.0.1")
UPSTREAM_PORT = int(os.environ.get("RELAY_UPSTREAM_PORT", "7897"))


async def _pipe(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def _handle(client_reader, client_writer):
    try:
        up_reader, up_writer = await asyncio.open_connection(UPSTREAM_HOST, UPSTREAM_PORT)
    except Exception:
        client_writer.close()
        return
    await asyncio.gather(_pipe(client_reader, up_writer), _pipe(up_reader, client_writer))


async def main():
    server = await asyncio.start_server(_handle, "0.0.0.0", LISTEN_PORT)
    print(f"relay listening on 0.0.0.0:{LISTEN_PORT} -> {UPSTREAM_HOST}:{UPSTREAM_PORT}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
