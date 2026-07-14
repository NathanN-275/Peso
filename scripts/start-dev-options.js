function parseStartOptions(argv = []) {
  const args = new Set(argv);

  return {
    startWeb: args.has('--web'),
    clearMetroCache: args.has('--clear') || args.has('-c'),
  };
}

function buildExpoStartArgs({ startWeb, clearMetroCache }) {
  return [
    'start',
    ...(startWeb ? ['--web'] : []),
    ...(clearMetroCache ? ['--clear'] : []),
  ];
}

module.exports = {
  buildExpoStartArgs,
  parseStartOptions,
};
