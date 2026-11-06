// Browser APIs Vuetify uses that jsdom doesn't provide. Only applies to test
// files that opt into jsdom (`// @vitest-environment jsdom`).
if (typeof window !== "undefined") {
  window.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  window.matchMedia ??= () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
  Element.prototype.scrollIntoView ??= () => {};
  // Used by Vuetify to position overlays (dialogs, menus).
  window.visualViewport ??= Object.assign(new EventTarget(), {
    width: 1024,
    height: 768,
    offsetLeft: 0,
    offsetTop: 0,
    pageLeft: 0,
    pageTop: 0,
    scale: 1,
  });
}
