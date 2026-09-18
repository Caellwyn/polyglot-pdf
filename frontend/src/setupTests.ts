// Import configure from @testing-library/react, NOT @testing-library/dom
// directly: this repo has two copies of @testing-library/dom installed (a
// hoisted one and a nested one under @testing-library/react's own
// node_modules), each with independent module-level config state. `screen`
// (what every test actually calls findBy*/waitFor on) comes from the NESTED
// copy via @testing-library/react's re-export, so configuring the hoisted
// copy directly is a silent no-op -- verified by comparing getConfig() on
// both copies before/after. Importing configure from @testing-library/react
// guarantees it resolves the same copy `screen` uses.
import { configure } from '@testing-library/react';

// Raise @testing-library's internal findBy*/waitFor retry timeout from its
// 1000ms default. vitest's own testTimeout (see vite.config.ts) only bounds
// the overall test body -- it does NOT touch this separate, lower timeout,
// so a `findByTestId(...)` call kept timing out under full-suite fork
// contention even inside tests already given a longer budget. This was the
// root cause behind a rotating set of overlay/preview test failures that
// were red under load and green in isolation (bd polyglot-pdf-630ej, sdds1,
// 8urce, qta6l, sw5vl).
configure({ asyncUtilTimeout: 10000 });
