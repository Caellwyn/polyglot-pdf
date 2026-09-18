import { configure } from '@testing-library/dom';

// Raise @testing-library's internal findBy*/waitFor retry timeout from its
// 1000ms default. vitest's own testTimeout (see vite.config.ts) only bounds
// the overall test body -- it does NOT touch this separate, lower timeout,
// so a `findByTestId(...)` call kept timing out under full-suite fork
// contention even inside tests already given a longer budget. This was the
// root cause behind a rotating set of overlay/preview test failures that
// were red under load and green in isolation (bd polyglot-pdf-630ej, sdds1,
// 8urce, qta6l, sw5vl).
configure({ asyncUtilTimeout: 10000 });
