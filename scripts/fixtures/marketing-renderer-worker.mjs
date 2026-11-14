import fs from 'node:fs';
import path from 'node:path';
import { syncBuiltinESMExports } from 'node:module';
import { pathToFileURL } from 'node:url';

// The test supplies an owned temporary root. No package JavaScript is loaded.
const [root, action, ...args] = process.argv.slice(2);
if (!root || !path.isAbsolute(root) || !['prepare', 'cli', 'fault-build'].includes(action)) {
  throw new Error('Expected an absolute fixture root and a reviewed worker action.');
}
const RealDate = Date;
globalThis.Date = class extends RealDate {
  constructor(...args) { super(...(args.length ? args : ['2026-01-01T00:00:00Z'])); }
  static now() { return new RealDate('2026-01-01T00:00:00Z').getTime(); }
};
if (action === 'fault-build') {
  const originalWrite = fs.writeFileSync;
  const output = path.join(root, 'dist');
  let writes = 0;
  fs.writeFileSync = function (file, ...args) {
    const relative = typeof file === 'string' ? path.relative(output, file) : '..';
    if (relative && !relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative)) {
      writes += 1;
      if (writes === 2) {
        process.stderr.write('Injected write failure after one successful owned output write.\n');
        throw Object.assign(new Error('Injected owned output failure'), { code: 'EIO' });
      }
    }
    return originalWrite.call(this, file, ...args);
  };
  syncBuiltinESMExports();
}
if (action !== 'prepare') {
  process.argv = [process.execPath, path.join(root, 'web/build.mjs'), ...args];
  await import(pathToFileURL(process.argv[1]));
} else {
  const { prepareBuild } = await import(pathToFileURL(path.join(root, 'web/build.mjs')));
  process.stdout.write(JSON.stringify([...prepareBuild()].map(([name, bytes]) => [name, bytes.toString('base64')])));
}
