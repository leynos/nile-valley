/**
 * @file Ensures the Chrome binaries required by Puppeteer are available before
 * Mermaid diagrams are rendered in CI.
 *
 * Nixie shells out to `mmdc`, which depends on Puppeteer finding the
 * `chrome-headless-shell` executable. The GitHub runners used in CI start with
 * an empty Puppeteer cache, so we proactively download the browser artefacts
 * that match the version bundled with our dependencies. This keeps the `make
 * nixie` target reproducible without relying on a manual pre-install step.
 */

import { existsSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { executablePath } from 'puppeteer';
import { downloadBrowsers } from 'puppeteer/lib/esm/puppeteer/node/install.js';

const missingBrowserMessageFragment = 'Could not find Chrome';

function hasLocalBrowser() {
  try {
    const browserPath = executablePath();
    return Boolean(browserPath) && existsSync(browserPath);
  } catch (error) {
    if (error instanceof Error && error.message.includes(missingBrowserMessageFragment)) {
      return false;
    }

    throw error;
  }
}

async function ensureBrowsersInstalled() {
  if (hasLocalBrowser()) {
    return;
  }

  await downloadBrowsers();

  if (!hasLocalBrowser()) {
    throw new Error('Puppeteer still cannot locate Chrome after downloading browser artefacts.');
  }
}

export async function main() {
  await ensureBrowsersInstalled();
}

const executedScriptUrl =
  process.argv[1] === undefined ? undefined : pathToFileURL(process.argv[1]).href;

if (executedScriptUrl === import.meta.url) {
  // Preserve the original side effect for the `make nixie` workflow while
  // allowing other modules to import `main` without triggering a download.
  main().catch((error) => {
    const message = error instanceof Error ? (error.stack ?? error.message) : String(error);
    process.stderr.write(`${message}\n`);
    process.exitCode = 1;
  });
}
