import type { Reporter, TestCase, TestResult, FullResult } from '@playwright/test/reporter';
import { mkdirSync, writeFileSync, appendFileSync } from 'node:fs';
import { dirname, relative } from 'node:path';

export default class CIReporter implements Reporter {
  rows: object[] = [];
  start = Date.now();
  onTestEnd(test: TestCase, result: TestResult) {
    this.rows.push({ file: relative(process.cwd() + '/e2e', test.location.file),
      title: test.titlePath().join(' › '), project: test.parent.project()?.name,
      status: result.status, expected: test.expectedStatus, duration: result.duration,
      error: result.errors.map(e => e.message || e.value).join('\n'), retry: result.retry });
  }
  onEnd(result: FullResult) {
    const path = process.env.E2E_SUMMARY || 'test-results/ci-summary.json';
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, JSON.stringify({ status: result.status, duration: Date.now() - this.start,
      shard: process.env.E2E_SHARD || 'local', rows: this.rows }, null, 2));
    if (process.env.GITHUB_STEP_SUMMARY) {
      const rows = this.rows as any[];
      const count = (status: string) => rows.filter(r => r.status === status).length;
      const failures = rows.filter(r => !['passed', 'skipped'].includes(r.status));
      appendFileSync(process.env.GITHUB_STEP_SUMMARY,
        `## Playwright ${process.env.E2E_SHARD || 'local'}\n\n` +
        `${result.status}: ${count('passed')} passed / ${failures.length} failed or interrupted / ${count('skipped')} skipped; ${((Date.now()-this.start)/1000).toFixed(1)} s\n\n` +
        failures.map(r => `- ${r.title.replaceAll('<', '&lt;')} (${r.status})\n\n\`\`\`text\n${r.error.replaceAll('```', "'''").slice(0,3000)}\n\`\`\`\n`).join('') +
        '\nHTML, JUnit, trace and JSON are in the artifact linked below.\n');
    }
  }
}
