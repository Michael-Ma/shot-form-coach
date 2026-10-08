/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { PoseComparison } from "./PoseComparison";

const text = (en: string, zh = `中 ${en}`) => ({ en, zh });
const frames = [0, 1, 2].map((n) => ({ frame_id: `f${n}`, frame_index: n, time_us: n * 500000, source_time_us: 10000000 + n * 500000, source_frame_index: 20 + n }));
const coaching = {
  version: "1", status: "reviewed", overall: { headline: text("Work on the finish", "先练结束动作"), summary: text("One supported observation.", "有一个可观察的调整方向。") },
  metrics: [{ id: "timing", label: text("Shooting rhythm", "出手节奏"), display_value: text("0.4 sec", "0.4 秒"), interpretation: text("Measured from loading to release."), status: "measured", evidence_frame_ids: ["f2"] }],
  strengths: [] as { title: ReturnType<typeof text>; detail: ReturnType<typeof text>; evidence_frame_ids: string[] }[], issues: [{ id: "finish", rubric_id: "finish", rank: 1, severity: "medium", confidence: "high", title: text("Hold a relaxed finish", "放松地完成随挥"), observation: text("The hand lowers in these frames."), standard_gap: text("Practice a relaxed extension."), why_it_matters: text("Compare repeatability."), action: text("Keep a natural finish."), drill: text("Review five attempts."), evidence_frame_ids: ["f1"], source_ids: [], basis: "measurement" }],
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
let fixtureHealth: { models_ready: boolean; gemini_configured: boolean; astra_api_configured: boolean; workbench_configured: boolean; codex: { ready: boolean; reason: string } };
let fixtureRuns: { id: string; clip_count: number }[];
let stored: Map<string, string>;
let fixtureComparison: PoseComparison;
const points = Array.from({ length: 33 }, (_, n) => ({ x: .45 + (n % 2) * .1, y: .2 + n * .015, visibility: .98 }));
const openSettings = () => { fireEvent.click(screen.getByRole("button", { name: "Settings" })); return screen.getByRole("dialog", { name: "Settings" }); };
const closeSettings = () => fireEvent.click(screen.getByRole("button", { name: "Close settings" }));
beforeEach(() => {
  stored = new Map();
  vi.stubGlobal("localStorage", { getItem: (key: string) => stored.get(key) ?? null, setItem: vi.fn((key: string, value: string) => stored.set(key, value)), clear: () => stored.clear() });
  fixtureHealth = { models_ready: true, gemini_configured: false, astra_api_configured: false, workbench_configured: false, codex: { ready: false, reason: "codex_login_required" } };
  fixtureRuns = [];
  fixtureComparison = {
    version: "1", mode: "teaching", label: text("Teaching target illustration", "教学目标示意"), description: text("Arm extension illustration, fitted to your own segment lengths.", "按本人手臂长度绘制的伸展示意。"), source_type: "teaching_schematic", source_ids: [], coordinate_system: "normalized_own_frame", comparison_status: "available",
    frames: frames.map((frame, n) => ({ frame_index: n, phase: n === 0 ? "outside_phase" : n === 1 ? "release" : "follow_through", available: n > 0, reason: n === 0 ? "outside_phase" : undefined, target_landmarks: points.map((p) => ({ ...p, x: p.x + .1 })), connections: [[12, 14], [14, 16]], own_evidence: { ...frame, asset_id: "b" }, deltas: [] })),
  };
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value: function(this: HTMLDialogElement) { this.setAttribute("open", ""); this.querySelector<HTMLButtonElement>(".settings-close")?.focus(); } });
  Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value: function(this: HTMLDialogElement) { this.removeAttribute("open"); this.dispatchEvent(new Event("close")); } });
  fixtureAssets = [makeAsset("a", "Shot A"), makeAsset("b", "Shot B")];
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: vi.fn() });
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.stubGlobal("fetch", vi.fn(async (path: string, options?: RequestInit) => {
    if (path === "/api/assets") return { ok: true, json: async () => fixtureAssets };
    if (path === "/api/jobs") return { ok: true, json: async () => [] };
    if (path === "/api/workbench/runs") return { ok: true, json: async () => fixtureRuns };
    if (path === "/api/health") return { ok: true, json: async () => fixtureHealth };
    if (path === "/api/analyses" && options?.method === "POST") return { ok: true, json: async () => ({}) };
    if (path.includes("/tracks")) return { ok: true, json: async () => ({ frames: frames.map(() => ({ width: 640, height: 480, landmarks: points, person_box: null, ball: null })) }) };
    if (path.includes("/pose-comparison")) return { ok: true, json: async () => fixtureComparison };
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
    openSettings();
    fireEvent.click(screen.getByRole("button", { name: "中文" }));
    fireEvent.click(screen.getByRole("button", { name: "关闭设置" }));
    expect(await screen.findByText("先练结束动作")).toBeTruthy();
    expect(screen.getByText("出手节奏")).toBeTruthy();
    expect(screen.queryByText("Work on the finish")).toBeNull();
  });
  it("hides stale comparison exports until the selected reference is rebuilt", async () => {
    render(<App />);
    await screen.findByText("Work on the finish");
    fireEvent.click(screen.getByText("Save or share this review"));
    expect(screen.getByRole("link", { name: /Written review/ }).getAttribute("href")).toBe("/api/reports/report-b/text");
    openSettings();
    fireEvent.change(screen.getByLabelText("Compare with another of your shots"), { target: { value: "a" } });
    closeSettings();
    fireEvent.click(document.querySelector(".comparison-disclosure > summary")!);
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
    openSettings();
    const select = screen.getByRole("combobox", { name: "Analysis method" }) as HTMLSelectElement;
    expect(select.value).toBe("astra_codex");
    closeSettings();
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


describe("unified settings drawer", () => {
  it("keeps every configuration input in a single labelled drawer and explains Workbench", async () => {
    render(<App />);
    await screen.findByText("Work on the finish");
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(document.querySelector(".sidebar")?.querySelector("select,input,details")).toBeNull();
    const dialog = openSettings();
    for (const label of ["Analysis method", "Shooting hand", "Camera view", "Shot context", "Compare with another of your shots", "Pose comparison target", "Playback speed"]) {
      expect(within(dialog).getByRole("combobox", { name: label })).toBeTruthy();
    }
    expect(within(dialog).getByRole("checkbox", { name: "Focus on movement" })).toBeTruthy();
    expect(within(dialog).getByRole("checkbox", { name: "Pose overlay" })).toBeTruthy();
    expect(within(dialog).getByRole("button", { name: "中文" })).toBeTruthy();
    expect(within(dialog).getByText(/It is not another analysis model/)).toBeTruthy();
    expect(within(dialog).getByText(/Workbench is not connected/)).toBeTruthy();
    expect(within(dialog).queryByRole("button", { name: "Import & analyze" })).toBeNull();
    expect(document.querySelectorAll("dialog")).toHaveLength(1);
  });
  it("retains valid preferences across closing and remounting, without analysis requests", async () => {
    fixtureHealth.gemini_configured = true;
    const app = render(<App />);
    await screen.findByText("Work on the finish");
    openSettings();
    fireEvent.change(screen.getByLabelText("Analysis method"), { target: { value: "gemini" } });
    fireEvent.change(screen.getByLabelText("Shooting hand"), { target: { value: "left" } });
    fireEvent.change(screen.getByLabelText("Camera view"), { target: { value: "side" } });
    fireEvent.change(screen.getByLabelText("Shot context"), { target: { value: "set_shot" } });
    fireEvent.change(screen.getByLabelText("Playback speed"), { target: { value: "0.25" } });
    fireEvent.click(screen.getByLabelText("Focus on movement"));
    fireEvent.click(screen.getByLabelText("Pose overlay"));
    closeSettings();
    expect(screen.queryByRole("dialog")).toBeNull();
    app.unmount();
    render(<App />);
    await screen.findByText("Work on the finish");
    openSettings();
    for (const [label, value] of [["Analysis method", "gemini"], ["Shooting hand", "left"], ["Camera view", "side"], ["Shot context", "set_shot"], ["Playback speed", "0.25"]]) {
      expect((screen.getByLabelText(label) as HTMLSelectElement).value).toBe(value);
    }
    expect((screen.getByLabelText("Focus on movement") as HTMLInputElement).checked).toBe(false);
    expect((screen.getByLabelText("Pose overlay") as HTMLInputElement).checked).toBe(true);
    expect(vi.mocked(fetch).mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
    closeSettings();
    fireEvent.click(screen.getByRole("button", { name: /Analyze this shot/ }));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([path, init]) => path === "/api/analyses" && init?.method === "POST")).toBe(true));
    const request = vi.mocked(fetch).mock.calls.find(([path]) => path === "/api/analyses")!;
    expect(JSON.parse(request[1]!.body as string).config).toMatchObject({ mode: "gemini", handedness: "left", camera_view: "side", shot_type: "set_shot" });
  });
  it("closes on cancel or backdrop and returns focus to the settings button", async () => {
    render(<App />);
    await screen.findByText("Work on the finish");
    const trigger = screen.getByRole("button", { name: "Settings" });
    trigger.focus();
    let dialog = openSettings();
    expect(document.activeElement).toBe(within(dialog).getByRole("button", { name: "Close settings" }));
    fireEvent(dialog, new Event("cancel", { bubbles: false, cancelable: true }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
    dialog = openSettings();
    fireEvent.click(dialog, { clientX: -1, clientY: -1 });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
  it("wraps Tab at both dialog edges without intercepting browser shortcuts", async () => {
    render(<App />);
    await screen.findByText("Work on the finish");
    const dialog = openSettings();
    // jsdom has no layout; supply bounds for this focus-containment check only.
    for (const element of dialog.querySelectorAll<HTMLElement>("a,button,input,select,textarea,summary,[tabindex]")) {
      Object.defineProperty(element, "getClientRects", { value: () => element.hidden ? [] : [new DOMRect(0, 0, 44, 44)] });
    }
    const first = within(dialog).getByRole("button", { name: "Close settings" });
    const last = within(dialog).getByRole("button", { name: "Back to review" });
    first.focus();
    fireEvent.keyDown(first, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(last);
    fireEvent.keyDown(last, { key: "Tab" });
    expect(document.activeElement).toBe(first);
    const shortcut = new KeyboardEvent("keydown", { key: "Tab", ctrlKey: true, shiftKey: true, bubbles: true, cancelable: true });
    fireEvent(first, shortcut);
    expect(shortcut.defaultPrevented).toBe(false);
    expect(document.activeElement).toBe(first);
  });
  it("shows the correct configured-empty Workbench state and a usable run when one exists", async () => {
    fixtureHealth.workbench_configured = true;
    render(<App />);
    await screen.findByText("Work on the finish");
    const dialog = openSettings();
    expect(within(dialog).getByText("No completed runs with clips are available yet.")).toBeTruthy();
    fixtureRuns = [{ id: "test-run-12345678", clip_count: 3 }];
    fireEvent.click(within(dialog).getByRole("button", { name: "Check again" }));
    await within(dialog).findByRole("combobox", { name: "Completed Workbench run" });
    expect(within(dialog).getByRole("option", { name: "12345678 · 3 clips" })).toBeTruthy();
    expect((within(dialog).getByRole("button", { name: "Import & analyze" }) as HTMLButtonElement).disabled).toBe(false);
    expect(vi.mocked(fetch).mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });
  it("keeps upload failures visible inside the open drawer without starting analysis", async () => {
    render(<App />);
    await screen.findByText("Work on the finish");
    const dialog = openSettings();
    const body = dialog.querySelector(".settings-body") as HTMLDivElement;
    body.scrollTop = 700;
    vi.mocked(fetch).mockImplementationOnce(async () => ({ ok: false, json: async () => ({ detail: "invalid_or_long_video" }) } as Response));
    fireEvent.change(dialog.querySelector("input[type=file]")!, { target: { files: [new File(["synthetic test"], "test.mp4", { type: "video/mp4" })] } });
    expect(await within(dialog).findByRole("alert")).toBeTruthy();
    expect(within(dialog).getByText("Choose a readable video of at most 30 seconds.")).toBeTruthy();
    expect(body.scrollTop).toBe(0);
    expect(screen.getByRole("dialog", { name: "Settings" })).toBeTruthy();
    expect(vi.mocked(fetch).mock.calls.some(([path]) => path === "/api/analyses")).toBe(false);
  });
  it("validates saved options instead of displaying invalid preferences", async () => {
    for (const key of ["sfc-lang", "sfc-mode", "sfc-hand", "sfc-view", "sfc-shot", "sfc-speed", "sfc-focus", "sfc-pose"]) stored.set(key, "invalid");
    render(<App />);
    await screen.findByText("Work on the finish");
    openSettings();
    expect((screen.getByLabelText("Analysis method") as HTMLSelectElement).value).toBe("local");
    expect((screen.getByLabelText("Playback speed") as HTMLSelectElement).value).toBe("0.5");
    expect((screen.getByLabelText("Shooting hand") as HTMLSelectElement).value).toBe("auto");
    expect((screen.getByLabelText("Focus on movement") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("Pose overlay") as HTMLInputElement).checked).toBe(false);
  });
});


describe("review outcomes and aligned pose comparison", () => {
  it("keeps a completed model review with no issues distinct from insufficient evidence", async () => {
    fixtureAssets = fixtureAssets.map((a) => ({ ...a, coaching: {
      ...coaching, assessment_source: "model", outcome: "no_priority_issue", issues: [],
      empty_state: { title: text("No correction needs priority in the observed phases"), detail: text("Check more shots for consistency; this is not an all-clear for unobserved technique.") },
      strengths: [
        { title: text("Continuous ball lift"), detail: text("The ball rises continuously in the reviewed frames."), evidence_frame_ids: ["f1"] },
        { title: text("Balanced landing"), detail: text("The landing stays within the visible base."), evidence_frame_ids: ["f2"] },
      ],
    } }));
    render(<App />);
    await screen.findByText("No correction needs priority in the observed phases");
    expect(screen.queryByText("No supported correction to rank yet")).toBeNull();
    expect(screen.getByTestId("review-empty").getAttribute("data-outcome")).toBe("no_priority_issue");
    expect(screen.getByText(/Keep doing · Continuous ball lift/)).toBeTruthy();
    expect(screen.getByText(/Keep doing · Balanced landing/)).toBeTruthy();
    fireEvent.click(within(screen.getByTestId("coaching-summary")).getAllByRole("button", { name: /Show this moment/ })[1]);
    expect(document.querySelector(".viewer img")?.getAttribute("src")).toBe("/api/assets/b/frames/2");
  });
  it("shows a model failure as a failed review without claiming the video cannot support findings", async () => {
    fixtureAssets = fixtureAssets.map((a) => ({ ...a, model_error: "model_reply_invalid", coaching: { ...coaching, outcome: "model_failed", issues: [], status: "limited" } }));
    render(<App />);
    await screen.findByText("The model review did not complete");
    expect(screen.queryByText("No supported correction to rank yet")).toBeNull();
    expect(screen.getByText(/Local movement measurements are available/)).toBeTruthy();
    expect(screen.getAllByTestId("coaching-metric")).toHaveLength(1);
    expect(screen.queryByText(/This is a movement summary. Choose Gemini/)).toBeNull();
  });
  it("draws a labeled target on the own video, jumps phases, and reuses one geometry request while scrubbing", async () => {
    stored.set("sfc-pose", "true");
    render(<App />);
    await screen.findByText("Arm extension illustration, fitted to your own segment lengths.");
    expect(screen.getByTestId("pose-unavailable").textContent).toContain("target appears around release");
    expect(screen.queryByTestId("target-pose")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Release ↗" }));
    expect(await screen.findByTestId("target-pose")).toBeTruthy();
    const target = screen.getByTestId("target-pose");
    expect(target.querySelectorAll("line")).toHaveLength(2);
    expect(target.closest(".video-main")).toBeTruthy();
    expect(screen.getByLabelText("Pose legend").textContent).toContain("You");
    fireEvent.click(screen.getByRole("button", { name: "Follow-through ↗" }));
    expect(document.querySelector(".viewer img")?.getAttribute("src")).toBe("/api/assets/b/frames/2");
    fireEvent.change(screen.getByLabelText("Video position"), { target: { value: "1" } });
    expect(vi.mocked(fetch).mock.calls.filter(([path]) => String(path).includes("/pose-comparison"))).toHaveLength(1);
    expect(vi.mocked(fetch).mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });
  it("does not display stale target geometry when selecting a blocked reference or changing shots", async () => {
    stored.set("sfc-pose", "true");
    render(<App />);
    await screen.findByText("Arm extension illustration, fitted to your own segment lengths.");
    fireEvent.click(screen.getByRole("button", { name: "Release ↗" }));
    expect(await screen.findByTestId("target-pose")).toBeTruthy();
    fixtureComparison = { ...fixtureComparison, mode: "reference", label: text("Selected reference"), comparison_status: "unavailable", reason: "view_unverified", frames: [] };
    openSettings();
    fireEvent.change(screen.getByLabelText("Pose comparison target"), { target: { value: "reference" } });
    fireEvent.change(screen.getByLabelText("Compare with another of your shots"), { target: { value: "a" } });
    closeSettings();
    await screen.findByText("Confirm that both clips share the same fixed camera view in Comparison settings.");
    expect(screen.queryByTestId("target-pose")).toBeNull();
    expect(vi.mocked(fetch).mock.calls.some(([path]) => String(path).includes("mode=reference&reference_asset_id=a&assume_same_view=false"))).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /Shot A/ }));
    await waitFor(() => expect(document.querySelector(".viewer img")?.getAttribute("src")).toBe("/api/assets/a/frames/0"));
    expect(screen.queryByTestId("target-pose")).toBeNull();
    expect(vi.mocked(fetch).mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });
  it("keeps comparison configuration in the drawer and respects an explicit hidden overlay preference", async () => {
    stored.set("sfc-pose", "false");
    render(<App />);
    await screen.findByText("Work on the finish");
    expect(screen.queryByRole("combobox", { name: "Pose comparison target" })).toBeNull();
    expect(vi.mocked(fetch).mock.calls.some(([path]) => String(path).includes("/pose-comparison"))).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Pose settings ↗" }));
    const dialog = screen.getByRole("dialog", { name: "Settings" });
    expect((within(dialog).getByRole("checkbox", { name: "Pose overlay" }) as HTMLInputElement).checked).toBe(false);
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Pose overlay" }));
    closeSettings();
    await screen.findByText("Arm extension illustration, fitted to your own segment lengths.");
    openSettings();
    fireEvent.change(within(dialog).getByRole("combobox", { name: "Pose comparison target" }), { target: { value: "none" } });
    closeSettings();
    expect(screen.queryByTestId("target-pose")).toBeNull();
    expect(screen.getByText(/Your pose is visible. Choose a teaching target/)).toBeTruthy();
    expect(stored.get("sfc-pose-target")).toBe("none");
    expect(vi.mocked(fetch).mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });
});


describe("explicit retry of an unknown model result", () => {
  it("requires an unchecked per-shot acknowledgement and never applies it to batch analysis", async () => {
    stored.set("sfc-mode", "gemini");
    fixtureHealth.gemini_configured = true;
    fixtureAssets = fixtureAssets.map((a) => ({ ...a, model_error: "request_unknown", analysis_config: { mode: "gemini" } }));
    render(<App />);
    await screen.findByText("Work on the finish");
    openSettings();
    const acknowledgement = screen.getByRole("checkbox", { name: /The last result is unknown/ }) as HTMLInputElement;
    expect(acknowledgement.checked).toBe(false);
    expect((screen.getByRole("button", { name: /Analyze this shot/, hidden: true }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Confirm in Settings whether to submit this shot again.")).toBeTruthy();
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
    fireEvent.click(acknowledgement);
    closeSettings();
    expect((screen.getByRole("button", { name: /Analyze this shot/ }) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByText("Confirm in Settings whether to submit this shot again.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Analyze this shot/ }));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([path]) => path === "/api/analyses")).toBe(true));
    const firstRequest = vi.mocked(fetch).mock.calls.find(([path]) => path === "/api/analyses")!;
    expect(JSON.parse(firstRequest[1]!.body as string)).toMatchObject({ asset_ids: ["b"], config: { allow_unknown_retry: true } });
    await waitFor(() => expect((screen.getByRole("button", { name: /Analyze this shot/ }) as HTMLButtonElement).disabled).toBe(true));
    openSettings();
    expect((screen.getByRole("checkbox", { name: /The last result is unknown/ }) as HTMLInputElement).checked).toBe(false);
    fireEvent.click(screen.getByRole("checkbox", { name: /The last result is unknown/ }));
    fireEvent.click(screen.getByRole("button", { name: /Analyze all shots/ }));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.filter(([path]) => path === "/api/analyses")).toHaveLength(2));
    const batch = vi.mocked(fetch).mock.calls.filter(([path]) => path === "/api/analyses")[1];
    expect(JSON.parse(batch[1]!.body as string).config.allow_unknown_retry).toBeUndefined();
  });
  it("clears retry acknowledgement on mode changes and hides it for a known failure", async () => {
    stored.set("sfc-mode", "gemini");
    fixtureHealth.gemini_configured = true;
    fixtureAssets = fixtureAssets.map((a) => ({ ...a, model_error: a.id === "b" ? "request_unknown" : "provider_bad_request", analysis_config: { mode: "gemini" } }));
    render(<App />);
    await screen.findByText("Work on the finish");
    openSettings();
    fireEvent.click(screen.getByRole("checkbox", { name: /The last result is unknown/ }));
    fireEvent.change(screen.getByLabelText("Analysis method"), { target: { value: "local" } });
    expect(screen.queryByRole("checkbox", { name: /The last result is unknown/ })).toBeNull();
    fireEvent.change(screen.getByLabelText("Analysis method"), { target: { value: "gemini" } });
    expect((screen.getByRole("checkbox", { name: /The last result is unknown/ }) as HTMLInputElement).checked).toBe(false);
    closeSettings();
    fireEvent.click(screen.getByRole("button", { name: /Shot A/ }));
    openSettings();
    expect(screen.queryByRole("checkbox", { name: /The last result is unknown/ })).toBeNull();
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });
});
