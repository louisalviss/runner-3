#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import subprocess
import sys

NETWORK = 'browser-stack_default'
LISTEN_PORT = 18889
UPSTREAM_HOST = '127.0.0.1'
UPSTREAM_PORT = 8888


def docker_network_info() -> tuple[str, str, str]:
    cp = subprocess.run(['docker', 'network', 'inspect', NETWORK], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=15)
    if cp.returncode != 0:
        raise RuntimeError(f'network_unavailable:{NETWORK}')
    rows = json.loads(cp.stdout or '[]')
    if not rows:
        raise RuntimeError(f'network_empty:{NETWORK}')
    row = rows[0]
    cfg = ((row.get('IPAM') or {}).get('Config') or [{}])[0]
    gateway = str(cfg.get('Gateway') or '').strip()
    subnet = str(cfg.get('Subnet') or '').strip()
    network_id = str(row.get('Id') or '').strip()
    if not gateway or not subnet or len(network_id) < 12:
        raise RuntimeError(f'network_metadata_invalid:{NETWORK}')
    return gateway, subnet, 'br-' + network_id[:12]


def ensure_firewall_rule(gateway: str, subnet: str, bridge: str) -> None:
    rule = ['-i', bridge, '-s', subnet, '-d', gateway, '-p', 'tcp', '--dport', str(LISTEN_PORT), '-j', 'ACCEPT']
    check = subprocess.run(['iptables', '-C', 'INPUT', *rule], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if check.returncode != 0:
        add = subprocess.run(['iptables', '-I', 'INPUT', '1', *rule], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if add.returncode != 0:
            raise RuntimeError(f'firewall_rule_failed:{add.stderr.strip()}')


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def handle(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
    try:
        upstream_reader, upstream_writer = await asyncio.open_connection(UPSTREAM_HOST, UPSTREAM_PORT)
    except Exception:
        client_writer.close()
        try:
            await client_writer.wait_closed()
        except Exception:
            pass
        return
    await asyncio.gather(pipe(client_reader, upstream_writer), pipe(upstream_reader, client_writer), return_exceptions=True)


async def main() -> None:
    gateway, subnet, bridge = docker_network_info()
    ensure_firewall_rule(gateway, subnet, bridge)
    server = await asyncio.start_server(handle, gateway, LISTEN_PORT)
    print(json.dumps({'ok': True, 'profile': 'flippa-legacy', 'listen': f'{gateway}:{LISTEN_PORT}', 'upstream': f'{UPSTREAM_HOST}:{UPSTREAM_PORT}', 'bridge': bridge, 'source_subnet': subnet}), flush=True)
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f'flippa-vn-proxy-relay: {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
        raise
