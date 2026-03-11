import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface WindowPortalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  /** Unique name for the popup window — allows multiple independent popups */
  windowName?: string;
  width?: number;
  height?: number;
  children: ReactNode;
}

/**
 * Renders children into a real browser popup window via React portal.
 * Components stay in the same React tree so Zustand store, callbacks,
 * and all reactivity work automatically.
 */
export function WindowPortal({
  open,
  onClose,
  title = "Table",
  windowName,
  width = 700,
  height = 800,
  children,
}: WindowPortalProps) {
  const windowRef = useRef<Window | null>(null);
  const [portalContainer, setPortalContainer] = useState<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) {
      if (windowRef.current && !windowRef.current.closed) {
        windowRef.current.close();
      }
      windowRef.current = null;
      // Defer to avoid synchronous setState in effect body
      queueMicrotask(() => setPortalContainer(null));
      return;
    }

    // Center the popup on screen
    const left = window.screenX + (window.outerWidth - width) / 2;
    const top = window.screenY + (window.outerHeight - height) / 2;

    const popup = window.open(
      "",
      windowName ?? "",
      `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`,
    );

    if (!popup) {
      // Popup blocked — fall back silently
      onClose();
      return;
    }

    windowRef.current = popup;

    // Copy stylesheets from parent window
    const parentStyles = document.querySelectorAll('style, link[rel="stylesheet"]');
    parentStyles.forEach((node) => {
      popup.document.head.appendChild(node.cloneNode(true));
    });

    // Set dark mode class if parent has it
    if (document.documentElement.classList.contains("dark")) {
      popup.document.documentElement.classList.add("dark");
    }

    popup.document.title = title;
    popup.document.body.style.margin = "0";
    popup.document.body.style.overflow = "auto";

    // Create mount point
    const container = popup.document.createElement("div");
    container.id = "portal-root";
    popup.document.body.appendChild(container);
    // Defer to avoid synchronous setState in effect body
    queueMicrotask(() => setPortalContainer(container));

    // Handle popup close
    popup.addEventListener("beforeunload", () => {
      windowRef.current = null;
      setPortalContainer(null);
      onClose();
    });

    return () => {
      if (popup && !popup.closed) {
        popup.close();
      }
      windowRef.current = null;
      setPortalContainer(null);
    };
  }, [open, title, width, height, onClose]);

  if (!portalContainer) return null;

  return createPortal(children, portalContainer);
}
