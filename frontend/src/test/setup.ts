/**
 * Bun test setup file.
 *
 * Configures happy-dom for DOM testing and extends matchers.
 */

import { GlobalRegistrator } from "@happy-dom/global-registrator";
import "@testing-library/jest-dom";

// Register happy-dom globals (window, document, etc.)
GlobalRegistrator.register();

// Clean up after each test
afterEach(() => {
  // Clear DOM by removing all child nodes
  while (document.body.firstChild) {
    document.body.removeChild(document.body.firstChild);
  }
});
