import { spawn } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { dirname, join, resolve } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';

const require = createRequire(import.meta.url);
const architecture = process.arch === 'x64' ? 'amd64' : process.arch;
const binaryName = process.platform === 'win32' ? 'anvil.exe' : 'anvil';
let anvil = binaryName;
try {
  const pkg = require.resolve(`@foundry-rs/anvil-${process.platform}-${architecture}/package.json`);
  anvil = join(dirname(pkg), 'bin', binaryName);
} catch {
  // Use an existing Anvil installation when npm has no binary for this platform.
}

const data = resolve(process.env.DRISHTI_DATA_DIR || 'backend/data', 'demo-blockchain');
await mkdir(data, { recursive: true });
const rpcUrl = 'http://127.0.0.1:8545';
const chain = spawn(anvil, [
  '--host', '127.0.0.1', '--port', '8545', '--chain-id', '31337', '--accounts', '1',
  '--state', join(data, 'anvil-state.json'), '--state-interval', '1', '--silent',
], { stdio: 'inherit' });
let app;
let chainFailure;
chain.once('error', (error) => { chainFailure = error; });
chain.once('exit', (code) => {
  chainFailure = new Error(`Anvil exited (${code}).`);
  app?.kill();
});
for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => {
  app?.kill(signal);
  chain.kill(signal);
});

try {
  let ready = false;
  for (let attempt = 0; attempt < 30 && !ready; attempt++) {
    if (chainFailure) throw chainFailure;
    const response = await fetch(rpcUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'eth_chainId', params: [] }),
      signal: AbortSignal.timeout(1000),
    }).catch(() => null);
    ready = response?.ok && (await response.json()).result === '0x7a69';
    if (!ready) await delay(200);
  }
  if (chainFailure) throw chainFailure;
  if (!ready) throw new Error('The local demo chain did not become ready on port 8545.');
  console.log('Local demonstration chain running. This chain is controlled by this workstation.');
  const python = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python';
  app = spawn(python, ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8001'], {
    stdio: 'inherit',
    env: { ...process.env, DRISHTI_CHAIN_RPC_URL: rpcUrl, DRISHTI_CHAIN_SENDER: '', DRISHTI_CHAIN_DEMO: '1', DRISHTI_DISABLE_AUTO_STREAMS: '1' },
  });
  process.exitCode = await new Promise((done, reject) => {
    app.once('exit', (code) => done(code ?? 0));
    app.once('error', reject);
  });
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
} finally {
  chain.kill();
}
