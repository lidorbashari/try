"""SimpleHTTPRequestHandler + HTTP Range (206) support, like a real CDN (Apple's preview CDN, GitHub Pages).
Safari will not play media from a server without byte ranges, and Chromium cannot seek reliably without them."""
import http.server, os, re


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    def handle_one_request(self):  # a browser aborting a media request is normal, not an error
        try:
            return super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def send_head(self):
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        if not rng or os.path.isdir(path) or not os.path.isfile(path):
            return super().send_head()
        m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
        size = os.path.getsize(path)
        if not m:
            return super().send_head()
        a, b = m.group(1), m.group(2)
        if a == "":
            start, end = max(0, size - int(b or 0)), size - 1
        else:
            start, end = int(a), min(size - 1, int(b) if b else size - 1)
        if start >= size or start > end:
            self.send_response(416); self.send_header("Content-Range", f"bytes */{size}"); self.end_headers(); return None
        f = open(path, "rb"); f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._left = end - start + 1
        return f

    def copyfile(self, source, outputfile):
        left = getattr(self, "_left", None)
        if left is None:
            try:
                return super().copyfile(source, outputfile)
            except (BrokenPipeError, ConnectionResetError):
                return
        try:
            while left > 0:
                buf = source.read(min(65536, left))
                if not buf: break
                outputfile.write(buf); left -= len(buf)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self._left = None

    def end_headers(self):
        if not getattr(self, "_ar", False):
            self.send_header("Accept-Ranges", "bytes") if self.command == "GET" and self.path.endswith((".wav", ".m4a", ".mp3")) and not self.headers.get("Range") else None
        super().end_headers()
