const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const root = path.join(__dirname, '..');
const appRoot = path.join(root, 'dist', 'app');
const htmlPath = path.join(appRoot, 'index.html');
const maxJavaScriptBytes = 600 * 1024;
const maxFontBytes = 200 * 1024;

if (!fs.existsSync(htmlPath)) {
  throw new Error('dist/app/index.html is missing. Run npm run web:build first.');
}

const html = fs.readFileSync(htmlPath, 'utf8');
const scriptSources = [...html.matchAll(/<script[^>]+src=["']([^"']+)["']/g)]
  .map((match) => match[1]);

if (scriptSources.length === 0) {
  throw new Error('No startup JavaScript was found in dist/app/index.html.');
}

const startupJavaScript = scriptSources.map((source) => {
  const relativePath = source.replace(/^\/app\//, '').replace(/^\.\//, '');
  const filePath = path.join(appRoot, relativePath);
  if (!fs.existsSync(filePath)) throw new Error(`Startup asset is missing: ${source}`);
  return {
    source,
    gzipBytes: zlib.gzipSync(fs.readFileSync(filePath), { level: 9 }).byteLength,
  };
});

const fontRoot = path.join(appRoot, 'fonts');
const fontFiles = fs.existsSync(fontRoot)
  ? fs.readdirSync(fontRoot).filter((name) => name.endsWith('.woff2'))
  : [];
const fontBytes = fontFiles.reduce(
  (total, name) => total + fs.statSync(path.join(fontRoot, name)).size,
  0
);
const javascriptBytes = startupJavaScript.reduce((total, asset) => total + asset.gzipBytes, 0);

console.log(JSON.stringify({
  startupJavaScript,
  startupJavaScriptGzipBytes: javascriptBytes,
  woff2Files: fontFiles,
  woff2Bytes: fontBytes,
  limits: { startupJavaScriptGzipBytes: maxJavaScriptBytes, woff2Bytes: maxFontBytes },
}, null, 2));

if (javascriptBytes > maxJavaScriptBytes) {
  throw new Error(`Startup JavaScript is ${javascriptBytes} bytes; limit is ${maxJavaScriptBytes}.`);
}
if (fontBytes > maxFontBytes) {
  throw new Error(`Startup fonts are ${fontBytes} bytes; limit is ${maxFontBytes}.`);
}
