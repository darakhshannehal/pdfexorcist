// node test/pytest.mjs [pytest args]

import { nodeBoot } from '../node-boot.mjs';

// print the Python traceback; Node shows the minified source line
for (const ev of ['unhandledRejection', 'uncaughtException']) process.on(ev, (e) => {
  console.error(String(e?.message ?? e).slice(-4000));
  process.exit(2);
});

const { py } = await nodeBoot();
await py.loadPackage(['pytest', 'pyarrow'], { messageCallback: () => {} });
py.globals.set('ARGS', py.toPy(process.argv.slice(2)));
py.globals.set('SHARD', process.env.SHARD ?? ''); // "i/n": run every n-th test from i (CI matrix)
const code = await py.runPythonAsync(`
import os, sys, pytest
os.chdir('/repo')

class Shard:
    def pytest_collection_modifyitems(self, config, items):
        i, n = map(int, SHARD.split('/'))
        keep = items[i - 1::n]
        config.hook.pytest_deselected(items=[t for t in items if t not in keep])
        items[:] = keep

pytest.main(['-p', 'no:cacheprovider', 'tests', *ARGS], plugins=[Shard()] if SHARD else [])
`);
process.exit(Number(code));
