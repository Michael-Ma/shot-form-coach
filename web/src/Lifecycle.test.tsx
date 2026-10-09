/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { type ManagedClip, type TrainingVideo } from "./Lifecycle";

type Clip = ManagedClip & { width: number; height: number; phases: {}; report: null };
type Candidate = { id: string; start_us: number; end_us: number; status: string };
let videos: TrainingVideo[];
let clips: Clip[];
let candidates: Candidate[];
let jobs: { id: string; kind: string; status: string; stage: string; payload: { video_id: string } }[];
let scanState: Record<string, string>;
let requests: { path: string; body: Record<string, unknown> }[];
const makeClip = (id = "clip-a", label = "Shot 1", start = 10000000, end = 15000000): Clip => ({
  id, label, revision: 2, lifecycle_revision: 0, session_id: "training", source_start_us: start, source_end_us: end,
  duration_us: end - start, status: "ready", preview_url: `/api/assets/${id}/preview`,
  frame_index: [], width: 640, height: 480, phases: {}, report: null,
});
const counts = (video: TrainingVideo) => ({ ...video, clip_count: clips.filter((clip) => clip.session_id === video.id && !clip.trashed_at).length, trashed_count: clips.filter((clip) => clip.session_id === video.id && clip.trashed_at).length });
async function openWorkspace() {
  fireEvent.click(await screen.findByRole("button", { name: "Manage clips · Saturday practice.mp4" }));
  await screen.findByRole("heading", { name: "Saturday practice.mp4" });
}
beforeEach(() => {
  videos = [{ id: "training", label: "Saturday practice.mp4", kind: "source", duration_us: 60000000, status: "ready", preview_url: "/api/videos/training/preview", clip_count: 2, trashed_count: 0 }];
  clips = [makeClip(), makeClip("clip-b", "Shot 2", 20000000, 25000000)];
  candidates = [];
  requests = []; jobs = []; scanState = {};
  const stored = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => stored.get(key) ?? null, setItem: (key: string, value: string) => stored.set(key, value) });
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: vi.fn() });
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value: function(this: HTMLDialogElement) { this.setAttribute("open", ""); } });
  Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value: function(this: HTMLDialogElement) { this.removeAttribute("open"); } });
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
    const ok = (value: unknown) => ({ ok: true, json: async () => value });
    if (path === "/api/health") return ok({ models_ready: true, gemini_configured: true, workbench_configured: false });
    if (path === "/api/jobs") return ok(jobs);
    if (path === "/api/workbench/runs") return ok([]);
    if (path === "/api/assets") return ok(clips.filter((clip) => !clip.trashed_at));
    if (path === "/api/videos") return ok(videos.map(counts));
    if (/^\/api\/videos\/[^/]+\?/.test(path)) { const id = path.split("/")[3].split("?")[0]; return ok({ ...counts(videos.find((video) => video.id === id)!), clips: clips.filter((clip) => clip.session_id === id), candidates, ...scanState }); }
    if (path === "/api/videos/upload") {
      requests.push({ path, body: {} });
      const video = { ...videos[0], id: "new-video", label: "New practice.mp4", status: "processing", preview_url: null };
      videos.push(video); return ok({ video, job: { status: "queued" } });
    }
    if (init?.method && init.method !== "GET") {
      const body = JSON.parse(init.body as string);
      requests.push({ path, body });
      if (path === "/api/analyses") return ok({});
      if (path === "/api/jobs/import-job/cancel") { jobs = []; return ok({ status: "cancelled" }); }
      if (path === "/api/videos/training/scan") return ok({ status: "queued" });
      if (path.endsWith("/dismiss")) { candidates = candidates.map((item) => item.id === path.split("/")[5] ? { ...item, status: "dismissed" } : item); return ok({}); }
      if (path === "/api/videos/training/clips") { const clip = makeClip("new-clip", body.label || "Shot 3", body.start_us, body.end_us); clips.push(clip); candidates = candidates.map((item) => item.id === body.candidate_id ? { ...item, status: "accepted" } : item); return ok(clip); }
      const id = path.split("/")[3];
      const index = clips.findIndex((clip) => clip.id === id);
      if (path.endsWith("/trim")) { const fresh = { ...clips[index], id: "trimmed", revision: 0, source_start_us: body.start_us, source_end_us: body.end_us, duration_us: body.end_us - body.start_us }; clips[index] = { ...clips[index], lifecycle_revision: (clips[index].lifecycle_revision || 0) + 1, trashed_at: "now", superseded_by: fresh.id }; clips.push(fresh); return ok(fresh); }
      if (path.endsWith("/trash") || path.endsWith("/restore")) { clips[index] = { ...clips[index], lifecycle_revision: (clips[index].lifecycle_revision || 0) + 1, trashed_at: path.endsWith("/trash") ? "now" : null }; return ok(clips[index]); }
      if (init.method === "PATCH") { clips[index] = { ...clips[index], label: body.label, lifecycle_revision: (clips[index].lifecycle_revision || 0) + 1 }; return ok(clips[index]); }
    }
    throw Error(`Unexpected request ${path}`);
  }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("full-video lifecycle", () => {
  it("opens in the source library and imports without automatically analyzing", async () => {
    render(<App />);
    await screen.findByRole("button", { name: "Manage clips · Saturday practice.mp4" });
    expect(screen.getByRole("heading", { name: "One session. One change to practice." })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Analyze this shot/ })).toBeNull();
    fireEvent.change(screen.getByLabelText("Import a training video"), { target: { files: [new File(["fixture"], "new.mp4", { type: "video/mp4" })] } });
    expect(await screen.findByRole("heading", { name: "New practice.mp4" })).toBeTruthy();
    expect(screen.getByText("Preparing video preview…")).toBeTruthy();
    expect(requests.map((request) => request.path)).toEqual(["/api/videos/upload"]);
  });
  it("uses the original playhead when marking and saves a selected clip for later analysis", async () => {
    render(<App />); await openWorkspace();
    const player = screen.getByLabelText("Source video", { selector: "video" }) as HTMLVideoElement;
    player.currentTime = 3.2; fireEvent.timeUpdate(player);
    fireEvent.click(screen.getByRole("button", { name: "Use current time as start" }));
    player.currentTime = 7.7; fireEvent.timeUpdate(player);
    fireEvent.click(screen.getByRole("button", { name: "Use current time as end" }));
    fireEvent.change(screen.getByLabelText("Clip name"), { target: { value: "Corner attempt" } });
    fireEvent.click(screen.getByRole("button", { name: /Add clip/ }));
    expect(await screen.findByRole("checkbox", { name: "Select Corner attempt" })).toBeTruthy();
    expect(requests[0]).toEqual({ path: "/api/videos/training/clips", body: { start_us: 3200000, end_us: 7700000, label: "Corner attempt" } });
    expect((screen.getByRole("checkbox", { name: "Select Corner attempt" }) as HTMLInputElement).checked).toBe(true);
    expect(requests.some((request) => request.path === "/api/analyses")).toBe(false);
  });
  it("rejects reversed or overlong ranges before submitting", async () => {
    render(<App />); await openWorkspace();
    fireEvent.change(screen.getByLabelText("Start (seconds)"), { target: { value: "20" } });
    fireEvent.change(screen.getByLabelText("End (seconds)"), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: /Add clip/ }));
    expect(screen.getByRole("alert").textContent).toContain("Choose a start before the end");
    fireEvent.change(screen.getByLabelText("Start (seconds)"), { target: { value: "0" } });
    fireEvent.change(screen.getByLabelText("End (seconds)"), { target: { value: "40" } });
    fireEvent.click(screen.getByRole("button", { name: /Add clip/ }));
    expect(requests).toHaveLength(0);
  });
  it("analyzes only selected clips and keeps settings out of clip controls", async () => {
    render(<App />); await openWorkspace();
    expect((screen.getByRole("button", { name: /Analyze selected/ }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Shot 2" }));
    fireEvent.click(screen.getByRole("button", { name: /Analyze selected/ }));
    await waitFor(() => expect(requests).toHaveLength(1));
    expect(requests[0].body.asset_ids).toEqual(["clip-b"]);
    expect(screen.queryByRole("combobox", { name: "Analysis method" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Analyze all shots/ })).toBeNull();
  });
  it("moves a clip to trash and restores with the returned revision on Undo", async () => {
    render(<App />); await openWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Move to trash · Shot 1" }));
    await screen.findByText("Clip moved to trash.");
    await waitFor(() => expect(screen.queryByRole("checkbox", { name: "Select Shot 1" })).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(await screen.findByRole("checkbox", { name: "Select Shot 1" })).toBeTruthy();
    expect(requests).toEqual([{ path: "/api/assets/clip-a/trash", body: { expected_revision: 2, expected_lifecycle_revision: 0 } }, { path: "/api/assets/clip-a/restore", body: { expected_revision: 2, expected_lifecycle_revision: 1 } }]);
  });
  it("saves an immutable trim and leaves the earlier version recoverable", async () => {
    render(<App />); await openWorkspace();
    fireEvent.click(screen.getAllByRole("button", { name: "Edit clip" })[0]);
    expect((screen.getByLabelText("Start (seconds)") as HTMLInputElement).value).toBe("10");
    fireEvent.change(screen.getByLabelText("Start (seconds)"), { target: { value: "11" } });
    fireEvent.click(screen.getByRole("button", { name: /Save changes/ }));
    await screen.findByText(/Trim saved as a new clip/);
    await waitFor(() => expect(screen.getByRole("button", { name: "Trash · 1" })).toBeTruthy());
    expect(requests[0]).toEqual({ path: "/api/assets/clip-a/trim", body: { start_us: 11000000, end_us: 15000000, expected_revision: 2, expected_lifecycle_revision: 0 } });
    fireEvent.click(screen.getByRole("button", { name: "Trash · 1" }));
    expect(screen.getByText("Previous trim")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Restore" }));
    await waitFor(() => expect(screen.getByText("Trash is empty.")).toBeTruthy());
    expect(requests.at(-1)?.body.expected_lifecycle_revision).toBe(1);
  });
  it("requires candidate preview and explicit Add clip, preserving candidate provenance", async () => {
    candidates = [{ id: "candidate-one", start_us: 31000000, end_us: 36000000, status: "proposed" }];
    render(<App />); await openWorkspace();
    expect(screen.getByText(/It can miss shots or include other movement/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Preview & adjust" }));
    expect(requests).toHaveLength(0);
    expect((screen.getByLabelText("Start (seconds)") as HTMLInputElement).value).toBe("31");
    fireEvent.click(screen.getByRole("button", { name: /Add clip/ }));
    await waitFor(() => expect(requests).toHaveLength(1));
    expect(requests[0].body).toEqual({ start_us: 31000000, end_us: 36000000, candidate_id: "candidate-one" });
  });
  it("returns to the source collection after review with the source context visible", async () => {
    render(<App />); await openWorkspace();
    fireEvent.click(screen.getAllByRole("button", { name: "Open review ↗" })[0]);
    const navigation = screen.getByRole("navigation", { name: "Current workflow" });
    expect(within(navigation).getByText("Saturday practice.mp4")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Analyze this shot/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "← Manage clips" }));
    expect(await screen.findByRole("checkbox", { name: "Select Shot 1" })).toBeTruthy();
  });
  it("exposes cancellation during first-video processing before any clip exists", async () => {
    clips = [];
    videos[0] = { ...videos[0], status: "processing", preview_url: null };
    jobs = [{ id: "import-job", kind: "video_import", status: "running", stage: "preparing_video", payload: { video_id: "training" } }];
    render(<App />); await openWorkspace();
    expect(screen.getByText("Preparing video")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cancel processing" }));
    await waitFor(() => expect(requests).toHaveLength(1));
    expect(requests[0].path).toBe("/api/jobs/import-job/cancel");
  });
  it("shows scan failure separately from zero candidates while manual marking remains usable", async () => {
    scanState = { scan_status: "failed", scan_error: "pose_model_missing" };
    render(<App />); await openWorkspace();
    expect(screen.getByRole("alert").textContent).toContain("The candidate scan failed");
    expect(screen.getByRole("alert").textContent).toContain("Manual marking is still available");
    expect((screen.getByRole("button", { name: /Add clip/ }) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByText("Scan complete; no candidates found. Mark shots manually.")).toBeNull();
  });
  it("clears a legacy trim draft when previewing another clip", async () => {
    videos[0] = { ...videos[0], kind: "legacy", preview_url: null };
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Manage clips · Imported shots/ }));
    fireEvent.click((await screen.findAllByRole("button", { name: "Edit clip" }))[0]);
    expect(screen.getByLabelText("Clip name")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Preview Shot 2" }));
    expect(screen.queryByLabelText("Clip name")).toBeNull();
    expect(screen.getByLabelText("Source video", { selector: "video" }).getAttribute("src")).toBe("/api/assets/clip-b/preview");
    expect(requests).toHaveLength(0);
  });

  it("does not attach comparison actions to an unrelated review in the clip manager", async () => {
    render(<App />); await openWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    const dialog = screen.getByRole("dialog", { name: "Settings" });
    expect(within(dialog).getByText("Open a clip review to choose its personal reference and update its comparison.")).toBeTruthy();
    expect(within(dialog).queryByRole("combobox", { name: "Compare with another of your shots" })).toBeNull();
    expect(within(dialog).queryByRole("button", { name: "Update comparison" })).toBeNull();
    expect(within(dialog).getByRole("combobox", { name: "Pose comparison target" })).toBeTruthy();
  });

  it("keeps oversized local batches within the API's 30-clip limit", async () => {
    clips = Array.from({ length: 31 }, (_, index) => makeClip(`clip-${index}`, `Shot ${index + 1}`));
    render(<App />); await openWorkspace();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select all visible" }));
    expect((screen.getByRole("button", { name: /Analyze selected/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Select up to 30 clips for one local analysis batch.")).toBeTruthy();
    expect(requests).toHaveLength(0);
  });
  it("translates completed action feedback when the interface language changes", async () => {
    render(<App />); await openWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Move to trash · Shot 1" }));
    await screen.findByText("Clip moved to trash.");
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    fireEvent.click(screen.getByRole("button", { name: "中文" }));
    fireEvent.click(screen.getByRole("button", { name: "关闭设置" }));
    expect(screen.getByText("片段已移到回收站。")).toBeTruthy();
    expect(screen.queryByText("Clip moved to trash.")).toBeNull();
  });

});
