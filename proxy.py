#!/usr/bin/env python3
"""
NE SC Dashboard — Network Proxy Server
Zero external dependencies (Python 3.6+ stdlib only)

Usage:
  python proxy.py          (or double-click start_dashboard.bat)
  Then open http://<this-machine-ip>:8080 in any browser on the network
"""
import http.server
import http.client
import re
import ssl
import os
import sys
import socket

PORT = 8080
ODOO_HOST = 'neuroelectrics.cloudodoo.com'
HTML_FILE = 'sc_dashboard_standalone.html'
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_local_ip():
    """Return the LAN IP of this machine (the one reachable by colleagues)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return socket.gethostbyname(socket.gethostname())


class ProxyHandler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path in ('/', '/index.html', '/' + HTML_FILE):
            self._serve_html()
        else:
            self._proxy('GET')

    def do_POST(self):
        self._proxy('POST')

    # ── Serve dashboard HTML (rewrites ODOO_URL to '' for relative calls) ──
    def _serve_html(self):
        path = os.path.join(SCRIPT_DIR, HTML_FILE)
        try:
            with open(path, 'rb') as f:
                content = f.read()
            # Rewrite hardcoded URL → empty string so fetch() calls go to localhost
            content = content.replace(
                b"const ODOO_URL = 'https://neuroelectrics.cloudodoo.com';",
                b"const ODOO_URL = '';"
            )
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404, f'{HTML_FILE} not found — make sure it is in the same folder as proxy.py')

    # ── Forward any other path to Odoo over HTTPS ──────────────────────────
    def _proxy(self, method):
        body_len = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(body_len) if body_len > 0 else b''

        fwd = {}
        for h in ('Content-Type', 'Cookie', 'Accept', 'X-Requested-With'):
            v = self.headers.get(h)
            if v:
                fwd[h] = v
        fwd['Host'] = ODOO_HOST

        ctx = ssl.create_default_context()
        conn = http.client.HTTPSConnection(ODOO_HOST, context=ctx, timeout=30)
        try:
            conn.request(method, self.path, body=body, headers=fwd)
            resp = conn.getresponse()
            body_out = resp.read()

            self.send_response(resp.status)
            self.send_header('Content-Type',   resp.getheader('Content-Type', 'application/json'))
            self.send_header('Content-Length', str(len(body_out)))

            # Forward Set-Cookie headers, stripping Domain / Secure / SameSite
            # so cookies are accepted by localhost
            for key, val in resp.getheaders():
                if key.lower() == 'set-cookie':
                    val = re.sub(r';\s*[Dd]omain=[^;,]+',     '', val)
                    val = re.sub(r';\s*[Ss]ecure\b',           '', val)
                    val = re.sub(r';\s*[Ss]ame[Ss]ite=[^;,]+', '', val)
                    self.send_header('Set-Cookie', val)

            self.end_headers()
            self.wfile.write(body_out)

        except ssl.SSLError as e:
            self.send_error(502, f'SSL error: {e}')
        except Exception as e:
            self.send_error(502, f'Proxy error: {e}')
        finally:
            conn.close()

    def log_message(self, fmt, *args):
        # Only print non-200 responses to keep the console clean
        if args and str(args[1]) not in ('200', '204', '304'):
            print(f'[proxy] {args[0]}  →  {args[1]}')


if __name__ == '__main__':
    local_ip = get_local_ip()
    server = http.server.HTTPServer(('0.0.0.0', PORT), ProxyHandler)
    print(f'\n  Neuroelectrics SC Dashboard')
    print(f'  ─────────────────────────────────────────────────────')
    print(f'  Tu URL (este PC)  →  http://localhost:{PORT}')
    print(f'  URL para el equipo →  http://{local_ip}:{PORT}')
    print(f'  Proxying to        →  https://{ODOO_HOST}')
    print(f'  ─────────────────────────────────────────────────────')
    print(f'  Comparte http://{local_ip}:{PORT} con tus compañeros.')
    print(f'  Mantén esta ventana abierta mientras lo usen.')
    print(f'  Ctrl+C para parar.\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nProxy stopped.')
