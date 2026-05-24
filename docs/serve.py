import os
import http.server
import socketserver

os.chdir("/Users/shivanshgupta/Desktop/country-guide-reconciliation/site")

handler = http.server.SimpleHTTPRequestHandler
with socketserver.TCPServer(("127.0.0.1", 8000), handler) as httpd:
    print("Serving docs at http://127.0.0.1:8000")
    httpd.serve_forever()
