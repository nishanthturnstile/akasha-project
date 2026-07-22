import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const frontendRoot = resolve(process.cwd());

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    if (!entry.name.match(/\.(?:ts|tsx)$/) || entry.name.match(/\.test\.(?:ts|tsx)$/)) return [];
    return [path];
  });
}

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
    const retiredPalette = /(?:bg|border|text|ring)-(?:amber|red|emerald|zinc)-\d{2,3}/;
    for (const file of sourceFiles(resolve(frontendRoot, 'src'))) {
      expect(readFileSync(file, 'utf8'), file).not.toMatch(retiredPalette);
    }
  });

  it('keeps hard-coded runtime colors out of React UI modules', () => {
    const approvedScientificModule = resolve(frontendRoot, 'src/components/map/Legend.tsx');
    const hardCodedColor = /#[\da-f]{3,8}|rgb\(\s*\d|hsl\(\s*\d/i;
    for (const file of sourceFiles(resolve(frontendRoot, 'src')).filter((path) => path.endsWith('.tsx'))) {
      if (file === approvedScientificModule) continue;
      expect(readFileSync(file, 'utf8'), file).not.toMatch(hardCodedColor);
    }
  });

  it('uses named overlay layers instead of isolated numeric z-index utilities', () => {
    const numericLayer = /\bz-(?:50|\[\d+\])\b/;
    for (const file of sourceFiles(resolve(frontendRoot, 'src')).filter((path) => path.endsWith('.tsx'))) {
      expect(readFileSync(file, 'utf8'), file).not.toMatch(numericLayer);
    }
  });
});
