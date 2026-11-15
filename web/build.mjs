import { createHash } from 'node:crypto';
import { lstatSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { betaAvailable, betaHref, betaLabel } from './src/scripts/beta-entry.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(root, 'dist');
const publicFiles = [
  'og.png', 'robots.txt', 'peso-logo.png', 'favicon.png',
  'demo/peso-demo-thumbnail.jpg', 'demo/peso-pose-overlay.jpg',
  'demo/peso-demo-captions.vtt', 'demo/peso-pin-assisted-bar-path.jpg',
  'auth/turnstile.css', 'auth/turnstile.js',
];
const fonts = [
  ['archivo-black', '400'], ['inter', '400'], ['inter', '500'],
  ['inter', '600'], ['inter', '700'],
];
const pages = [
  { file: 'index', route: '/', title: 'Peso — Improve each set with focused squat coaching',
    description: 'Peso turns a side-view squat video into visible rep analysis and focused coaching cues for your next set. '
      + (betaAvailable ? 'Join the side-view squat beta.' : 'Side-view squat beta coming soon.') },
  { file: 'beta', route: '/beta/', title: 'Beta coming soon — Peso',
    description: 'Peso’s side-view squat analysis beta is not open yet. Explore the preview while we prepare for launch.' },
  { file: 'privacy', route: '/privacy/', title: 'Privacy — Peso',
    description: 'Read the draft privacy information for Peso’s limited US web beta.' },
  { file: 'terms', route: '/terms/', title: 'Terms — Peso',
    description: 'Read the draft terms for Peso’s limited US web beta.' },
];

function relativePath(name) {
  if (!name || name.includes('\\') || path.posix.isAbsolute(name)
      || name.split('/').some(part => !part || part === '.' || part === '..')) {
    throw new Error(`Invalid local path: ${name}`);
  }
  return name;
}

function checkedPath(name, missingAllowed = false) {
  let current = root;
  if (lstatSync(current).isSymbolicLink()) throw new Error('Project root must not be a symlink.');
  for (const part of relativePath(name).split('/')) {
    current = path.join(current, part);
    try {
      if (lstatSync(current).isSymbolicLink()) throw new Error(`Symlink is not allowed: ${name}`);
    } catch (error) {
      if (missingAllowed && error.code === 'ENOENT') return current;
      throw error;
    }
  }
  return current;
}

function readInput(name) {
  const file = checkedPath(name);
  if (!lstatSync(file).isFile()) throw new Error(`Expected a regular file: ${name}`);
  return readFileSync(file);
}

function escapeHtml(value) {
  const escapes = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  return String(value).replace(/[&<>"']/g, character => escapes[character]);
}

function template(name, values) {
  const text = readInput(`web/src/${name}.html`).toString('utf8');
  const marker = /\{\{([A-Z_]+)\}\}/g;
  if (/\{\{|\}\}/.test(text.replace(marker, ''))) {
    throw new Error(`Malformed template marker: ${name}`);
  }
  // Values are explicit escaped text or trusted fragments; never evaluate templates.
  return text.replace(marker, (_, key) => {
    if (!Object.hasOwn(values, key)) throw new Error(`Unknown template marker ${key}: ${name}`);
    return values[key];
  });
}

function siteUrl() {
  const value = process.env.DEPLOY_PRIME_URL || process.env.URL;
  if (!value) return undefined;
  const site = new URL(value);
  if (!['https:', 'http:'].includes(site.protocol) || site.username || site.password) {
    throw new Error('The deployment URL must be an HTTP(S) URL without credentials.');
  }
  return site;
}

export function prepareBuild() {
  const mode = process.env.PESO_WEB_BUILD ?? 'marketing';
  if (!['marketing', 'private-beta'].includes(mode)) throw new Error('Unknown marketing build mode.');
  const site = siteUrl();
  const files = new Map();
  function add(name, content) {
    relativePath(name);
    const bytes = Buffer.isBuffer(content) ? content : Buffer.from(content);
    if (files.has(name) && !files.get(name).equals(bytes)) throw new Error(`Output collision: ${name}`);
    files.set(name, bytes);
  }
  function asset(name, content) {
    const bytes = Buffer.isBuffer(content) ? content : Buffer.from(content);
    const extension = path.posix.extname(name);
    const digest = createHash('sha256').update(bytes).digest('hex');
    const file = `marketing-assets/${path.posix.basename(name, extension)}.${digest}${extension}`;
    add(file, bytes);
    return `/${file}`;
  }

  for (const name of publicFiles) add(name, readInput(`web/public/${name}`));
  const fontStyles = [];
  for (const [family, weight] of fonts) {
    const packageRoot = `web/node_modules/@fontsource/${family}`;
    const manifest = JSON.parse(readInput(`${packageRoot}/package.json`).toString('utf8'));
    if (manifest.name !== `@fontsource/${family}` || manifest.version !== '5.3.0') {
      throw new Error(`Expected reviewed @fontsource/${family} 5.3.0.`);
    }
    let css = readInput(`${packageRoot}/latin-${weight}.css`).toString('utf8');
    for (const extension of ['woff2', 'woff']) {
      const name = `${family}-latin-${weight}-normal.${extension}`;
      const from = `url(./files/${name})`;
      if (css.split(from).length !== 2) throw new Error(`Unexpected font stylesheet: ${family}/${weight}`);
      css = css.replace(from, `url(${asset(name, readInput(`${packageRoot}/files/${name}`))})`);
    }
    const urls = [...css.matchAll(/url\(([^)]+)\)/g)].map(match => match[1]);
    if (urls.length !== 2 || urls.some(url => !url.startsWith('/') || !files.has(url.slice(1)))
        || /@import\b/i.test(css)) throw new Error(`Unmapped font resource: ${family}/${weight}`);
    fontStyles.push(css);
  }
  const licenses = ['archivo-black', 'inter'].map(family =>
    `@fontsource/${family}\n${readInput(`web/node_modules/@fontsource/${family}/LICENSE`).toString('utf8')}`);
  asset('font-licenses.txt', licenses.join('\n\n'));
  const stylesheet = asset('site.css', [
    ...fontStyles, readInput('web/src/styles/global.css').toString('utf8'),
  ].join('\n'));
  const video = asset('peso-pose-overlay.mp4', readInput('assets/demo/peso-pose-overlay.mp4'));
  const demoScript = asset('demo-video.js', readInput('web/src/scripts/demo-video.js'));
  const shared = { BETA_HREF: escapeHtml(betaHref), BETA_LABEL: escapeHtml(betaLabel) };
  const footer = template('components/site-footer', {
    ...shared, YEAR: String(new Date().getFullYear()),
    BETA_STATUS: betaAvailable ? 'Public web beta.' : 'Beta coming soon.',
  });
  for (const page of pages) {
    const header = template('components/site-header', {
      ...shared, COMPACT_CLASS: page.file === 'index' ? '' : ' site-header--compact',
    });
    const body = template(`pages/${page.file}`, {
      ...shared, HEADER: header, FOOTER: footer,
      BETA_AVAILABILITY: betaAvailable
        ? 'Signup for the web beta requires a US IP address and email verification. Signed-in users can upload side-view squat videos for private analysis, including while abroad.'
        : 'This public website is an informational preview only. Signup, uploads, analysis, and email collection are unavailable. The draft below describes the future beta, not services currently offered on this site.',
      BETA_EYEBROW: betaAvailable ? 'Public web beta' : 'Beta coming soon',
      BETA_TRUST: betaAvailable ? 'Side-view squats · US-IP signup'
        : 'Side-view squats · Preview only · Analysis is not open yet',
      BETA_CTA: betaAvailable
        ? 'Create an account to upload a side-view squat video and review your analysis.'
        : 'The side-view squat beta is not open yet. This site previews the experience; signup, uploads, and analysis are unavailable.',
      DEMO_VIDEO_URL: escapeHtml(video), DEMO_SCRIPT_URL: escapeHtml(demoScript),
    });
    const metadata = site ? [
      `<link rel="canonical" href="${escapeHtml(new URL(page.route, site).href)}" />`,
      `<meta property="og:url" content="${escapeHtml(new URL(page.route, site).href)}" />`,
      `<meta property="og:image" content="${escapeHtml(new URL('/og.png', site).href)}" />`,
      `<meta name="twitter:image" content="${escapeHtml(new URL('/og.png', site).href)}" />`,
    ].join('\n    ') : '';
    const html = template('layouts/base-layout', {
      TITLE: escapeHtml(page.title), DESCRIPTION: escapeHtml(page.description),
      METADATA: metadata, STYLESHEET_URL: escapeHtml(stylesheet), BODY: body,
    });
    add(page.file === 'index' ? 'index.html' : `${page.file}/index.html`, html);
  }
  add('auth/turnstile/index.html', template('pages/auth/turnstile', {
    SITE_KEY: escapeHtml(process.env.EXPO_PUBLIC_TURNSTILE_SITE_KEY?.trim() ?? ''),
  }));
  return files;
}

function clearOutput() {
  checkedPath('dist', true);
  rmSync(output, { recursive: true, force: true });
}

function main() {
  const args = process.argv.slice(2);
  if (args.length > 1 || (args[0] && args[0] !== '--check')) throw new Error('Usage: node build.mjs [--check]');
  if (args[0] === '--check') {
    const files = prepareBuild();
    console.log(`Marketing inputs validated: five pages, ${files.size} planned files; no files written.`);
    return;
  }
  try {
    const files = prepareBuild();
    clearOutput();
    mkdirSync(output);
    for (const [name, content] of files) {
      const file = path.join(output, name);
      mkdirSync(path.dirname(file), { recursive: true });
      writeFileSync(file, content, { flag: 'wx' });
    }
    console.log(`Marketing pages written: ${files.size} files.`);
  } catch (error) {
    clearOutput();
    throw error;
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
