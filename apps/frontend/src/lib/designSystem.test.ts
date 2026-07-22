import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const frontendRoot = resolve(process.cwd());

describe('CIDSA design-system contract', () => {
  it('keeps the canonical light-first palette and typography', () => {
    const css = readFileSync(resolve(frontendRoot, 'src/styles/globals.css'), 'utf8');
    expect(css).toContain('--color-cidsa-primary: #16a34a');
    expect(css).toContain('--color-cidsa-secondary: #3b82f6');
    expect(css).toContain('--color-cidsa-accent: #0891b2');
    expect(css).toContain('"Plus Jakarta Sans"');
    expect(css).toContain('color-scheme: light');
    expect(css).toContain('.dark {');
  });

  it('does not depend on the retired display and numeric fonts', () => {
    const packageJson = readFileSync(resolve(frontendRoot, 'package.json'), 'utf8');
    expect(packageJson).not.toMatch(/space-grotesk|jetbrains-mono/i);
  });

  it('applies the saved theme before paint and otherwise falls back to light', () => {
    const html = readFileSync(resolve(frontendRoot, 'index.html'), 'utf8');
    expect(html).toContain("stored === 'light' || stored === 'dark' ? stored : 'light'");
    expect(html).toContain("document.documentElement.style.colorScheme = 'light'");
    expect(html).not.toContain('prefers-color-scheme');
  });

  it('uses semantic status classes instead of raw Tailwind status palettes', () => {
    const sourceFiles = [
      'src/components/admin/ingestion/AdminIngestionRunPanel.tsx',
      'src/components/scaffold/IndexPanel.tsx',
      'src/pages/monitoring/MonitoringGlobalView.tsx',
      'src/pages/monitoring/IngestionJobDetail.tsx',
      'src/pages/monitoring/IngestionJobsList.tsx',
      'src/pages/risk/DiseasesPestsPage.tsx',
    ];
    const retiredPalette = /(?:bg|border|text|ring)-(?:amber|red|emerald|zinc)-\d{2,3}/;
    for (const file of sourceFiles) {
      expect(readFileSync(resolve(frontendRoot, file), 'utf8')).not.toMatch(retiredPalette);
    }
  });
});
