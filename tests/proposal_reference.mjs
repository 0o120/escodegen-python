// Development oracle only; no JavaScript runtime is needed by the library.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const modules = process.env.ESCODEGEN_REFERENCE_NODE_MODULES;
if (!modules) throw new Error('ESCODEGEN_REFERENCE_NODE_MODULES is required');
const parser = await import(pathToFileURL(path.join(modules, '@babel/parser/lib/index.js')));
const omit = new Set(['start', 'end', 'loc', 'range', 'raw', 'extra', 'comments',
  'leadingComments', 'trailingComments', 'innerComments']);
function normalize(value) {
  if (Array.isArray(value)) return value.map(normalize);
  if (value && typeof value === 'object') {
    // Babel's decorator-specific call path omits optional:false. The
    // equivalent parenthesized expression takes its ordinary ESTree path.
    return Object.fromEntries(Object.entries(value).filter(([key, child]) =>
      !omit.has(key) && !(key === 'optional' && child === false))
      .map(([key, child]) => [key, normalize(child)]));
  }
  return typeof value === 'bigint' ? null : value;
}
const jobs = JSON.parse(fs.readFileSync(0, 'utf8'));
const results = jobs.map(job => {
  try {
    const plugins = ['estree', ['decorators', {version: '2023-11'}], 'decoratorAutoAccessors',
      'explicitResourceManagement', 'deferredImportEvaluation', 'sourcePhaseImports'];
    if (job.exportDefaultFrom !== false) plugins.push('exportDefaultFrom');
    return normalize(parser.parse(job.source, {sourceType: job.sourceType || 'module',
      plugins}).program);
  } catch(error) {
    throw new Error(job.source + '\n' + error.message);
  }
});
process.stdout.write(JSON.stringify(results));
