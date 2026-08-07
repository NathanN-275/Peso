#!/usr/bin/env node

import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

const WINDOW_DAYS = 90;
const DEFAULT_OUTPUT = 'docs/architecture/assets/activity-data.js';
const argv = process.argv.slice(2);
const outputIndex = argv.indexOf('--output');
const outputPath = resolve(outputIndex >= 0 ? argv[outputIndex + 1] : DEFAULT_OUTPUT);
const now = new Date();
const cutoff = new Date(now.getTime() - WINDOW_DAYS * 24 * 60 * 60 * 1000);

function runGit(args) {
  return execFileSync('git', args, { encoding: 'utf8' }).trim();
}

function classifyPath(path) {
  const normalized = path.toLowerCase();

  if (normalized.startsWith('backend/')) return 'Backend & analysis';
  if (normalized.startsWith('web/')) return 'Marketing Site';
  if (normalized.startsWith('dashboard/')) return 'Analysis dashboard';
  if (normalized.startsWith('supabase/')) return 'Supabase data';
  if (
    normalized === 'app.web.tsx'
    || normalized.startsWith('src/web/')
    || normalized.includes('/web')
    || normalized.startsWith('lib/web')
  ) return 'Web App';
  if (
    normalized === 'app.tsx'
    || normalized === 'index.ts'
    || normalized.startsWith('src/')
    || normalized.startsWith('lib/')
    || normalized.startsWith('context/')
    || normalized.startsWith('ios/')
    || normalized.startsWith('android/')
  ) return 'Mobile & shared app';
  if (
    normalized.startsWith('docs/')
    || normalized.endsWith('.md')
    || normalized === 'context.md'
  ) return 'Documentation';
  return 'Delivery & tooling';
}

function weekStart(value) {
  const date = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  const day = date.getUTCDay();
  const offset = day === 0 ? -6 : 1 - day;
  date.setUTCDate(date.getUTCDate() + offset);
  return date.toISOString().slice(0, 10);
}

function buildCommitActivity() {
  const raw = runGit([
    'log',
    `--since=${cutoff.toISOString()}`,
    '--no-merges',
    '--date=iso-strict',
    '--pretty=format:COMMIT%x09%aI',
    '--numstat',
  ]);
  const commits = [];
  let current = null;

  for (const line of raw.split('\n')) {
    if (line.startsWith('COMMIT\t')) {
      current = { date: line.slice(7, 17), files: [] };
      commits.push(current);
      continue;
    }

    if (!current || !line.trim()) continue;
    const [addedRaw, deletedRaw, ...pathParts] = line.split('\t');
    const path = pathParts.join('\t');
    if (!path) continue;
    const additions = addedRaw === '-' ? 0 : Number.parseInt(addedRaw, 10) || 0;
    const deletions = deletedRaw === '-' ? 0 : Number.parseInt(deletedRaw, 10) || 0;
    current.files.push({ path, additions, deletions });
  }

  const weeks = new Map();
  const systems = new Map();
  const activeDays = new Set();
  let fileChanges = 0;
  let additions = 0;
  let deletions = 0;

  for (const commit of commits) {
    activeDays.add(commit.date);
    const key = weekStart(commit.date);
    const week = weeks.get(key) ?? {
      start: key,
      commits: 0,
      fileChanges: 0,
      additions: 0,
      deletions: 0,
    };
    week.commits += 1;

    for (const file of commit.files) {
      fileChanges += 1;
      additions += file.additions;
      deletions += file.deletions;
      week.fileChanges += 1;
      week.additions += file.additions;
      week.deletions += file.deletions;

      const name = classifyPath(file.path);
      const system = systems.get(name) ?? {
        name,
        fileChanges: 0,
        additions: 0,
        deletions: 0,
      };
      system.fileChanges += 1;
      system.additions += file.additions;
      system.deletions += file.deletions;
      systems.set(name, system);
    }

    weeks.set(key, week);
  }

  const firstWeek = weekStart(cutoff.toISOString());
  const cursor = new Date(`${firstWeek}T00:00:00Z`);
  const lastWeek = weekStart(now.toISOString());
  while (cursor.toISOString().slice(0, 10) <= lastWeek) {
    const key = cursor.toISOString().slice(0, 10);
    if (!weeks.has(key)) {
      weeks.set(key, { start: key, commits: 0, fileChanges: 0, additions: 0, deletions: 0 });
    }
    cursor.setUTCDate(cursor.getUTCDate() + 7);
  }

  return {
    summary: {
      commits: commits.length,
      activeDays: activeDays.size,
      fileChanges,
      additions,
      deletions,
    },
    weeks: [...weeks.values()].sort((a, b) => a.start.localeCompare(b.start)),
    systems: [...systems.values()].sort((a, b) => b.fileChanges - a.fileChanges),
  };
}

async function fetchAllIssues(repository, token) {
  if (!repository || !token) {
    return { available: false, open: [], recentlyClosed: [], openedInWindow: 0 };
  }

  const issues = [];
  let page = 1;

  while (page <= 10) {
    const url = new URL(`https://api.github.com/repos/${repository}/issues`);
    url.searchParams.set('state', 'all');
    url.searchParams.set('sort', 'updated');
    url.searchParams.set('direction', 'desc');
    url.searchParams.set('per_page', '100');
    url.searchParams.set('page', String(page));

    const response = await fetch(url, {
      headers: {
        Accept: 'application/vnd.github+json',
        Authorization: `Bearer ${token}`,
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'peso-project-pages',
      },
    });

    if (!response.ok) {
      throw new Error(`GitHub issues request failed with ${response.status}`);
    }

    const pageItems = await response.json();
    issues.push(...pageItems.filter((item) => !item.pull_request));
    if (pageItems.length < 100) break;
    page += 1;
  }

  const normalize = (issue) => ({
    number: issue.number,
    title: issue.title,
    state: issue.state,
    url: issue.html_url,
    createdAt: issue.created_at,
    updatedAt: issue.updated_at,
    closedAt: issue.closed_at,
    labels: issue.labels.map((label) => typeof label === 'string' ? label : label.name),
  });
  const normalized = issues.map(normalize);
  const open = normalized
    .filter((issue) => issue.state === 'open')
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  const recentlyClosed = normalized
    .filter((issue) => issue.closedAt && new Date(issue.closedAt) >= cutoff)
    .sort((a, b) => b.closedAt.localeCompare(a.closedAt));

  return {
    available: true,
    open,
    recentlyClosed,
    openedInWindow: normalized.filter((issue) => new Date(issue.createdAt) >= cutoff).length,
  };
}

const repository = process.env.GITHUB_REPOSITORY || 'NathanN-275/Peso';
const branch = process.env.GITHUB_REF_NAME || runGit(['branch', '--show-current']) || 'main';
const activity = buildCommitActivity();
let issues;

try {
  issues = await fetchAllIssues(repository, process.env.GITHUB_TOKEN);
} catch (error) {
  console.warn(`Issue data unavailable: ${error.message}`);
  issues = { available: false, open: [], recentlyClosed: [], openedInWindow: 0 };
}

const payload = {
  generatedAt: now.toISOString(),
  window: {
    days: WINDOW_DAYS,
    startsAt: cutoff.toISOString(),
    endsAt: now.toISOString(),
  },
  repository: {
    name: repository,
    url: `https://github.com/${repository}`,
    branch,
  },
  activity,
  issues,
};

mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(
  outputPath,
  `window.PESO_PROJECT_ACTIVITY = ${JSON.stringify(payload, null, 2)};\n`,
  'utf8',
);

console.log(`Wrote project activity to ${outputPath}`);
