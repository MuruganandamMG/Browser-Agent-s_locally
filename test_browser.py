from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from browser_tool import BrowserSession


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/download':
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Disposition', 'attachment; filename="test.txt"')
            self.end_headers()
            self.wfile.write(b'Browser download verified')
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(b'''<html><head><title>Browser fixture</title></head><body>
            <h1>Browser test</h1><label>Name <input id="name" placeholder="Your name"></label>
            <button onclick="document.querySelector('#result').textContent='Hello '+document.querySelector('#name').value">Greet</button>
            <p id="result"></p><select id="choice"><option value="a">A</option><option value="b">B</option></select>
            <input id="check" type="checkbox"><a href="/next">Next page</a><a id="download" href="/download">Download</a>
            <iframe srcdoc="<p>Inside frame</p>"></iframe></body></html>''')

    def log_message(self, *args):
        pass


class BrowserTests(unittest.TestCase):
    def test_real_browser_navigation_and_interaction(self):
        with TemporaryDirectory() as directory:
            http = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            browser = BrowserSession(Path(directory))
            try:
                url = f'http://127.0.0.1:{http.server_port}'
                result = browser.run({'action': 'open', 'url': url})
                self.assertEqual(result['title'], 'Browser fixture')
                selector = next(e['selector'] for e in result['elements'] if e['label'] == 'Your name')
                browser.run({'action': 'fill', 'selector': selector, 'text': 'Gemma'})
                result = browser.run({'action': 'click', 'selector': 'button'})
                self.assertIn('Hello Gemma', result['text'])
                browser.run({'action': 'select', 'selector': '#choice', 'text': 'b'})
                browser.run({'action': 'check', 'selector': '#check'})
                result = browser.run({'action': 'evaluate', 'text': 'document.querySelector("#check").checked'})
                self.assertEqual(result['javascript_result'], 'True')
                result = browser.run({'action': 'snapshot', 'frame': 1})
                self.assertIn('Inside frame', result['text'])
                result = browser.run({'action': 'click', 'selector': '#download'})
                self.assertEqual(result['downloads'][0]['name'], 'test.txt')
                filename = result['downloads'][0]['url'].split('/')[-1]
                self.assertEqual((browser.artifacts / filename).read_text(), 'Browser download verified')
                result = browser.run({'action': 'screenshot'})
                self.assertTrue((browser.artifacts / result['screenshot_url'].split('/')[-1]).exists())
                result = browser.run({'action': 'new_tab', 'url': url + '/next'})
                self.assertEqual(len(result['tabs']), 2)
                result = browser.run({'action': 'switch_tab', 'tab': 0})
                self.assertEqual(result['url'], url + '/')
                result = browser.run({'action': 'close_tab'})
                self.assertEqual(len(result['tabs']), 1)
                with self.assertRaises(ValueError):
                    browser.run({'action': 'open', 'url': 'file:///etc/passwd'})
            finally:
                browser.close()
                http.shutdown()
                http.server_close()
