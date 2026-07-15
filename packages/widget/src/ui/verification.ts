/**
 * Human Verification UI Component
 */

import type { VerificationData, VerificationResponse } from '../types';
import {
  announceToScreenReader,
  trapFocus,
  createAccessibleButton,
} from '../utils/accessibility';
import { PerformanceTimer } from '../utils/timing';

/**
 * Verification UI Component
 */
export class VerificationUI {
  private container: HTMLElement;
  private data: VerificationData;
  private onSubmit: (response: VerificationResponse) => void;
  private releaseFocusTrap: (() => void) | null = null;
  private releaseEscapeHandler: (() => void) | null = null;
  private timer: PerformanceTimer;
  private element: HTMLElement | null = null;

  constructor(
    container: HTMLElement,
    data: VerificationData,
    onSubmit: (response: VerificationResponse) => void
  ) {
    this.container = container;
    this.data = data;
    this.onSubmit = onSubmit;
    this.timer = new PerformanceTimer();
  }

  /**
   * Render the verification UI
   */
  render(): void {
    this.timer.start('verification');

    this.element = document.createElement('div');
    this.element.className = 'pouw-verification';
    this.element.setAttribute('role', 'dialog');
    this.element.setAttribute('aria-modal', 'true');
    this.element.setAttribute('aria-labelledby', 'pouw-verification-title');

    // Prompt
    const prompt = document.createElement('p');
    prompt.id = 'pouw-verification-title';
    prompt.className = 'pouw-verification-prompt';
    prompt.textContent = this.data.prompt;

    // Content (image or text)
    const content = this.createContent();

    this.element.appendChild(prompt);
    this.element.appendChild(content);

    if (this.data.mode === 'blind') {
      this.element.appendChild(this.createBlindLabelingUI());
    } else {
      // Confirmation mode is retained for integrations that explicitly want
      // it. The server defaults to blind labeling to reduce anchoring bias.
      const label = document.createElement('div');
      label.className = 'pouw-verification-label';
      label.textContent = `"${this.data.predictedLabel ?? ''}"`;
      this.element.appendChild(label);
      this.element.appendChild(this.createActions());
      this.element.appendChild(this.createCorrectionUI());
    }

    // Clear container and add verification UI
    this.container.innerHTML = '';
    this.container.appendChild(this.element);

    // Set up accessibility
    this.releaseFocusTrap = trapFocus(this.element);

    // Announce to screen readers
    const announcement =
      this.data.mode === 'blind'
        ? `Verification required: ${this.data.prompt}`
        : `Verification required: ${this.data.prompt} The predicted answer is ${this.data.predictedLabel ?? ''}`;
    announceToScreenReader(announcement, 'polite');
  }

  /**
   * Create an unanchored label selector. The model's predicted label is not
   * shown, so an honest reviewer supplies an independent judgment.
   */
  private createBlindLabelingUI(): HTMLElement {
    const wrapper = document.createElement('div');
    wrapper.className = 'pouw-correction visible';

    const label = document.createElement('label');
    label.className = 'pouw-correction-label';
    label.htmlFor = 'pouw-blind-label-select';
    label.textContent = 'Choose the correct label';

    const select = this.createLabelSelect('pouw-blind-label-select');
    const submitBtn = createAccessibleButton({
      text: 'Submit label',
      onClick: () => this.handleCorrection(select.value),
      className: 'pouw-button pouw-button--primary',
    });

    wrapper.appendChild(label);
    wrapper.appendChild(select);
    wrapper.appendChild(submitBtn);
    return wrapper;
  }

  /**
   * Create content display (image or text)
   */
  private createContent(): HTMLElement {
    const content = document.createElement('div');
    content.className = 'pouw-verification-content';

    if (this.data.displayType === 'image') {
      const img = document.createElement('img');
      img.className = 'pouw-verification-image';
      img.src = this.data.displayContent;
      img.alt = 'Image to verify';
      img.loading = 'eager';
      content.appendChild(img);
    } else {
      const text = document.createElement('div');
      text.className = 'pouw-verification-text';
      text.textContent = this.data.displayContent;
      content.appendChild(text);
    }

    return content;
  }

  /**
   * Create action buttons
   */
  private createActions(): HTMLElement {
    const actions = document.createElement('div');
    actions.className = 'pouw-verification-actions';

    // Yes/Confirm button
    const confirmBtn = createAccessibleButton({
      text: 'Yes, correct',
      ariaLabel: `Confirm that the answer "${this.data.predictedLabel}" is correct`,
      onClick: () => this.handleConfirm(),
      className: 'pouw-button pouw-button--primary',
    });

    // No/Reject button
    const rejectBtn = createAccessibleButton({
      text: 'No, wrong',
      ariaLabel: `Indicate that "${this.data.predictedLabel}" is incorrect`,
      onClick: () => this.handleReject(),
      className: 'pouw-button pouw-button--secondary',
    });

    actions.appendChild(confirmBtn);
    actions.appendChild(rejectBtn);

    return actions;
  }

  /**
   * Create correction UI
   */
  private createCorrectionUI(): HTMLElement {
    const correction = document.createElement('div');
    correction.className = 'pouw-correction';
    correction.id = 'pouw-correction';

    const label = document.createElement('label');
    label.className = 'pouw-correction-label';
    label.htmlFor = 'pouw-correction-select';
    label.textContent = 'What is the correct answer?';

    const select = this.createLabelSelect('pouw-correction-select');

    const submitBtn = createAccessibleButton({
      text: 'Submit correction',
      onClick: () => this.handleCorrection(select.value),
      className: 'pouw-button pouw-button--primary',
    });

    correction.appendChild(label);
    correction.appendChild(select);
    correction.appendChild(submitBtn);

    return correction;
  }

  /**
   * Get available correction labels
   */
  private getCorrectionLabels(): string[] {
    const labels = this.data.labels ?? [];
    if (this.data.mode === 'blind') return labels;
    return labels.filter((label) => label !== this.data.predictedLabel);
  }

  private createLabelSelect(id: string): HTMLSelectElement {
    const select = document.createElement('select');
    select.className = 'pouw-correction-select';
    select.id = id;

    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = 'Select the correct label...';
    placeholder.disabled = true;
    placeholder.selected = true;
    select.appendChild(placeholder);

    for (const labelText of this.getCorrectionLabels()) {
      const option = document.createElement('option');
      option.value = labelText;
      option.textContent = labelText;
      select.appendChild(option);
    }
    return select;
  }

  /**
   * Handle confirm action
   */
  private handleConfirm(): void {
    this.timer.end('verification');

    const response: VerificationResponse = {
      responseType: 'confirm',
      responseTimeMs: this.timer.get('verification'),
    };

    this.cleanup();
    this.onSubmit(response);
  }

  /**
   * Handle reject action
   */
  private handleReject(): void {
    // Show correction UI
    const correction = this.element?.querySelector('.pouw-correction');
    if (correction) {
      correction.classList.add('visible');
      const select = correction.querySelector('select');
      select?.focus();

      announceToScreenReader(
        'Please select the correct label from the dropdown',
        'polite'
      );
    }
  }

  /**
   * Handle correction submission
   */
  private handleCorrection(correctedLabel: string): void {
    if (!correctedLabel) {
      announceToScreenReader('Please select a label', 'assertive');
      return;
    }

    this.timer.end('verification');

    const response: VerificationResponse = {
      responseType: 'correct',
      correctedLabel,
      responseTimeMs: this.timer.get('verification'),
    };

    this.cleanup();
    this.onSubmit(response);
  }

  /**
   * Clean up event listeners
   */
  private cleanup(): void {
    if (this.releaseFocusTrap) {
      this.releaseFocusTrap();
      this.releaseFocusTrap = null;
    }

    if (this.releaseEscapeHandler) {
      this.releaseEscapeHandler();
      this.releaseEscapeHandler = null;
    }
  }

  /**
   * Destroy the component
   */
  destroy(): void {
    this.cleanup();
    if (this.element) {
      this.element.remove();
      this.element = null;
    }
  }
}
