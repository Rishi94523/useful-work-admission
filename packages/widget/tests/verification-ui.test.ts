import { describe, expect, it, vi } from 'vitest';

import type { VerificationData } from '../src/types';
import { VerificationUI } from '../src/ui/verification';

function makeData(overrides: Partial<VerificationData> = {}): VerificationData {
  return {
    verificationId: 'verify-1',
    mode: 'blind',
    displayType: 'text',
    displayContent: 'A useful sample',
    prompt: 'Choose the correct label for this sample.',
    labels: ['negative', 'positive'],
    options: [],
    ...overrides,
  };
}

describe('VerificationUI', () => {
  it('renders a blind model-specific selector without exposing the prediction', () => {
    const container = document.createElement('div');
    const onSubmit = vi.fn();
    const ui = new VerificationUI(
      container,
      makeData({ predictedLabel: 'positive' }),
      onSubmit
    );

    ui.render();

    expect(container.textContent).not.toContain('"positive"');
    const select = container.querySelector('select') as HTMLSelectElement;
    expect(Array.from(select.options).map((option) => option.value)).toEqual([
      '',
      'negative',
      'positive',
    ]);

    select.value = 'negative';
    (container.querySelector('button') as HTMLButtonElement).click();
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        responseType: 'correct',
        correctedLabel: 'negative',
      })
    );
  });

  it('uses server-provided labels in confirmation correction mode', () => {
    const container = document.createElement('div');
    const ui = new VerificationUI(
      container,
      makeData({
        mode: 'confirm',
        predictedLabel: '1',
        labels: ['0', '1', '2'],
      }),
      vi.fn()
    );

    ui.render();
    const values = Array.from(
      (container.querySelector('select') as HTMLSelectElement).options
    ).map((option) => option.value);
    expect(values).toEqual(['', '0', '2']);
    expect(container.textContent).not.toContain('airplane');
  });
});
