import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { BrandLockup } from '@/components/BrandLockup';

describe('BrandLockup', () => {
  it('renders the endorsed full product name', () => {
    render(<BrandLockup />);
    expect(screen.getByLabelText('Akasha by CIDSA')).toBeTruthy();
    expect(screen.getByText('Akasha')).toBeTruthy();
    expect(screen.getByText('by CIDSA')).toBeTruthy();
  });

  it('keeps the full accessible name in icon mode', () => {
    render(<BrandLockup variant="icon" />);
    expect(screen.getByLabelText('Akasha by CIDSA')).toBeTruthy();
  });
});
