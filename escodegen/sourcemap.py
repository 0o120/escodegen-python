"""Small dependency-free Source Map v3 writer (UTF-16 generated columns)."""
import json
import re
from types import SimpleNamespace


_BASE64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'


def _vlq(value):
    value = (-value << 1 | 1) if value < 0 else value << 1
    encoded = ''
    while True:
        digit = value & 31
        value >>= 5
        encoded += _BASE64[digit | (32 if value else 0)]
        if not value:
            return encoded


class SourceMap:
    def __init__(self, entries, file=None, sourceRoot=None):
        self.entries = entries
        self.file = file
        self.sourceRoot = sourceRoot
        self.contents = {}

    def setSourceContent(self, source, content):
        self.contents[source] = content

    def toJSON(self):
        sources = list(dict.fromkeys(entry[2] for entry in self.entries if entry[2] is not None))
        names = list(dict.fromkeys(entry[5] for entry in self.entries if entry[5] is not None))
        source_ids = {source: i for i, source in enumerate(sources)}
        name_ids = {name: i for i, name in enumerate(names)}
        lines = [[]]
        previous_source = previous_line = previous_column = previous_name = 0
        previous_generated = 0
        current_line = 0
        for generated_line, generated_column, source, original_line, original_column, name in self.entries:
            while current_line < generated_line:
                lines.append([])
                current_line += 1
                previous_generated = 0
            fields = [generated_column - previous_generated]
            previous_generated = generated_column
            if source is not None:
                source_id = source_ids[source]
                fields.extend([source_id - previous_source, original_line - previous_line,
                               original_column - previous_column])
                previous_source, previous_line, previous_column = source_id, original_line, original_column
                if name is not None:
                    name_id = name_ids[name]
                    fields.append(name_id - previous_name)
                    previous_name = name_id
            lines[-1].append(''.join(_vlq(field) for field in fields))
        result = {'version': 3, 'sources': sources, 'names': names,
                  'mappings': ';'.join(','.join(line) for line in lines)}
        if self.file is not None:
            result['file'] = self.file
        if self.sourceRoot is not None:
            result['sourceRoot'] = self.sourceRoot
        if self.contents:
            result['sourcesContent'] = [self.contents.get(source) for source in sources]
        return result

    def toString(self):
        return json.dumps(self.toJSON(), ensure_ascii=True, separators=(',', ':'))

    def __str__(self):
        return self.toString()


class SourceNode:
    def __init__(self, line=None, column=None, source=None, children=None, name=None):
        if source is not None and not isinstance(source, str):
            raise ValueError('source-map source names must be strings')
        if line is not None and (not isinstance(line, int) or line < 1 or
                                 not isinstance(column, int) or column < 0):
            raise ValueError('source-map locations require line >= 1 and UTF-16 column >= 0')
        self.location = (source, line - 1, column, name) if line is not None and source is not None else None
        self.children = children if isinstance(children, list) else [children]

    def _chunks(self, inherited=None):
        location = self.location or inherited
        def visit(child):
            if isinstance(child, SourceNode):
                yield from child._chunks(location)
            elif isinstance(child, list):
                for item in child:
                    yield from visit(item)
            elif child is not None:
                yield str(child), location
        for child in self.children:
            yield from visit(child)

    def toString(self):
        return ''.join(text for text, _ in self._chunks())

    def toStringWithSourceMap(self, options):
        entries = []
        generated_line = generated_column = 0
        last_location = object()
        last_position = None
        code = []
        for text, location in self._chunks():
            code.append(text)
            parts = re.split(r'(\r\n|[\r\n\u2028\u2029])', text)
            for part in parts:
                if not part:
                    continue
                if part in ('\r\n', '\r', '\n', '\u2028', '\u2029'):
                    generated_line += 1
                    generated_column = 0
                    last_location = object()
                    continue
                position = (generated_line, generated_column)
                if location != last_location:
                    fields = location or (None, None, None, None)
                    entry = (*position, *fields)
                    if position == last_position:
                        entries[-1] = entry
                    else:
                        entries.append(entry)
                    last_position = position
                    last_location = location
                generated_column += len(part.encode('utf-16-le', 'surrogatepass')) // 2
        return SimpleNamespace(code=''.join(code), map=SourceMap(entries, options.file, options.sourceRoot))

    def replaceRight(self, pattern, replacement):
        text = self.toString()
        match = re.search(pattern, text)
        if match is None:
            return self
        if match.end() != len(text):
            raise ValueError('replaceRight requires a trailing match')
        keep = match.start()
        children = []
        for chunk, location in self._chunks():
            if keep <= 0:
                break
            part = chunk[:keep]
            if location:
                source, line, column, name = location
                children.append(SourceNode(line + 1, column, source, part, name))
            else:
                children.append(part)
            keep -= len(chunk)
        children.append(replacement)
        self.children = children
        return self

    def _legacy_location(self):
        if self.location is None:
            return None, None, None
        source, line, column, _ = self.location
        return line + 1, column, source

    def __str__(self):
        return self.toString()

    def __len__(self):
        return len(self.toString())

    def __getitem__(self, key):
        return self.toString()[key]

    def __add__(self, other):
        return SourceNode(children=[self, other])

    def __radd__(self, other):
        return SourceNode(children=[other, self])
