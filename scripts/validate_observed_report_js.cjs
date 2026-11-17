'use strict';
// Compile every inline script, then exercise the actual generated controls with a small DOM fixture.
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const assert = require('node:assert/strict'), crypto = require('node:crypto');
const root = path.resolve(process.argv[2] || '');
assert(process.argv[2], 'Pass the completed report directory');
const report = path.join(root, 'receptiveness_report.html');
const html = fs.readFileSync(report, 'utf8');
const blocks = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].map(m => m[1]);
assert(blocks.length > 33, 'Plotly and client scripts are missing');
blocks.forEach((code, i) => new vm.Script(code, {filename: 'report-inline-'+i+'.js'}));
const metadata = JSON.parse(fs.readFileSync(path.join(root, 'report_figures.json'), 'utf8'));
const people = metadata.figures.filter(r => r.kind === 'individual-trend');
assert.equal(people.length, 16);
const groups = new Map(), cards = new Map(), resized = [], scrolled = [], handlers = {};
for (const row of people) {
  if (!groups.has(row.profile)) groups.set(row.profile, {
    open: false, handlers: {}, plots: [],
    addEventListener(name, fn) { this.handlers[name] = fn; },
    querySelectorAll(selector) { assert.equal(selector, '.plotly-graph-div'); return this.plots; }
  });
  const group = groups.get(row.profile);
  const plot = {_fullLayout: {}, id: row.id}; group.plots.push(plot);
  cards.set('card-'+row.participant, {
    closest(selector) { assert.equal(selector, 'details'); return group; },
    querySelectorAll(selector) { assert.equal(selector, '.plotly-graph-div'); return [plot]; },
    scrollIntoView(options) { assert.equal(options.block, 'start'); scrolled.push(row.participant); }
  });
}
const context = {
  document: {
    querySelectorAll(selector) { assert.equal(selector, 'details'); return [...groups.values()]; },
    getElementById(id) {
      if (id === 'actor-jump') return {addEventListener(name, fn) { handlers[name] = fn; }};
      assert(cards.has(id), 'Jump target does not exist'); return cards.get(id);
    }
  },
  requestAnimationFrame(fn) { fn(); },
  Plotly: {Plots: {resize(plot) { resized.push(plot.id); }}}
};
vm.runInNewContext(blocks.at(-1), context, {filename: 'report-controls.js'});
for (const group of groups.values()) {
  group.open = true; group.handlers.toggle.call(group);
}
assert.equal(resized.length, 16, 'Opening clusters must resize all individual figures');
resized.length = 0;
for (const row of people) {
  const group = groups.get(row.profile); group.open = false;
  handlers.change.call({value: row.participant});
  assert(group.open, 'Jump did not open the actor cluster');
}
assert.equal(resized.length, 16);
assert.deepEqual(scrolled, people.map(r => r.participant));
const result = {
  validated_at_utc: new Date().toISOString(),
  report_sha256: crypto.createHash('sha256').update(html).digest('hex'),
  compiled_inline_scripts: blocks.length,
  actor_jump_targets_exercised: scrolled.length,
  cluster_resize_targets_exercised: 16,
  verified: true,
  scope: 'JavaScript syntax and actual generated control handlers; not native browser visual/timing validation.'
};
fs.writeFileSync(path.join(root, 'report_javascript_validation.json'), JSON.stringify(result, null, 2)+'\n');
process.stdout.write(JSON.stringify(result, null, 2)+'\n');
