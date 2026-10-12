// Development oracle only. Runtime generation remains pure Python.
const fs = require('node:fs');
const path = require('node:path');
const modules = process.env.ESCODEGEN_REFERENCE_NODE_MODULES ||
  path.resolve(__dirname, '../tools/reference/node_modules');
const acorn = require(path.join(modules, 'acorn'));
const jsx = require(path.join(modules, 'acorn-jsx'));
const Parser = acorn.Parser.extend(jsx());
function normalize(value) {
  if (Array.isArray(value)) return value.map(normalize);
  if (value && typeof value === 'object') {
    const result = {};
    for (const [key, item] of Object.entries(value)) {
      if (['start', 'end', 'loc', 'range', 'raw'].includes(key)) continue;
      if (key === 'value' && value.regex) { result.value = null; continue; }
      if (key === 'directive') {
        result.directive = item === 'use strict' ? 'use strict' : '<non-strict-directive>';
        continue;
      }
      result[key] = normalize(item);
    }
    return result;
  }
  return typeof value === 'bigint' ? null : value;
}
const jobs = JSON.parse(fs.readFileSync(0, 'utf8'));
const results = jobs.map(job => {
  const options = {ecmaVersion: 2026, sourceType: job.module ? 'module' : 'script', locations: true, ranges: true};
  let parsed;
  try { parsed = Parser.parse(job.source, options); }
  catch(error) {
    if (job.reportError) return {error: error.message};
    throw new Error(job.source + '\n' + error.message);
  }
  return job.normalized ? normalize(parsed) : parsed;
});
process.stdout.write(JSON.stringify(results, (_, value) => typeof value === 'bigint' ? null : value));
