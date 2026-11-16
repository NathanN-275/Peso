const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const { execFileSync } = require('node:child_process');
const { chromium } = require('@playwright/test');
const { resolveByteRange } = require('../../lib/httpRangePolicy');

// Runs the real exported Web App against synthetic, browser-local responses.
// Every other origin is blocked before dispatch. No accounts or media uploads.
async function main() {
  const root = path.resolve(process.env.PESO_UI_EXPORT || '/private/tmp/peso-web-ui-export');
  assert.ok(fs.existsSync(path.join(root, 'index.html')), 'Export the fixture Web App first');
  const media = fs.mkdtempSync(path.join(os.tmpdir(), 'peso-ui-media-'));
  execFileSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=180x320:rate=15', '-t', '4', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuv420p', path.join(media, 'portrait.webm')]);
  execFileSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=15', '-t', '4', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuv420p', path.join(media, 'landscape.webm')]);
  execFileSync('ffmpeg', ['-v', 'error', '-y', '-ss', '1', '-i', path.join(media, 'portrait.webm'), '-frames:v', '1', path.join(media, 'thumbnail.jpg')]);
  const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.jpg': 'image/jpeg', '.ttf': 'font/ttf', '.woff2': 'font/woff2', '.mp4': 'video/mp4', '.webm': 'video/webm' };
  const server = http.createServer((request, response) => {
    let pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
    let file = pathname.startsWith('/fixtures/') ? path.join(media, path.basename(pathname)) : path.join(root, pathname.replace(/^\/app(?=\/)/, ''));
    if (pathname.startsWith('/app/fonts/')) file = path.join(__dirname, '../../public/fonts', path.basename(pathname));
    if (!fs.existsSync(file) || !fs.statSync(file).isFile()) file = path.join(root, 'index.html');
    const size = fs.statSync(file).size, range = resolveByteRange(request.headers.range, size);
    const headers = { 'Content-Type': types[path.extname(file)] || 'application/octet-stream', 'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store', 'Content-Length': range ? range.end - range.start + 1 : size };
    if (range) headers['Content-Range'] = `bytes ${range.start}-${range.end}/${size}`;
    response.writeHead(range ? 206 : 200, headers);
    if (request.method === 'HEAD') response.end(); else fs.createReadStream(file, range || {}).pipe(response);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  const owner = '11111111-1111-4111-8111-111111111111', sessionId = '22222222-2222-4222-8222-222222222222';
  const one = '33333333-3333-4333-8333-333333333333', two = '44444444-4444-4444-8444-444444444444';
  const encode = value => Buffer.from(JSON.stringify(value)).toString('base64url');
  const token = `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode({ sub: owner, session_id: sessionId, iss: 'https://fixture.supabase.co/auth/v1', exp: Math.floor(Date.now() / 1000) + 3600, role: 'authenticated', aud: 'authenticated' })}.fixture`;
  const user = { id: owner, email: 'fixture@example.test', aud: 'authenticated', role: 'authenticated', app_metadata: { provider: 'email', providers: ['email'] }, user_metadata: {}, created_at: new Date().toISOString() };
  const makeActivity = (id, stage, age = 0) => {
    const time = new Date(Date.now() - age).toISOString();
    return { video_id: id, job_id: id, source_file_name: 'IMG_0013.MOV', exercise_type: 'squat', view_type: 'side', status: stage === 'ready' ? 'ready' : stage === 'failed' ? 'failed' : stage === 'queued' ? 'queued' : 'processing', stage, created_at: time, updated_at: time, stage_started_at: time, stage_timestamps: { queued: time, [stage]: time }, thumbnail_url: null, thumbnail_available: false, failure_class: stage === 'failed' ? 'analysis_runtime' : null, recovery_action: null };
  };
  let variant = 'portrait', mediaFailure = false;
  let items = [makeActivity(one, 'pose', 20000), makeActivity(two, 'queued', 10000)], activityCalls = 0;
  const browser = await chromium.launch({ executablePath: process.env.PESO_CHROMIUM || chromium.executablePath(), headless: true });
  const results = [];
  try {
    for (const width of [1280, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [], requests = [];
      variant = 'portrait'; mediaFailure = false;
      page.on('request', request => requests.push(request.url()));
      page.on('pageerror', error => errors.push(error.message));
      await page.addInitScript(({ token, user }) => localStorage.setItem('sb-fixture-auth-token', JSON.stringify({ access_token: token, refresh_token: 'fixture-refresh', token_type: 'bearer', expires_in: 3600, expires_at: Math.floor(Date.now() / 1000) + 3600, user })), { token, user });
      await page.route('**/*', async route => {
        const url = new URL(route.request().url());
        const json = body => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
        if (url.origin === 'https://fixture.supabase.co') return url.pathname === '/auth/v1/user' ? json(user) : route.abort();
        if (url.origin !== base && url.origin !== 'https://api.fixture.test') return route.abort();
        if (url.pathname === '/videos/analysis-activity') { activityCalls++; return json({ items, active_count: items.filter(x => ['queued', 'processing'].includes(x.status)).length, active_limit: 3 }); }
        if (url.pathname === '/private-media/session-acceptance') return json({ owner_id: owner, session_id: sessionId, accepted: true });
        if (url.pathname.includes('/private-media/session/')) {
          const root = `https://api.fixture.test/private-media/session/${sessionId}/video/${one}/`;
          if (url.pathname.endsWith('/session')) return route.fulfill({ status: 200, contentType: 'application/json', headers: { 'Cache-Control': 'private, no-store' }, body: JSON.stringify({ resource_kind: 'video', resource_id: one, expires_in: 300, expires_at: new Date(Date.now() + 299000).toISOString(), urls: Object.fromEntries(['export:barbell', 'export:clean', 'export:pose', 'export:pose-barbell', 'playback', 'thumbnail'].map(asset => [asset, root + encodeURIComponent(asset)])) }) });
          if (mediaFailure) return route.fulfill({ status: 503 });
          const thumbnail = url.pathname.endsWith('/thumbnail');
          const bytes = fs.readFileSync(path.join(media, thumbnail ? 'thumbnail.jpg' : `${variant}.webm`));
          const range = thumbnail ? null : resolveByteRange(route.request().headers().range, bytes.length);
          const body = range ? bytes.subarray(range.start, range.end + 1) : bytes;
          return route.fulfill({ status: range ? 206 : 200, headers: { 'Content-Type': thumbnail ? 'image/jpeg' : 'video/webm', 'Cache-Control': 'private, no-store', 'Content-Length': String(body.length), 'Accept-Ranges': 'bytes', ...(range ? { 'Content-Range': `bytes ${range.start}-${range.end}/${bytes.length}` } : {}) }, body });
        }
        if (url.pathname === '/videos/saved') return json([{ id: one, exercise_type: 'squat', view_type: 'side', performed_reps: 3, load_value: null, load_unit: null, storage_path: null, thumbnail_path: null, video_url: null, thumbnail_url: null, thumbnail_available: true, save_state: 'saved', storage_state: 'available', saved_at: user.created_at, created_at: user.created_at, analysis: null }]);
        if (url.pathname === '/profile') return json({ profile: { id: owner, username: null, display_name: 'Fixture', avatar_path: null, created_at: user.created_at, updated_at: user.created_at, profile_revision: sessionId }, avatar_available: false });
        if (url.pathname === `/analysis/${one}`) return json({ video_id: one, status: 'completed', result_json: { video_id: one, exercise: 'squat', duration: 4, videoWidth: variant === 'portrait' ? 180 : 320, videoHeight: variant === 'portrait' ? 320 : 180, processedVideoWidth: variant === 'portrait' ? 180 : 320, processedVideoHeight: variant === 'portrait' ? 320 : 180, trackingAssistance: { requestedMode: 'pins', actualMode: 'pin_assisted', used: true, reference: { version: 1, timeMs: 0, anchors: { shoulder: { x: 0.5, y: 0.25 }, hip: { x: 0.5, y: 0.5 }, knee: { x: 0.5, y: 0.7 }, ankle: { x: 0.5, y: 0.9 } } } }, poseFrames: [], reps: [], rep_count: 0, summaryFlags: [], coachingFeedback: [] } });
        if (url.pathname === `/videos/${one}/playback-url`) return json({ video_id: one, video_url: base + '/fixtures/portrait.webm', expires_in: 300 });
        return url.origin === base ? route.continue() : route.abort();
      });
      await page.goto(base + '/app');
      await page.getByRole('heading', { name: 'Home', exact: true }).waitFor({ timeout: 10000 }).catch(async error => { console.error(JSON.stringify({ requests, body: await page.locator('body').innerText(), errors })); throw error; });
      await page.getByText('IMG_0013.MOV', { exact: true }).first().waitFor({ timeout: 10000 }).catch(async error => { console.error(JSON.stringify({ requests, body: await page.locator('body').innerText(), errors })); throw error; });
      assert.equal(await page.getByText('IMG_0013.MOV', { exact: true }).count(), 2, 'both uploads have their own identity');
      await page.getByText('Tracking your movement', { exact: true }).waitFor();
      await page.getByText('Video queued', { exact: true }).waitFor();
      if (width > 767) {
        await page.getByRole('button', { name: 'Collapse sidebar' }).click();
        await page.getByLabel('Peso logo placeholder', { exact: true }).waitFor();
        await page.getByRole('button', { name: 'Expand sidebar' }).click();
      }
      await page.screenshot({ path: path.join(media, `home-${width}.png`) });
      const oldItems = items;
      const readyStarted = Date.now();
      items = [makeActivity(one, 'ready'), makeActivity(two, 'barbell_tracking')];
      await page.getByRole('button', { name: 'Review result', exact: true }).waitFor();
      assert.ok(Date.now() - readyStarted < 4500, 'readiness arrives within one poll interval plus local request time');
      await page.getByText('Tracking the barbell', { exact: true }).waitFor();
      items = oldItems;
      await page.goto(base + `/app/processing/${one}`);
      await page.getByText('IMG_0013.MOV', { exact: true }).waitFor();
      await page.getByLabel('Tracking movement: current', { exact: true }).waitFor();
      await page.goto(base + `/app/queued/${two}`);
      await page.getByRole('heading', { name: 'Video queued for analysis' }).waitFor();
      await page.getByRole('button', { name: 'Back to Home', exact: true }).click();
      assert.equal(new URL(page.url()).pathname.replace(/\/$/, ''), '/app');
      await page.getByRole('img', { name: 'Video preview', exact: true }).waitFor();
      const thumbnail = page.getByRole('img', { name: 'Video preview', exact: true });
      assert.ok((await thumbnail.evaluate(node => node.getAttribute('src') || node.querySelector('img')?.src || '')).startsWith('data:image/jpeg;base64,'), 'genuine private frame, no demo asset');
      await page.getByRole('link', { name: 'Saved Lifts', exact: true }).click();
      await page.getByRole('radio', { name: 'Grid View', exact: true }).click();
      await page.getByRole('img', { name: 'Video preview', exact: true }).waitFor();
      await page.goto(base + `/app/review/${one}`);
      const play = page.getByRole('button', { name: 'Play video', exact: true });
      await play.waitFor({ timeout: 10000 }).catch(async error => { console.error(JSON.stringify({ requests, body: await page.locator('body').innerText(), errors })); throw error; }); await play.click();
      await page.waitForFunction(() => document.querySelector('video')?.currentTime > 0.2);
      await page.getByRole('button', { name: 'Pause video', exact: true }).click();
      const paused = await page.locator('video').evaluate(video => video.paused); assert.equal(paused, true);
      const slider = page.getByRole('slider', { name: 'Video position' });
      await slider.focus(); await page.keyboard.press('End');
      await page.waitForFunction(() => document.querySelector('video')?.currentTime >= 3.8, { }, { timeout: 10000 }).catch(async error => { console.error(await page.locator('video').evaluate(v => ({ time: v.currentTime, duration: v.duration, error: v.error?.message, paused: v.paused, seekable: Array.from({length:v.seekable.length}, (_,i) => [v.seekable.start(i),v.seekable.end(i)]) }))); throw error; });
      await page.keyboard.press('Home');
      await page.waitForFunction(() => document.querySelector('video')?.currentTime < 0.1);
      const geometry = await page.locator('video').evaluate(video => {
        const rect = video.getBoundingClientRect(); return { x: rect.x, y: rect.y, width: rect.width, height: rect.height, fit: getComputedStyle(video).objectFit, naturalWidth: video.videoWidth, naturalHeight: video.videoHeight };
      });
      assert.equal(geometry.fit, 'contain'); assert.equal(geometry.naturalWidth, 180); assert.equal(geometry.naturalHeight, 320);
      const controls = await slider.boundingBox(); assert.ok(controls.y + controls.height <= 900, 'seek controls fit the viewport');
      assert.ok(geometry.y >= 0 && geometry.y + geometry.height <= controls.y, 'video stays above its controls');
      await page.getByText('Upper Back', { exact: true }).waitFor();
      const pin = await page.getByText('+', { exact: true }).first().locator('..').boundingBox();
      const scale = Math.min(geometry.width / 180, geometry.height / 320);
      const fitTop = geometry.y + (geometry.height - 320 * scale) / 2;
      assert.ok(Math.abs(pin.x + pin.width / 2 - (geometry.x + geometry.width / 2)) < 1, 'reference x uses the fitted video rectangle');
      assert.ok(Math.abs(pin.y + pin.height / 2 - (fitTop + 320 * scale * 0.25)) < 1, 'reference y uses the fitted video rectangle');
      await page.screenshot({ path: path.join(media, `review-${width}.png`) });
      variant = 'landscape';
      await page.reload();
      await page.getByRole('button', { name: 'Play video', exact: true }).click();
      await page.waitForFunction(() => document.querySelector('video')?.currentTime > 0.2);
      await page.getByRole('button', { name: 'Pause video', exact: true }).click();
      assert.equal(await page.locator('video').evaluate(video => video.videoWidth), 320);
      assert.equal(await page.locator('video').evaluate(video => video.videoHeight), 180);
      await page.screenshot({ path: path.join(media, `landscape-${width}.png`) });
      if (width === 390) {
        await page.setViewportSize({ width: 844, height: 390 });
        const shortControls = page.getByRole('slider', { name: 'Video position' });
        await shortControls.scrollIntoViewIfNeeded();
        const shortBox = await shortControls.boundingBox();
        assert.ok(shortBox.y >= 0 && shortBox.y + shortBox.height <= 390, 'short landscape viewport can reach the seek control');
      }
      const detachedVideo = await page.locator('video').elementHandle();
      await page.getByRole('link', { name: 'Home', exact: true }).click();
      await page.getByRole('heading', { name: 'Home', exact: true }).waitFor();
      assert.equal(await detachedVideo.getAttribute('src'), null, 'navigation removes the detached private source');
      mediaFailure = true;
      await page.goto(base + `/app/review/${one}`);
      await page.getByText('Video could not load', { exact: true }).waitFor();
      assert.ok(!(await page.locator('body').innerText()).includes('expired'), 'failed fetch must not claim media expiry');
      await page.getByRole('link', { name: 'Home', exact: true }).click();
      await page.getByRole('button', { name: 'Retry video preview', exact: true }).waitFor();
      assert.equal(await page.getByRole('img', { name: 'Video preview', exact: true }).count(), 0, 'failed frame fetch shows no demo image');
      assert.deepEqual(errors, []);
      results.push({ width, individualLifts: 'passed', queueConfirmation: 'passed', playback: 'passed', keyboardSeek: 'passed', geometry });
      await page.close();
    }
    const login = await browser.newPage();
    await login.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
    await login.goto(base + '/app/login');
    const password = login.getByLabel('Password', { exact: true });
    await password.fill('synthetic-check');
    assert.equal(await password.evaluate(input => input.type), 'password');
    const eye = login.getByRole('button', { name: 'Show password', exact: true });
    const eyeBox = await eye.boundingBox(); assert.ok(eyeBox.width >= 44 && eyeBox.height >= 44);
    await eye.click(); assert.equal(await password.evaluate(input => input.type), 'text');
    await login.getByRole('button', { name: 'Hide password', exact: true }).click();
    assert.equal(await password.evaluate(input => input.type), 'password');
    await login.close();
    console.log(JSON.stringify({ results, activityCalls, passwordToggle: 'passed', screenshots: media }));
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
