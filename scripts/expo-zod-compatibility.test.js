'use strict';
// Exercise actual installed Expo CLI consumers and their normally resolved Zod.
// Optional MCP SDK registration is not covered; native schema conversion is a separate boundary.
// Arrays capped at 32 test the fixed leading-size gate; production plugin limits remain unchanged.
const assert = require('node:assert/strict');
const path = require('node:path');
const test = require('node:test');
const { createRequire } = require('node:module');
const projectRoot = path.resolve(__dirname, '..');
const projectRequire = createRequire(path.join(projectRoot, 'package.json'));
const expoRequire = createRequire(projectRequire.resolve('expo/package.json'));
const cliPath = expoRequire.resolve('@expo/cli/package.json');
const cliRoot = path.dirname(cliPath);
const cliRequire = createRequire(cliPath);
const zod = cliRequire('zod');
const { z } = zod;
const allowed = new Set(['DevToolsPlugin.schema.js', 'createMCPDevToolsExtensionSchema.js', 'DevToolsPluginCliExtensionResults.js']);
function consumer(name) {
  assert.ok(allowed.has(name));
  const relative = `build/src/start/server/${name}`;
  const file = path.join(cliRoot, relative);
  // Actual installed consumer requires its own resolved overridden Zod, without substitution.
  return cliRequire(file);
}
const { PluginSchema, DevToolsPluginOutputSchema } = consumer('DevToolsPlugin.schema.js');
const { createMCPDevToolsExtensionSchema } = consumer('createMCPDevToolsExtensionSchema.js');
const { DevToolsPluginCliExtensionResults } = consumer('DevToolsPluginCliExtensionResults.js');
function plugin() {
  return { packageName: 'owned-fixture-plugin', packageRoot: '/owned/fixture', bannerTitle: false,
    cliExtensions: { description: 'Bounded fixture', entryPoint: './fixture.js', commands: [
      { name: 'inspect', title: 'Inspect', environments: ['cli', 'mcp'], parameters: [
        { name: 'query', type: 'text', description: 'Query text' }, { name: 'count', type: 'number' }, { name: 'confirmed', type: 'confirm' },
      ] }, { name: 'status', title: 'Status', environments: ['mcp'] },
    ] } };
}
const output = [
  { type: 'text', text: 'Review complete', level: 'info' },
  { type: 'audio', url: 'https://example.test/sound.ogg', text: 'Audio' },
  { type: 'image', url: 'https://example.test/image.png' },
];
function rejects(schema, value) {
  const result = schema.safeParse(value);
  assert.equal(result.success, false);
  assert.ok(result.error.issues.length > 0);
  for (const issue of result.error.issues) {
    assert.equal(typeof issue.message, 'string');
    assert.ok(Array.isArray(issue.path));
  }
  return result.error;
}

test('Z01 exact default implementation is Zod v4, with no v3 modules loaded', () => {
  assert.equal(cliRequire('zod/package.json').version, '4.6.7');
  assert.deepEqual(z.core.version, { major: 4, minor: 6, patch: 7 });
  assert.equal(z.object, cliRequire('zod/v4').object);
  assert.ok(cliRequire.resolve('zod').endsWith(path.join('zod', 'index.cjs')));
  assert.equal(Object.keys(require.cache).some(name => name.includes(`${path.sep}zod${path.sep}v3${path.sep}`)), false);
});

test('Z02 actual Expo descriptor accepts optional fields and readonly environments', () => {
  const input = plugin(); input.extra = 'stripped';
  const parsed = PluginSchema.parse(input);
  assert.equal(parsed.extra, undefined);
  assert.equal(Object.isFrozen(parsed.cliExtensions.commands[0].environments), true);
  assert.throws(() => parsed.cliExtensions.commands[0].environments.push('mcp'), TypeError);
  assert.deepEqual(PluginSchema.parse({ packageName: 'minimal', packageRoot: '/owned' }), { packageName: 'minimal', packageRoot: '/owned' });
  for (const bannerTitle of [true, false, 'title']) assert.equal(PluginSchema.parse({ ...plugin(), bannerTitle }).bannerTitle, bannerTitle);
});

test('Z03 actual Expo descriptor rejects invalid nested enum/min/type inputs', () => {
  const variants = [];
  for (const key of ['packageName', 'packageRoot']) { const input = plugin(); input[key] = ''; variants.push(input); }
  { const input = plugin(); input.bannerTitle = ''; variants.push(input); }
  { const input = plugin(); input.cliExtensions.commands = []; variants.push(input); }
  { const input = plugin(); input.cliExtensions.entryPoint = ''; variants.push(input); }
  { const input = plugin(); input.cliExtensions.commands[0].environments = ['invalid']; variants.push(input); }
  { const input = plugin(); input.cliExtensions.commands[0].parameters[0].type = 'invalid'; variants.push(input); }
  for (const input of variants) rejects(PluginSchema, input);
  const error = rejects(PluginSchema, { ...plugin(), packageName: '' });
  assert.deepEqual(error.issues[0].path, ['packageName']);
});

test('Z04 actual Expo output union accepts text/audio/image and optional fields', () => {
  assert.deepEqual(DevToolsPluginOutputSchema.parse(output), output);
  for (const level of ['info', 'warning', 'error']) assert.equal(DevToolsPluginOutputSchema.parse([{ type: 'text', text: '', level }])[0].level, level);
  assert.deepEqual(DevToolsPluginOutputSchema.parse([]), []);
  for (const type of ['audio', 'image']) rejects(DevToolsPluginOutputSchema, [{ type, url: 'invalid URL' }]);
  rejects(DevToolsPluginOutputSchema, [{ type: 'text', text: 'x', level: 'debug' }]);
  rejects(DevToolsPluginOutputSchema, [{ type: 'unknown', url: 'https://example.test' }]);
});

test('Z05 actual CLI result formatter preserves success/plain-text/error issue paths', () => {
  const notifications = [];
  const result = new DevToolsPluginCliExtensionResults(lines => notifications.push(lines));
  result.append(JSON.stringify(output));
  assert.deepEqual(result.getOutput(), output);
  assert.deepEqual(notifications, [output]);
  assert.deepEqual(result.parseOutputText('one\n\ntwo', 'warning'), [
    { type: 'text', text: 'one', level: 'warning' }, { type: 'text', text: 'two', level: 'warning' },
  ]);
  const invalid = [{ type: 'image', url: 'invalid URL' }];
  const expected = DevToolsPluginOutputSchema.safeParse(invalid);
  const error = result.parseOutputText(JSON.stringify(invalid));
  assert.equal(error[0].text, `Invalid JSON: ${expected.error.issues.map(issue => issue.message).join(', ')}`);
  assert.equal(error[0].level, 'error');
  result.exit(2);
  assert.equal(result.getOutput().at(-1).text, 'Process exited with code 2');
  assert.equal(result.isTruncated(), false);
});

test('Z06 actual dynamic MCP schema preserves enums/optional parameters/types/strictness', () => {
  const schema = createMCPDevToolsExtensionSchema(plugin());
  assert.deepEqual(schema.parse({ command: 'inspect', query: 'x', count: 2, confirmed: true }), { command: 'inspect', query: 'x', count: 2, confirmed: true });
  assert.deepEqual(schema.parse({ command: 'status' }), { command: 'status' });
  for (const input of [{ command: 'invalid' }, { command: 'status', extra: true },
    { command: 'inspect', query: 2 }, { command: 'inspect', count: '2' }, { command: 'inspect', confirmed: 'true' }]) rejects(schema, input);
  assert.match(schema.shape.query.description, /Query text.*Used by: "inspect"/);
  assert.throws(() => createMCPDevToolsExtensionSchema({ packageName: 'empty' }), /has no commands defined/);
});

test('Z07 native v4 JSON schema represents actual dynamic object boundary', () => {
  const schema = createMCPDevToolsExtensionSchema(plugin());
  const wrapped = z.object({ parameters: schema });
  const json = z.toJSONSchema(wrapped);
  assert.equal(json.properties.parameters.additionalProperties, false);
  assert.deepEqual(json.properties.parameters.properties.command.enum, ['inspect', 'status']);
  assert.equal(json.properties.parameters.properties.count.type, 'number');
  assert.deepEqual(json.properties.parameters.required, ['command']);
  assert.deepEqual(wrapped.parse({ parameters: { command: 'status' } }), { parameters: { command: 'status' } });
  // This is real Zod schema conversion, not an MCP SDK registration claim.
});

test('Z08 bounded synchronous collections reject before element validation', () => {
  for (const mode of ['array', 'nested']) {
    let visited = 0;
    const item = z.string().superRefine(() => { visited += 1; });
    const schema = mode === 'array' ? z.array(item).max(32) : z.object({ items: z.array(item).max(32) });
    const value = Array(33).fill('bounded value');
    const error = rejects(schema, mode === 'array' ? value : { items: value });
    assert.equal(visited, 0);
    assert.equal(error.issues.length, 1);
    assert.equal(error.issues[0].code, 'too_big');
    assert.deepEqual(error.issues[0].path, mode === 'array' ? [] : ['items']);
  }
});

test('Z09 bounded asynchronous collections reject before element validation', async () => {
  let visited = 0;
  const schema = z.array(z.string().superRefine(async () => { visited += 1; })).max(32);
  const result = await schema.safeParseAsync(Array(33).fill('bounded value'));
  assert.equal(result.success, false);
  assert.equal(result.error.issues.length, 1);
  assert.equal(result.error.issues[0].code, 'too_big');
  assert.equal(visited, 0);
  assert.deepEqual(await schema.parseAsync(['one', 'two']), ['one', 'two']);
  assert.equal(visited, 2);
});

test('Z10 actual Expo output array remains unbounded without an explicit maximum', () => {
  const error = rejects(DevToolsPluginOutputSchema, Array(64).fill({ type: 'unknown' }));
  assert.equal(error.issues.length, 64, 'Fixed v4 alone is not a universal issue-count cap');
  assert.equal(DevToolsPluginOutputSchema.parse(Array.from({ length: 64 }, () => output[0])).length, 64);
});
