import { chromium } from 'playwright-core';
import fs from 'fs';

const slug = process.env.WP_SITE_SLUG || 'runner3-factory-smoke-2';
const pluginSlug = process.env.WP_PLUGIN_SLUG || 'runner3-r2-media';
const zipPath = process.env.WP_PLUGIN_ZIP || `/tmp/${pluginSlug}.zip`;
const stateFile = `ops/site-factory/${slug}.json`;
if (!fs.existsSync(stateFile)) throw new Error(`site factory state missing: ${stateFile}`);
if (!fs.existsSync('/tmp/wasmer-account.json')) throw new Error('decrypted Wasmer account state missing');
if (!fs.existsSync(zipPath)) throw new Error(`plugin zip missing: ${zipPath}`);

const site = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json,', 'utf8').replace?.('', '') || '{}');
