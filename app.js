(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const form = $("checkForm");
  const input = $("message");
  const btn = $("checkBtn");
  const counter = $("counter");
  const clearBtn = $("clearBtn");
  const pasteBtn = $("pasteBtn");
  const errorBox = $("error");
  const result = $("result");
  const MAX = 10000;
  const ARC = 251.33; // длина дуги шкалы (π·80)
  let lastResult = null;

  const EXAMPLES = [
    {
      label: "«Служба безопасности банка»",
      text: "Уважаемый клиент! По вашей карте зафиксирована подозрительная операция на 48 900 ₽. Карта будет заблокирована в течение 30 минут. Для отмены операции продиктуйте код из SMS сотруднику службы безопасности банка. Никому не сообщайте об этом звонке.",
    },
    {
      label: "«Мама, это я»",
      text: "Мама, это я, у меня новый номер. Попал в аварию, срочно переведи 15000 на эту карту 2202 2063 1234 5678, потом всё объясню, не могу говорить",
    },
    {
      label: "Выигрыш приза",
      text: "Поздравляем! Вы выиграли iPhone 17 в розыгрыше Ozon! Чтобы получить приз, оплатите доставку 299 руб. до конца дня по ссылке: ozon-prize.xyz/get",
    },
    {
      label: "Посылка на почте",
      text: "Ваша посылка задержана на складе. Подтвердите адрес доставки: http://pochta-ru.delivery-track.top/lk",
    },
    {
      label: "«Безопасный счёт»",
      text: "Говорит следователь ФСБ. На ваше имя пытаются оформить кредит. Срочно переведите все сбережения на безопасный счёт Центробанка. Это тайна следствия, не говорите родным.",
    },
    {
      label: "Обычное сообщение",
      text: "Привет! Встречаемся завтра в 18:00 у кафе, не забудь книгу. Вот адрес на карте: https://yandex.ru/maps",
    },
  ];

  /* ---------- тема ---------- */
  const root = document.documentElement;
  try {
    const saved = localStorage.getItem("shield-theme");
    if (saved === "dark" || saved === "light") root.dataset.theme = saved;
  } catch (_) { /* хранилище недоступно */ }
  $("themeToggle").addEventListener("click", () => {
    const isDark = root.dataset.theme
      ? root.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = isDark ? "light" : "dark";
    try { localStorage.setItem("shield-theme", root.dataset.theme); } catch (_) {}
  });

  /* ---------- поле ввода ---------- */
  const fmt = (n) => n.toLocaleString("ru-RU");
  function syncInput() {
    const len = input.value.length;
    counter.textContent = `${fmt(len)} / ${fmt(MAX)}`;
    btn.disabled = input.value.trim().length === 0;
    clearBtn.hidden = len === 0;
    pasteBtn.hidden = len > 0;
  }
  input.addEventListener("input", () => { hideError(); syncInput(); });
  input.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") form.requestSubmit();
  });

  clearBtn.addEventListener("click", () => {
    input.value = "";
    syncInput();
    input.focus();
  });

  pasteBtn.addEventListener("click", async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        input.value = text.slice(0, MAX);
        syncInput();
      } else {
        showError("Буфер обмена пуст. Скопируйте сообщение и попробуйте ещё раз.");
      }
    } catch (_) {
      input.focus();
      showError("Не удалось прочитать буфер обмена. Нажмите и удерживайте поле, затем выберите «Вставить».");
    }
  });

  const chips = $("examples");
  EXAMPLES.forEach((ex) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.textContent = ex.label;
    b.addEventListener("click", () => {
      input.value = ex.text;
      syncInput();
      hideError();
      form.requestSubmit();
    });
    chips.appendChild(b);
  });

  function showError(msg) { errorBox.textContent = msg; errorBox.hidden = false; }
  function hideError() { errorBox.hidden = true; }

  /* ---------- проверка ---------- */
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    hideError();
    btn.classList.add("loading");
    btn.disabled = true;
    btn.querySelector(".btn-label").textContent = "Проверяем";
    const originalText = text;
    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, use_ai: $("useAI").checked }),
      });
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();
      render(data, originalText);
    } catch (err) {
      showError("Не удалось выполнить проверку. Проверьте подключение к интернету и попробуйте снова.");
    } finally {
      btn.classList.remove("loading");
      btn.querySelector(".btn-label").textContent = "Проверить";
      syncInput();
    }
  });

  $("shareBtn").addEventListener("click", async () => {
    if (!lastResult) return;
    const d = lastResult;
    const topSigns = (d.signs || []).filter(s => s.score >= 10).slice(0, 3).map(s => "• " + s.title);
    const shareText = [
      "Антимошенник — результат проверки",
      d.label + ": " + d.verdict,
      topSigns.length ? "\nНайдены признаки:\n" + topSigns.join("\n") : "\nЯвных признаков мошенничества не найдено.",
      "\nПроверь, прежде чем поверить."
    ].join("\n");
    try {
      if (navigator.share) {
        await navigator.share({ title: "Антимошенник", text: shareText, url: location.origin });
      } else {
        await navigator.clipboard.writeText(shareText + "\n" + location.origin);
        $("shareBtn").textContent = "Скопировано";
        setTimeout(() => $("shareBtn").textContent = "Поделиться результатом", 1600);
      }
    } catch (_) {}
  });

  $("againBtn").addEventListener("click", () => {
    result.hidden = true;
    input.value = "";
    syncInput();
    window.scrollTo({ top: 0, behavior: "smooth" });
    setTimeout(() => input.focus(), 300);
  });

  /* ---------- вывод результата ---------- */
  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function pluralSigns(n) {
    const m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return "признак";
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "признака";
    return "признаков";
  }

  function render(data, originalText) {
    lastResult = data;
    result.hidden = false;
    const ai = data.ai;
    $("aiCard").hidden = !ai;
    $("aiSigns").replaceChildren();
    $("aiAdvice").replaceChildren();
    if (ai) {
      const labels = {low: "Низкий", medium: "Средний", high: "Высокий", critical: "Критический"};
      $("aiSummary").textContent = ai.status === "ok"
        ? `${labels[ai.risk]} риск по оценке ИИ. ${ai.explanation}` : ai.message;
      (ai.signs || []).forEach(s => $("aiSigns").append(el("li", null, s)));
      (ai.recommendations || []).forEach(s => $("aiAdvice").append(el("li", null, s)));
    }
    // перезапуск анимации появления
    result.style.animation = "none"; void result.offsetWidth; result.style.animation = "";

    const card = $("scoreCard");
    card.dataset.level = data.level;
    $("levelBadge").textContent = data.label;
    $("verdictText").textContent = data.verdict;
    animateGauge(data.score);

    // признаки
    const list = $("signs");
    list.replaceChildren();
    const signs = data.signs || [];
    $("signsCount").textContent = signs.length;
    $("signsCount").setAttribute("aria-label", `${signs.length} ${pluralSigns(signs.length)}`);
    $("noSigns").hidden = signs.length > 0;
    signs.forEach((s) => {
      const li = el("li", "sign");
      li.dataset.sev = s.score >= 40 ? "high" : s.score >= 20 ? "mid" : "low";
      const head = el("div", "sign-head");
      head.append(el("span", "sign-icon", s.icon), el("span", "sign-title", s.title), el("span", "sign-score", `+${s.score}`));
      li.append(head, el("p", null, s.explanation));
      if (s.fragments && s.fragments.length) {
        const fr = el("div", "frags");
        s.fragments.forEach((f) => fr.append(el("span", "frag", `«${f.length > 70 ? f.slice(0, 70) + "…" : f}»`)));
        li.append(fr);
      }
      if (s.details && s.details.length) {
        const ul = el("ul", "details");
        s.details.forEach((d) => ul.append(el("li", null, d)));
        li.append(ul);
      }
      list.append(li);
    });

    // рекомендации
    const adv = $("advice");
    adv.replaceChildren();
    (data.recommendations || []).forEach((r) => adv.append(el("li", null, r)));

    // подсветка
    const hl = $("highlighted");
    hl.replaceChildren();
    const spans = data.highlights || [];
    $("highlightCard").hidden = spans.length === 0;
    let pos = 0;
    // сервер получил trim()-текст; позиции в Python считаются по символам Unicode,
    // поэтому режем массив кодовых точек, а не UTF-16 строку (важно для эмодзи)
    const cps = Array.from(originalText.trim());
    const cut = (a, b) => cps.slice(a, b).join("");
    spans.forEach((sp) => {
      if (sp.start > pos) hl.append(document.createTextNode(cut(pos, sp.start)));
      hl.append(el("mark", null, cut(sp.start, sp.end)));
      pos = sp.end;
    });
    if (pos < cps.length) hl.append(document.createTextNode(cut(pos)));

    requestAnimationFrame(() => result.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  function animateGauge(score) {
    const fill = $("gaugeFill");
    const dot = $("gaugeDot");
    const value = $("scoreValue");
    const place = (v) => {
      const a = Math.PI * (1 - v / 100); // угол от 180° до 0°
      dot.setAttribute("cx", (100 + 80 * Math.cos(a)).toFixed(2));
      dot.setAttribute("cy", (100 - 80 * Math.sin(a)).toFixed(2));
      fill.style.strokeDashoffset = ARC * (1 - v / 100);
      value.textContent = Math.round(v);
    };
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) { place(score); return; }
    place(0);
    const t0 = performance.now(), dur = 1100;
    const step = (t) => {
      const k = Math.min(1, (t - t0) / dur);
      place(score * (1 - Math.pow(1 - k, 3)));
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  syncInput();
})();
