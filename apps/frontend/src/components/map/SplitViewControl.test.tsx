import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SplitViewControl } from '@/components/map/SplitViewControl';

describe('SplitViewControl', () => {
  it('stays hidden until split view is available', () => {
    const { container } = render(
      <SplitViewControl available={ false } enabled={ false } onEnabledChange={ vi.fn() } />,
    );

    expect(container.childElementCount).toBe(0);
  });

  it('enters split view from the map overlay', () => {
    const onEnabledChange = vi.fn();
    render(
      <SplitViewControl available enabled={ false } onEnabledChange={ onEnabledChange } />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Split View' }));
    expect(onEnabledChange).toHaveBeenCalledWith(true);
  });

  it('remains available for returning to single view', () => {
    const onEnabledChange = vi.fn();
    render(
      <SplitViewControl available={ false } enabled onEnabledChange={ onEnabledChange } />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Single View' }));
    expect(onEnabledChange).toHaveBeenCalledWith(false);
  });
});
