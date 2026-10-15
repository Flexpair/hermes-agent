/**
 * Window text size (zoom).
 *
 * The main process owns the zoom level and persists it (see electron/zoom.ts
 * for the scale). The renderer only mirrors the current percent for the
 * settings UI: preset clicks go to the main process over IPC, and every
 * change comes back through onChanged, including ones made with the
 * Ctrl/Cmd +/-/0 shortcuts or the View menu, so the UI never drifts.
 */

import { DEFAULT_ZOOM_PERCENT } from '@hermes/shared'
import { atom } from 'nanostores'

// Mirror the main-process default so Appearance doesn't flash 100% before
// the main-process zoom.get() resolves.
export const $zoomPercent = atom<number>(DEFAULT_ZOOM_PERCENT)

export function setZoomPercent(percent: number): void {
  window.hermesDesktop?.zoom?.setPercent(percent)
}

if (typeof window !== 'undefined' && window.hermesDesktop?.zoom) {
  const zoom = window.hermesDesktop.zoom
  let receivedZoomChange = false

  zoom.onChanged(({ percent }) => {
    receivedZoomChange = true
    $zoomPercent.set(percent)
  })

  void zoom.get().then(({ percent }) => {
    if (!receivedZoomChange) {
      $zoomPercent.set(percent)
    }
  })
}
