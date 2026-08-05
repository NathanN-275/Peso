const { execFileSync } = require('node:child_process');

const NON_WEB_DIRECTORIES = [
  '.github/',
  'backend/',
  'dashboard/',
  'docs/',
  'supabase/',
];

function isRootDocumentation(filePath) {
  if (filePath.includes('/')) {
    return false;
  }

  return filePath.endsWith('.md') || filePath === 'LICENSE';
}

function isNonWebPath(filePath) {
  return isRootDocumentation(filePath)
    || NON_WEB_DIRECTORIES.some((directory) => filePath.startsWith(directory));
}

function shouldIgnoreBuild(changedFiles) {
  return changedFiles.length > 0 && changedFiles.every(isNonWebPath);
}

function netlifyIgnoreExitCode(changedFiles) {
  // Netlify uses 0 to stop a build and 1 to continue it.
  return shouldIgnoreBuild(changedFiles) ? 0 : 1;
}

function listChangedFiles(environment = process.env, runGit = execFileSync) {
  const cachedCommit = environment.CACHED_COMMIT_REF;
  const currentCommit = environment.COMMIT_REF;

  if (!cachedCommit || !currentCommit) {
    throw new Error('Netlify commit references are unavailable.');
  }

  const output = runGit(
    'git',
    [
      'diff',
      '--name-only',
      '--no-renames',
      '--diff-filter=ACDMRTUXB',
      '-z',
      cachedCommit,
      currentCommit,
      '--',
    ],
    { encoding: 'utf8' },
  );

  return output.split('\0').filter(Boolean);
}

function main() {
  try {
    const changedFiles = listChangedFiles();
    const exitCode = netlifyIgnoreExitCode(changedFiles);

    if (exitCode === 0) {
      console.log(`Skipping Netlify build for ${changedFiles.length} non-web file change(s).`);
    } else {
      console.log('Continuing Netlify build because web-relevant or unknown changes were detected.');
    }

    process.exitCode = exitCode;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.warn(`Continuing Netlify build because the change set could not be resolved: ${message}`);
    process.exitCode = 1;
  }
}

if (require.main === module) {
  main();
}

module.exports = {
  isNonWebPath,
  isRootDocumentation,
  listChangedFiles,
  netlifyIgnoreExitCode,
  shouldIgnoreBuild,
};
