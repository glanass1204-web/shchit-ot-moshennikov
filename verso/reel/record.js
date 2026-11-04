// Записывает вертикальный ролик 1080×1920 с анимацией входа/регистрации.
// Запуск из корня репозитория:  node verso/reel/record.js  → verso/reel/out/reel.mp4
// Нужны: playwright (Chromium) и ffmpeg.
const { chromium } = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..');            // папка verso/
const OUT = path.join(__dirname, 'out');
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css' };

function serve() {
  const server = http.createServer((req, res) => {
    const file = path.join(ROOT, decodeURIComponent(new URL(req.url, 'http://x').pathname));
    if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream' });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise(r => server.listen(0, '127.0.0.1', () => r(server)));
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const server = await serve();
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || '/opt/pw-browsers/chromium' });
  const context = await browser.newContext({
    viewport: { width: 1080, height: 1920 },
    recordVideo: { dir: OUT, size: { width: 1080, height: 1920 } },
  });
  const page = await context.newPage();
  const t0 = Date.now();
  await page.goto(`${base}/reel/reel.html`);
  const frame = page.frame({ url: /index\.html/ });
  await frame.waitForLoadState('networkidle');
  await page.evaluate(() => document.fonts.ready);
  const startOffset = (Date.now() - t0) / 1000;        // всё до этого момента обрежем

  // Курсор, которым «водим» по странице.
  await frame.evaluate(() => {
    const c = document.createElement('div');
    c.id = 'cursor';
    c.innerHTML = '<svg width="34" height="34" viewBox="0 0 24 24"><path d="M4 2l15 11-7 1.2L8.5 21z" fill="#fff" stroke="#0a1a17" stroke-width="1.4" stroke-linejoin="round"/></svg>';
    Object.assign(c.style, { position: 'fixed', left: '0', top: '0', zIndex: 99, pointerEvents: 'none',
      transform: 'translate(760px, 900px)', filter: 'drop-shadow(0 3px 6px rgba(0,0,0,.45))' });
    document.body.appendChild(c);
    window.__cur = { x: 760, y: 900 };
  });

  async function moveTo(selector, ms = 700) {
    await frame.evaluate(([sel, ms]) => {
      const r = document.querySelector(sel).getBoundingClientRect();
      const to = { x: r.left + Math.min(r.width * .5, 140), y: r.top + r.height * .6 };
      const c = document.getElementById('cursor');
      c.animate([{ transform: `translate(${__cur.x}px, ${__cur.y}px)` }, { transform: `translate(${to.x}px, ${to.y}px)` }],
        { duration: ms, easing: 'cubic-bezier(.6,0,.2,1)', fill: 'forwards' });
      window.__cur = to;
    }, [selector, ms]);
    await sleep(ms + 80);
  }
  async function click(selector) {
    await moveTo(selector);
    await frame.evaluate(() => document.getElementById('cursor').animate(
      [{ scale: 1 }, { scale: .82 }, { scale: 1 }], { duration: 220 }));
    await frame.click(selector);
  }
  async function type(selector, text) {
    await click(selector);
    await frame.type(selector, text, { delay: 55 });
  }
  const hl = ids => page.evaluate(ids => window.hl(ids), ids);

  // ---- Сценарий ----
  await sleep(1400);
  await hl(['h1', 'h3']);
  await type('#si-login', 'anna.petrova');
  await sleep(300);
  await hl(['j1', 'j2']);
  await click('#pane-signin .note .link');                 // «Создать аккаунт» — лезвие уходит влево
  await sleep(300); await hl(['c1', 'c2', 'j3']);
  await sleep(500); await hl(['j4']);
  await sleep(900); await hl(['c3', 'c4', 'h4']);

  await type('#su-name', 'Анна Петрова');
  await type('#su-email', 'anna@mail.ru');
  await type('#su-pass', 'Zaщita-2026!');
  await sleep(500);
  await click('#form-signup .btn');
  await sleep(2200);

  await hl(['j1', 'j2']);
  await click('#pane-signup .note .link');                 // «Войти» — лезвие возвращается вправо
  await sleep(300); await hl(['c1', 'c2', 'j3']);
  await sleep(500); await hl(['j4']);
  await sleep(1100); await hl(['h1', 'h2', 'h3']);
  await moveTo('.switch [data-go="signup"]', 900);
  await sleep(600);
  await click('.switch [data-go="signup"]');               // ещё один проход через переключатель
  await sleep(1700);
  await click('.switch [data-go="signin"]');
  await sleep(2200);

  const video = page.video();
  await context.close();
  await browser.close();
  server.close();

  const raw = await video.path();
  const mp4 = path.join(OUT, 'reel.mp4');
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-ss', String(startOffset + 0.2), '-i', raw,
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '20', '-pix_fmt', 'yuv420p', '-r', '30', '-movflags', '+faststart', mp4]);
  fs.unlinkSync(raw);
  console.log('Готово:', mp4);
})();
