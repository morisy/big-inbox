#!/usr/bin/env python3
"""
Simple HTTP server for local development of Open Inbox
"""
import http.server
import socketserver
import os
import webbrowser
from threading import Timer

PORT = 8000

class OpenInboxHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Enable CORS for local development
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

def open_browser():
    """Open browser after a short delay"""
    webbrowser.open(f'http://localhost:{PORT}')

def main():
    print("🌐 Starting Open Inbox Local Development Server...")
    print(f"📡 Server running at http://localhost:{PORT}")
    print("📧 Press Ctrl+C to stop")
    print()
    
    # Open browser after 1 second
    Timer(1.0, open_browser).start()
    
    try:
        with socketserver.TCPServer(("", PORT), OpenInboxHTTPRequestHandler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Server stopped")
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"❌ Port {PORT} is already in use. Try a different port:")
            print(f"   python -m http.server {PORT + 1}")
        else:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()