#!/usr/bin/env python3
"""
Vigia do Pregão
---------------
Acompanha o chat público do pregoeiro no Compras.gov.br e avisa no celular.

Etapa 1 (agora): página de diagnóstico para descobrir como o Compras.gov.br
entrega as mensagens públicas do chat.

Como rodar:  python3 vigia_pregao.py   (no Render: Start Command = python vigia_pregao.py)
Não precisa instalar nada além do Python 3.8+.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8000"))
CNET = "https://cnetmobile.estaleiro.serpro.gov.br"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def digitos(s):
    return re.sub(r"\D", "", str(s or ""))


def erro_txt(e):
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code}"
    if isinstance(e, urllib.error.URLError):
        return f"sem conexão ({e.reason})"
    return str(e)[:200]


def baixar(url, timeout=30, headers=None):
    h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def diagnostico(compra):
    """Abre a página pública de acompanhamento e procura de onde vêm as mensagens do chat."""
    linhas = [f"DIAGNOSTICO VIGIA compra={compra}", ""]
    pagina = f"{CNET}/comprasnet-web/public/compras/acompanhamento-compra?compra={compra}"
    try:
        st, ct, body = baixar(pagina)
        html = body.decode("utf-8", "replace")
        linhas.append(f"pagina: HTTP {st} {ct} {len(body)} bytes")
    except Exception as e:
        linhas.append(f"pagina: ERRO {erro_txt(e)}")
        return "\n".join(linhas)

    base = re.search(r'<base href="([^"]*)"', html)
    base = base.group(1) if base else "/comprasnet-web/"
    scripts = re.findall(r'<script[^>]+src="([^"]+\.js)"', html)
    linhas.append("base: " + base)
    linhas.append("scripts: " + ", ".join(scripts))

    def url_js(src):
        if src.startswith("http"):
            return src
        if src.startswith("/"):
            return CNET + src
        return f"{CNET}{base.rstrip('/')}/{src}"

    achados, contextos = set(), []
    fila = list(scripts)
    vistos = set()
    while fila and len(vistos) < 45:
        src = fila.pop(0)
        nome = src.split("/")[-1]
        if nome in vistos:
            continue
        vistos.add(nome)
        try:
            st, ct, body = baixar(url_js(src if "/" in src else base + src), timeout=40)
            js = body.decode("utf-8", "replace")
        except Exception as e:
            linhas.append(f"js {nome}: ERRO {erro_txt(e)}")
            continue
        if js.lstrip().startswith("<"):
            linhas.append(f"js {nome}: veio HTML em vez de JS ({len(body)} bytes)")
            continue
        n_ctx = 0
        for m in re.finditer(r'chunk-[A-Z0-9]+\.js', js):
            if m.group(0) not in vistos:
                fila.append(m.group(0))
        for m in re.finditer(r'["\'`]([^"\'`\s]{0,80}(?:comprasnet-[a-z\-]+|/chat|mensage[mn])[^"\'`\s]{0,120})["\'`]', js, re.I):
            achados.add(m.group(1))
        for m in re.finditer(r'.{0,200}(comprasnet-mensagem|/chat/|chat\b).{0,260}', js):
            if n_ctx < 12:
                contextos.append(f"[{nome}] " + m.group(0).replace("\n", " ")[:460])
                n_ctx += 1
        linhas.append(f"js {nome}: {len(body)} bytes, {n_ctx} trechos")

    linhas.append("")
    linhas.append(f"== caminhos encontrados ({len(achados)}):")
    for t in sorted(achados)[:200]:
        linhas.append("  " + t)
    linhas.append("")
    linhas.append(f"== trechos do codigo ({len(contextos)}):")
    for t in contextos[:60]:
        linhas.append("  " + t)
    linhas.append("")
    linhas.append("== testes diretos:")
    candidatos = [
        f"{CNET}/comprasnet-mensagem/v2/chat/{compra}",
        f"{CNET}/comprasnet-mensagem/v1/chat/{compra}",
        f"{CNET}/comprasnet-mensagem/v2/public/chat/{compra}",
        f"{CNET}/comprasnet-mensagem/public/v1/compras/{compra}/mensagens",
        f"{CNET}/comprasnet-fase-externa/public/v1/compras/{compra}",
        f"{CNET}/comprasnet-fase-externa/public/v1/compras/{compra}/mensagens",
        f"{CNET}/comprasnet-fase-externa/public/v2/compras/{compra}/mensagens",
        f"{CNET}/comprasnet-fase-externa/v1/compras/{compra}/mensagens",
    ]
    for u in candidatos:
        try:
            st, ct, body = baixar(u, timeout=20)
            linhas.append(f"  {st} {ct[:30]} {u}")
            linhas.append("     " + body[:400].decode("utf-8", "replace").replace("\n", " "))
        except urllib.error.HTTPError as e:
            corpo = ""
            try:
                corpo = e.read()[:600].decode("utf-8", "replace").replace("\n", " ")
            except Exception:
                pass
            linhas.append(f"  {e.code} {u}")
            if corpo:
                linhas.append("     " + corpo)
        except Exception as e:
            linhas.append(f"  ERRO {erro_txt(e)} {u}")
    return "\n".join(linhas)


PAGINA = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Vigia do Pregão</title>
<style>body{margin:0;background:#0d1422;color:#e8eef8;font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:640px;margin:0 auto;padding:48px 16px}h1{margin:0 0 8px}p{color:#94a3bb}</style></head>
<body><main><h1>Vigia do Pregão</h1><p>Em construção. Em breve: avisos no celular quando o pregoeiro escrever no chat.</p></main></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("  " + (fmt % args) + "\n")

    def _send(self, code, body, ctype):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/diagnostico":
            q = urllib.parse.parse_qs(u.query)
            compra = digitos(q.get("compra", ["20014106000482026"])[0])
            try:
                txt = diagnostico(compra)
            except Exception as e:
                txt = "ERRO: " + erro_txt(e)
            return self._send(200, txt, "text/plain; charset=utf-8")
        if u.path in ("/", "/index.html"):
            return self._send(200, PAGINA, "text/html; charset=utf-8")
        self._send(404, "não encontrado", "text/plain; charset=utf-8")


def main():
    na_nuvem = "PORT" in os.environ
    srv = ThreadingHTTPServer(("0.0.0.0" if na_nuvem else "127.0.0.1", PORT), Handler)
    print(f"Vigia do Pregão rodando na porta {PORT}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
