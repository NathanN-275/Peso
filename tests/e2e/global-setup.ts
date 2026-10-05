const { assertStagingE2EEnvironment } = require('../../scripts/e2e-environment');

export default function globalSetup() {
  assertStagingE2EEnvironment(process.env);
}
