"""Remove inline reasoning before any content reaches UI, storage or extraction."""


class AnswerStream:
    # Some OpenAI-compatible local servers put these blocks in delta.content.
    markers = ('<think>', '</think>', '<thinking>', '</thinking>', '<analysis>', '</analysis>',
               '［think］', '［/think］')

    def __init__(self):
        self.buffer = ''
        self.depth = 0

    def feed(self, value, final=False):
        self.buffer += value
        output = []
        while self.buffer:
            lower = self.buffer.lower()
            positions = [(lower.find(m), m) for m in self.markers if m in lower]
            if positions:
                pos, marker = min(positions)
                if not self.depth:
                    output.append(self.buffer[:pos])
                closing = marker.startswith('</') or marker.startswith('［/')
                self.depth = max(0, self.depth - 1) if closing else self.depth + 1
                self.buffer = self.buffer[pos + len(marker):]
                continue
            hold = 0
            if not final:
                hold = max((n for m in self.markers for n in range(1, len(m)) if lower.endswith(m[:n])), default=0)
            ready = self.buffer[:-hold] if hold else self.buffer
            if not self.depth:
                output.append(ready)
            self.buffer = self.buffer[-hold:] if hold else ''
            break
        return ''.join(output)
