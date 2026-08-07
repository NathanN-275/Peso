(function () {
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
  setText('open-issues', data.issues.available ? number.format(data.issues.open.length) : '—');
  setText('closed-issues', data.issues.available ? number.format(data.issues.recentlyClosed.length) : '—');
  setText('window-days', number.format(data.window.days));
  setText('branch', data.repository.branch);
  setText('generated-at', longDate.format(new Date(data.generatedAt)));

  const repositoryLinks = document.querySelectorAll('[data-repository-link]');
  repositoryLinks.forEach((link) => {
    link.href = data.repository.url;
  });

  const timeline = document.getElementById('activity-timeline');
  if (timeline) {
    const weeks = data.activity.weeks.slice(-13);
    const maximum = Math.max(1, ...weeks.map((week) => week.commits));

    for (const week of weeks) {
      const item = document.createElement('div');
      item.className = 'timeline__week';
      item.title = `${week.commits} commits and ${week.fileChanges} file changes in the week of ${week.start}`;

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
      value.textContent = `${number.format(system.fileChanges)} file changes`;
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
      item.textContent = data.issues.available ? emptyText : 'Issue data will appear after the first Pages build.';
      list.appendChild(item);
      return;
    }

    for (const issue of issues.slice(0, 7)) {
      const item = document.createElement('li');
      item.className = 'issue-item';
      const link = document.createElement('a');
      link.href = issue.url;

      const issueNumber = document.createElement('span');
      issueNumber.className = 'issue-number';
      issueNumber.textContent = `#${issue.number}`;
      const title = document.createElement('span');
      title.textContent = issue.title;
      link.append(issueNumber, title);
      item.appendChild(link);
      list.appendChild(item);
    }
  }

  renderIssues('open-issue-list', data.issues.open, 'No open issues.');
  renderIssues('closed-issue-list', data.issues.recentlyClosed, 'No issues closed in this window.');
})();
