#!/usr/bin/env node
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const target = path.resolve(__dirname, '../../../../scripts/click-through/browser.cjs');

if (require.main === module) {
  const result = spawnSync(process.execPath, [target, ...process.argv.slice(2)], {
    stdio: 'inherit',
    env: process.env,
  });
  process.exit(result.status === null ? 1 : result.status);
}

module.exports = require(target);
