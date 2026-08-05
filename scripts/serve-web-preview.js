const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const distRoot = path.resolve(__dirname, '..', 'dist');
const port = Number.parseInt(process.env.PORT ?? '4173', 10);

const contentTypes = {
  '.css': 'text/css; charset=utf-8',
  '.gif': 'image/gif',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.jpg': 'image/jpeg',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.mp4': 'video/mp4',
  '.png': 'image/png',
  '.ttf': 'font/ttf',
  '.vtt': 'text/vtt; charset=utf-8',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

function resolveRequestPath(requestUrl) {
  const pathname = decodeURIComponent(new URL(requestUrl, 'http://localhost').pathname);
  const relativePath = pathname.replace(/^\/+/, '');
  const candidate = path.resolve(distRoot, relativePath);

  if (!candidate.startsWith(`${distRoot}${path.sep}`) && candidate !== distRoot) {
    return null;
  }

  if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
    return candidate;
  }

  const indexPath = path.join(candidate, 'index.html');
  if (fs.existsSync(indexPath)) {
    return indexPath;
  }

  if (pathname === '/app' || pathname.startsWith('/app/')) {
    return path.join(distRoot, 'app', 'index.html');
  }

  return null;
}

http
  .createServer((request, response) => {
    const filePath = resolveRequestPath(request.url ?? '/');
    if (!filePath) {
      response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end('Not found');
      return;
    }

    response.writeHead(200, {
      'Cache-Control': 'no-store',
      'Content-Type': contentTypes[path.extname(filePath)] ?? 'application/octet-stream',
    });
    fs.createReadStream(filePath).pipe(response);
  })
  .listen(port, '127.0.0.1', () => {
    console.log(`Peso web preview: http://127.0.0.1:${port}`);
  });
