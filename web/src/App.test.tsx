/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const text = (en: string, zh = `中 ${en}`) => ({ en, zh });
const frames = [0, 1, 2].map((n) => ({ frame_id: `f${n}`, frame_index: n, time_us: n * 500000, source_time_us: 10000000 + n * 500000, source_frame_index: 20 + n }));
const coaching = {
  version: "1", status: "reviewed", overall: { headline: text("Work on the finish", "先练结束动作"), summary: text("One supported observation.", "有一个可观察的调整方向。") },
  metrics: [{ id: "timing", label: text("Shooting rhythm", "出手节奏"), display_value: text("0.4 sec", "0.4 秒"), interpretation: text("Measured from loading to release."), status: "measured", evidence_frame_ids: ["f2"] }],
  strengths: [], issues: [{ id: "finish", rubric_id: "finish", rank: 1, severity: "medium", confidence: "high", title: text("Hold a relaxed finish", "放松地完成随挥"), observation: text("The hand lowers in these frames."), standard_gap: text("Practice a relaxed extension."), why_it_matters: text("Compare repeatability."), action: text("Keep a natural finish."), drill: text("Review five attempts."), evidence_frame_ids: ["f1"], source_ids: [], basis: "measurement" }],
  next_practice: { title: text("Five relaxed attempts"), instruction: text("Stay at the same location."), success_check: text("Review the finish together.") }, limitations: [], rubric_version: "1",
};
const makeAsset = (id: string, label: string) => ({
  id, label, revision: 2, width: 640, height: 480, duration_us: 1500000, status: "analyzed", preview_url: `/api/assets/${id}/preview`, frame_index: frames,
  phases: { release: { range_us: [400000, 500000], frame_range: [0, 1], source: "manual", quality: "reviewed" } },
  measurements: { curve: [], measurements: [], flags: [], side: "right", visible_frames: 3, total_frames: 3 }, coaching,
  report: { id: `report-${id}`, locale: "en", asset_revision: 2, reference_id: null as string | null, reference_revision: null as number | null, coaching, findings: [], comparison: { status: "unavailable", reason: "select_reference", differences: [] }, sources: [] },
  report_request: { reference_asset_id: undefined as string | undefined, assume_same_view: false },
});
let fixtureAssets: ReturnType<typeof makeAsset>[];
beforeEach(() => {
  vi.stubGlobal("localStorage", { getItem: () => null, setItem: vi.fn(), clear: vi.fn() });
  fixtureAssets = [makeAsset("a", "Shot A"), makeAsset("b", "Shot B")];
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: vi.fn() });
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.stubGlobal("fetch", vi.fn(async (path: string, options?: RequestInit) => {
    if (path === "/api/assets") return { ok: true, json: async () => fixtureAssets };
    if (path === "/api/jobs" || path === "/api/workbench/runs") return { ok: true, json: async () => [] };
    if (path === "/api/health") return { ok: true, json: async () => ({ models_ready: true, gemini_configured: false, astra_api_configured: false, codex: { ready: false, reason: "codex_login_required" } }) };
    if (path.includes("/tracks")) return { ok: true, json: async () => ({ frames: [] }) };
    if (path === "/api/assets/b/reports" && options?.method === "POST") {
      const body = JSON.parse(options.body as string);
      fixtureAssets = fixtureAssets.map((a) => a.id === "b" ? { ...a, report_request: { reference_asset_id: body.reference_asset_id, assume_same_view: body.assume_same_view }, report: { ...a.report, id: "new-matching-report", reference_id: body.reference_asset_id, reference_revision: 2, locale: body.locale } } : a);
      return { ok: true, json: async () => ({}) };
    }
    throw Error(`Unexpected request: ${path}`);
  }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("coaching-first review", () => {
  it("switches all coaching prose immediately and jumps findings to the original evidence frame", async () => {
    render(<App />);
    await screen.findByText("Work on the finish");
    expect(screen.getAllByTestId("issue-card")).toHaveLength(1);
    fireEvent.click(screen.getAllByRole("button", { name: /Show this moment/ })[0]);
    expect(document.querySelector(".viewer img")?.getAttribute("src")).toBe("/api/assets/b/frames/1");
    expect(document.querySelector(".source-caption")?.textContent).toContain("10.500s");
    fireEvent.click(screen.getByRole("button", { name: "中文" }));
    expect(await screen.findByText("先练结束动作")).toBeTruthy();
    expect(screen.getByText("出手节奏")).toBeTruthy();
    expect(screen.queryByText("Work on the finish")).toBeNull();
  });
  it("hides stale comparison exports until the selected reference is rebuilt", async () => {
    render(<App />);
    await screen.findByText("Work on the finish");
    fireEvent.click(screen.getByText("Save or share this review"));
    expect(screen.getByRole("link", { name: /Written review/ }).getAttribute("href")).toBe("/api/reports/report-b/text");
    fireEvent.click(document.querySelector(".comparison-disclosure > summary")!);
    fireEvent.change(screen.getByLabelText("Compare with another of your shots"), { target: { value: "a" } });
    expect(screen.getByTestId("comparison-stale")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Written review/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Update comparison" }));
    await waitFor(() => expect(screen.queryByTestId("comparison-stale")).toBeNull());
    expect(screen.getByRole("link", { name: /Written review/ }).getAttribute("href")).toBe("/api/reports/new-matching-report/text");
  });
  it("keeps a saved remote choice visible without automatically starting a model call", async () => {
    vi.stubGlobal("localStorage", { getItem: (key: string) => key === "sfc-mode" ? "astra_codex" : null, setItem: vi.fn() });
    render(<App />);
    await screen.findByText("Work on the finish");
    const select = screen.getByRole("combobox", { name: "Analysis method" }) as HTMLSelectElement;
    expect(select.value).toBe("astra_codex");
    expect((screen.getByRole("button", { name: /Analyze this shot/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getAllByText("Sign in to Codex with ChatGPT, then restart the app.").length).toBeGreaterThan(0);
    expect(vi.mocked(fetch).mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });
  it("does not label historical exports as the new coaching review", async () => {
    fixtureAssets = fixtureAssets.map((a) => ({ ...a, report: { ...a.report, coaching: undefined as unknown as typeof coaching } }));
    render(<App />);
    await screen.findByText("Work on the finish");
    fireEvent.click(screen.getByText("Save or share this review"));
    expect(screen.queryByRole("link", { name: /Written review/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Prepare matching exports" })).toBeTruthy();
  });
  it("does not present a limited review with zero ranked issues as correct form", async () => {
    fixtureAssets = fixtureAssets.map((a) => ({ ...a, coaching: { ...coaching, status: "limited", issues: [] } }));
    render(<App />);
    await screen.findByText("No supported correction to rank yet");
    expect(screen.getByText(/This is not a clean bill of technique/)).toBeTruthy();
    expect(screen.queryByTestId("issue-card")).toBeNull();
  });
});
