// @vitest-environment jsdom
//
// The client-side per-form archive disclosure (bd polyglot-pdf-qfyxr):
// collapsed by default with lazy AUTHED fetching through the backend routes
// (the archive is deliberately absent from the static bundle), and a viewer
// that is unmistakably read-only (exit criterion 3).
import { describe, expect, it, vi, afterEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { getIdToken: async () => "tok-a" } }),
}));

import { ArchivedVersionsLink } from "./ArchivedVersionsLink";

const REVS = {
  revisions: [
    { marker: "2025-06", published_at: "2025-06-01T00:00:00+00:00" },
    { marker: "2024-01", published_at: "2024-01-05T00:00:00+00:00" },
  ],
};

const SCHEMA = {
  form_metadata: { title: "Old W-7", form_number: "W-7" },
  parts: [], sections: [{ id: "s1", title: "Part One" }], fields: [],
};

function stubFetch(opts: { schema404?: boolean } = {}) {
  const calls: { url: string; init: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: any, init?: any) => {
      calls.push({ url: String(url), init: init ?? {} });
      if (opts.schema404 && String(url).includes("/schema")) {
        return {
          ok: false,
          status: 404,
          json: async () => ({ detail: "gone" }),
        } as unknown as Response;
      }
      const body = String(url).includes("/schema") ? SCHEMA : REVS;
      return {
        ok: true,
        status: 200,
        json: async () => body,
      } as unknown as Response;
    }),
  );
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ArchivedVersionsLink", () => {
  it("fetches nothing until expanded, then lists revisions with the Bearer token", async () => {
    // Mutations: fetch on mount -- the zero-calls assert goes red; drop the
    // Authorization header threading -- the header assert goes red.
    const calls = stubFetch();
    const user = userEvent.setup();
    render(<ArchivedVersionsLink kitId="w7" kitLabel="W-7" />);

    expect(calls).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Archived versions" }));
    await waitFor(() => expect(screen.getByText(/2025-06/)).toBeTruthy());

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toContain("/api/form-kits/w7/archive");
    const headers = calls[0].init.headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer tok-a");
  });

  it("a 404 on the revision read shows the in-viewer not-found message", async () => {
    // The listed revision vanished between listing and opening (removed,
    // superseded storage churn). Same register as the editor sibling: an
    // explicit read-only-viewer message, NOT an error banner and NOT a
    // throw. Mutation: revert the 404 branch to throwing -- red (the
    // dialog never opens).
    stubFetch({ schema404: true });
    const user = userEvent.setup();
    render(<ArchivedVersionsLink kitId="w7" kitLabel="W-7" />);

    await user.click(screen.getByRole("button", { name: "Archived versions" }));
    await waitFor(() => expect(screen.getByText(/2025-06/)).toBeTruthy());
    await user.click(screen.getByText(/2025-06/));

    const dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).toContain("could not be found");
    expect(dialog.querySelectorAll("input, textarea, select")).toHaveLength(0);
  });

  it("opening a revision shows the read-only viewer with no inputs", async () => {
    const calls = stubFetch();
    const user = userEvent.setup();
    render(<ArchivedVersionsLink kitId="w7" kitLabel="W-7" />);

    await user.click(screen.getByRole("button", { name: "Archived versions" }));
    await waitFor(() => expect(screen.getByText(/2025-06/)).toBeTruthy());
    await user.click(screen.getByText(/2025-06/));

    const dialog = await screen.findByRole("dialog");
    expect(calls[1].url).toContain("/api/form-kits/w7/archive/2025-06/schema");
    expect(dialog.textContent).toContain("read only");
    expect(dialog.textContent).toContain("cannot be filled");
    expect(dialog.querySelectorAll("input, textarea, select")).toHaveLength(0);
  });
});
