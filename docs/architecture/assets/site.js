(function () {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function enableRevealMotion() {
    const targets = document.querySelectorAll(
      '[data-reveal], .hero--compact .shell, .section > .shell, .diagram'
    );
    if (!targets.length || reduceMotion || !('IntersectionObserver' in window)) return;

    document.documentElement.classList.add('reveal-ready');
    targets.forEach((target) => target.classList.add('reveal'));

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.08 }
    );

    targets.forEach((target) => observer.observe(target));
  }

  enableRevealMotion();

  function matchDemoCardHeight() {
    const compactLayout = window.matchMedia('(max-width: 780px)');

    document.querySelectorAll('[data-match-height]').forEach((layout) => {
      const source = layout.querySelector('[data-height-source]');
      const target = layout.querySelector('[data-height-target]');
      const targetCopy = target?.querySelector('.demo-card__copy');
      if (!source || !target || !targetCopy) return;

      const update = () => {
        if (compactLayout.matches) {
          target.style.removeProperty('--matched-demo-height');
          target.style.removeProperty('--matched-demo-width');
          return;
        }

        const targetHeight = Math.ceil(source.getBoundingClientRect().height);
        target.style.setProperty('--matched-demo-height', `${targetHeight}px`);

        let targetWidth = Math.min(260, Math.max(160, targetHeight * 0.34));
        for (let pass = 0; pass < 3; pass += 1) {
          target.style.setProperty('--matched-demo-width', `${targetWidth}px`);
          const copyHeight = Math.ceil(targetCopy.getBoundingClientRect().height);
          targetWidth = Math.max(160, (targetHeight - copyHeight) * (360 / 874));
        }
        target.style.setProperty('--matched-demo-width', `${Math.round(targetWidth)}px`);
      };

      update();
      compactLayout.addEventListener('change', update);
      if ('ResizeObserver' in window) {
        new ResizeObserver(update).observe(source);
      } else {
        window.addEventListener('resize', update);
      }
      document.fonts?.ready.then(update);
    });
  }

  matchDemoCardHeight();

  const data = window.PESO_PROJECT_ACTIVITY;
  if (!data) return;

  const number = new Intl.NumberFormat();
  const shortDate = new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  });
  const longDate = new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });

  function setText(name, value) {
    document.querySelectorAll(`[data-activity="${name}"]`).forEach((element) => {
      element.textContent = value;
    });
  }

  setText('commits', number.format(data.activity.summary.commits));
  setText('active-days', number.format(data.activity.summary.activeDays));
  setText('file-changes', number.format(data.activity.summary.fileChanges));
  setText('system-count', number.format(data.activity.systems.length));
  setText('open-issues', data.issues.available ? number.format(data.issues.open.length) : '—');
  setText('closed-issues', data.issues.available ? number.format(data.issues.recentlyClosed.length) : '—');
  setText('window-days', number.format(data.window.days));
  setText('branch', data.repository.branch);
  setText('generated-at', longDate.format(new Date(data.generatedAt)));

  document.querySelectorAll('[data-repository-link]').forEach((link) => {
    link.href = data.repository.url;
  });

  const weeklyProgress = document.getElementById('weekly-progress');
  if (weeklyProgress) {
    const weeks = data.activity.weeks.slice(-6);
    const maximum = Math.max(1, ...weeks.map((week) => week.fileChanges));

    weeks.forEach((week, index) => {
      const item = document.createElement('article');
      item.className = 'weekly-card';
      if (index === weeks.length - 1) item.classList.add('weekly-card--current');

      const heading = document.createElement('div');
      heading.className = 'weekly-card__head';
      const label = document.createElement('span');
      label.textContent = index === weeks.length - 1 ? 'Current week' : 'Week of';
      const date = document.createElement('strong');
      date.textContent = shortDate.format(new Date(`${week.start}T00:00:00Z`));
      heading.append(label, date);

      const value = document.createElement('p');
      value.className = 'weekly-card__value';
      value.textContent = number.format(week.fileChanges);

      const detail = document.createElement('p');
      detail.className = 'weekly-card__detail';
      detail.textContent = `${week.fileChanges === 1 ? 'file touch' : 'file touches'} · ${number.format(week.commits)} ${week.commits === 1 ? 'update' : 'updates'}`;

      const track = document.createElement('div');
      track.className = 'weekly-card__track';
      const fill = document.createElement('span');
      fill.style.width = `${Math.max(4, Math.round((week.fileChanges / maximum) * 100))}%`;
      track.appendChild(fill);

      item.append(heading, value, detail, track);
      weeklyProgress.appendChild(item);
    });
  }

  const timeline = document.getElementById('activity-timeline');
  if (timeline) {
    const weeks = data.activity.weeks.slice(-13);
    const maximum = Math.max(1, ...weeks.map((week) => week.commits));

    for (const week of weeks) {
      const item = document.createElement('div');
      item.className = 'timeline__week';
      item.setAttribute('role', 'img');
      item.setAttribute(
        'aria-label',
        `${week.commits} project updates and ${week.fileChanges} file touches in the week of ${week.start}`
      );

      const track = document.createElement('div');
      track.className = 'timeline__track';

      const fill = document.createElement('div');
      fill.className = 'timeline__fill';
      fill.style.height = `${Math.max(2, Math.round((week.commits / maximum) * 100))}%`;
      track.appendChild(fill);

      const label = document.createElement('span');
      label.className = 'timeline__label';
      label.textContent = shortDate.format(new Date(`${week.start}T00:00:00Z`));

      item.append(track, label);
      timeline.appendChild(item);
    }
  }

  const focusBars = document.getElementById('focus-bars');
  if (focusBars) {
    const systems = data.activity.systems.slice(0, 7);
    const maximum = Math.max(1, ...systems.map((system) => system.fileChanges));

    for (const system of systems) {
      const row = document.createElement('div');
      row.className = 'focus-bar';

      const top = document.createElement('div');
      top.className = 'focus-bar__top';
      const label = document.createElement('span');
      label.textContent = system.name;
      const value = document.createElement('span');
      value.textContent = `${number.format(system.fileChanges)} touches`;
      top.append(label, value);

      const track = document.createElement('div');
      track.className = 'focus-bar__track';
      const fill = document.createElement('div');
      fill.className = 'focus-bar__fill';
      fill.style.width = `${Math.max(3, Math.round((system.fileChanges / maximum) * 100))}%`;
      track.appendChild(fill);

      row.append(top, track);
      focusBars.appendChild(row);
    }
  }

  function renderIssues(listId, issues, emptyText) {
    const list = document.getElementById(listId);
    if (!list) return;

    if (!data.issues.available || issues.length === 0) {
      const item = document.createElement('li');
      item.className = 'issue-item--empty';
      item.textContent = data.issues.available ? emptyText : 'Issue data will appear after the next Pages build.';
      list.appendChild(item);
      return;
    }

    for (const issue of issues.slice(0, 6)) {
      const item = document.createElement('li');
      item.className = 'issue-item';
      const link = document.createElement('a');
      link.href = issue.url;
      link.target = '_blank';
      link.rel = 'noreferrer';

      const issueNumber = document.createElement('span');
      issueNumber.className = 'issue-number';
      issueNumber.textContent = `#${issue.number}`;
      const title = document.createElement('span');
      title.textContent = issue.title;
      const arrow = document.createElement('span');
      arrow.className = 'issue-arrow';
      arrow.setAttribute('aria-hidden', 'true');
      arrow.textContent = '↗';
      link.append(issueNumber, title, arrow);
      item.appendChild(link);
      list.appendChild(item);
    }
  }

  renderIssues('open-issue-list', data.issues.open, 'No open issues.');
  renderIssues('closed-issue-list', data.issues.recentlyClosed, 'No issues closed in this window.');
})();
