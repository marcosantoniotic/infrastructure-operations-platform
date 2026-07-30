from http.server import BaseHTTPRequestHandler, HTTPServer


class ContractHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ok":
            self.send_response(200)
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "https://example.invalid/login")
        else:
            self.send_response(404)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

    def log_message(self, _format, *_args):
        return


HTTPServer(("localhost", 18080), ContractHandler).serve_forever()
