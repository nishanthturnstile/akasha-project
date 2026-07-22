import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { AuthHero } from '@/components/auth/AuthHero';

describe('AuthHero', () => {
  it('renders the supplied real image and endorsed brand treatment', () => {
    const { container } = render(
      <AuthHero
        description="Workspace-scoped field intelligence."
        imageSrc="/images/onboarding1.png"
        title="Secure field intelligence."
      />,
    );

    expect(screen.getByText('Secure field intelligence.')).toBeTruthy();
    expect(screen.getByLabelText('Akasha by CIDSA')).toBeTruthy();
    expect(container.querySelector('img')?.getAttribute('src')).toBe('/images/onboarding1.png');
  });
});
