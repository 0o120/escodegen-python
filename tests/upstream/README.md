These files preserve all 100 comparison fixtures from escodegen 2.1.0 for
ES5 through ES2021 syntax, including expected output files and BSD notices.
`PROVENANCE.json` records the exact archive checksum. Run
`python tools/import_upstream.py` to reproduce the import.

There are 37 source fixtures. The generator tests round-trip all 28 valid
programs through pinned Acorn in default and minified formats. Nine old
fixtures combine independently valid module or binding examples into a
program with duplicate declarations/exports, omit exported declarations,
or exercise obsolete draft destructuring syntax. `LEGACY_INVALID.json`
records each one and its independently verified syntax error; tests assert
those errors explicitly. Their source files remain available for comparison.
The modern corpus separately covers valid imports, exports and destructuring.

Formatting spellings can differ deliberately (for example corrected BigInt
or shorter Number spellings); comparison checks the AST's semantic fields.
