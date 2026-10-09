import { useEffect, useRef, useState } from "react";

export type ManagedClip = {
  id: string; label: string; revision: number; lifecycle_revision?: number; duration_us: number; status: string; preview_url: string;
  session_id?: string; source_start_us?: number; source_end_us?: number; trashed_at?: string | null; superseded_by?: string | null;
  frame_index: { frame_index: number }[];
};
export type TrainingVideo = {
  id: string; label: string; filename?: string; duration_us: number; status: string; preview_url: string | null;
  kind: string; created_at?: string; clip_count: number; trashed_count: number; thumbnail_url?: string | null;
};
type Candidate = { id: string; start_us: number; end_us: number; peak_us?: number; status: string };
type VideoDetail = TrainingVideo & { clips: ManagedClip[]; candidates: Candidate[]; scan_status?: string; scan_error?: string; error_code?: string };
export type LifecycleJob = { id: string; kind: string; status: string; stage: string; payload?: { video_id?: string; asset_ids?: string[] }; cancel_requested?: boolean; progress?: { frames?: number; total_frames?: number; sampled_frames?: number; time_us?: number } };
const COPY: Record<string, [string, string]> = {
  library: ["Training videos", "训练视频"], import: ["Import video", "导入视频"],
  libraryTitle: ["One session. One change to practice.", "从一段训练，找到下一步。"],
  libraryHelp: ["Start with your full video, keep the shots you want, then review your movement.", "导入完整训练视频，整理想看的投篮，再逐球复盘动作。"],
  importHelp: ["Full videos or short clips · up to 60 minutes / 2 GB", "完整视频或短片段 · 最长 60 分钟 / 最大 2 GB"],
  stepImport: ["Import video", "导入视频"], stepClips: ["Manage clips", "整理片段"], stepReview: ["Review & practice", "复盘与练习"],
  collection: ["Your video library", "我的视频库"], videos: ["videos", "段视频"], clips: ["clips", "个片段"],
  open: ["Manage clips", "整理片段"], empty: ["Your first training video goes here.", "从第一段训练视频开始。"],
  emptyHelp: ["Keep the full body and ball visible. You can mark shots by hand or review local scan suggestions.", "尽量保留全身和篮球。可手动标记投篮，也可检查本地扫描提供的候选。"],
  source: ["Original video", "原始视频"], legacy: ["Imported clips", "已导入片段"],
  back: ["Back to videos", "返回视频库"], manageHelp: ["Keep one complete shot per clip, including the finish. Select only the clips you want to analyze.", "每段保留一次完整投篮及随挥。选中需要复盘的片段后再分析。"],
  sourceVideo: ["Source video", "原视频"], legacyHelp: ["This collection contains previously imported clips. Preview and trim each clip below; import the original video to find more shots.", "这组内容是之前导入的短片段。可在下方预览和裁剪；要查找更多投篮，请导入完整原视频。"],
  preparing: ["Preparing video preview…", "正在准备视频预览…"], prepareFailed: ["The video preview could not be prepared.", "视频预览准备失败。"], retry: ["Retry preview", "重试视频预览"],
  mark: ["Mark a shot", "标记一球"], edit: ["Edit clip", "编辑片段"], start: ["Start (seconds)", "开始（秒）"], end: ["End (seconds)", "结束（秒）"],
  setStart: ["Use current time as start", "用当前画面设为开始"], setEnd: ["Use current time as end", "用当前画面设为结束"],
  label: ["Clip name", "片段名称"], optionalName: ["Optional name", "可选名称"], create: ["Add clip", "添加片段"], save: ["Save changes", "保存修改"], cancel: ["Cancel edit", "取消编辑"],
  trimHelp: ["Times refer to the original video. Each clip can be up to 30 seconds.", "时间对应原视频；每个片段最长 30 秒。"],
  legacyTrimHelp: ["Times refer to the original video. This imported clip can only be trimmed within its existing boundaries.", "时间对应原视频；已导入片段只能在现有边界内裁剪。"],
  trimRange: ["Choose a start before the end, within the video, and at most 30 seconds apart.", "开始须早于结束，范围须在视频内，且不超过 30 秒。"],
  scanShort: ["Local suggestions · review before adding", "本地候选 · 确认后再添加"], scanFailed: ["The candidate scan failed. You can retry or mark clips manually.", "候选扫描未完成。可以重试，或继续手动标记。"], scanCancelled: ["Scan cancelled. Manual marking is still available.", "扫描已取消，仍可手动标记。"], scanEmpty: ["Scan complete; no candidates found. Mark shots manually.", "扫描已完成，未找到候选。请手动标记投篮。"], cancelJob: ["Cancel processing", "取消处理"], cancelling: ["Stopping after the current step…", "正在结束当前步骤…"],
  scan: ["Find shot candidates", "查找投篮候选"], scanNote: ["A local motion scan suggests moments to check. It can miss shots or include other movement. Review before adding.", "本地动作扫描会提出待检查的时间段，可能漏掉投篮或包含其他动作。请确认后再添加。"],
  scanning: ["Processing video…", "正在处理视频…"], candidates: ["Candidates to review", "待检查的候选"], candidate: ["Candidate", "候选"],
  check: ["Preview & adjust", "预览并调整"], dismiss: ["Dismiss", "忽略"], noCandidates: ["No pending candidates. Mark shots manually or run a local scan.", "暂无待检查候选。可以手动标记投篮，或运行本地扫描。"],
  organized: ["Your clips", "已整理的片段"], selected: ["selected", "个已选"], selectAll: ["Select all visible", "选择当前全部"], clear: ["Clear selection", "取消选择"],
  analyze: ["Analyze selected", "分析所选片段"], nextMethod: ["Analysis method", "分析方式"], settings: ["Change in Settings", "在设置中修改"],
  noClips: ["No clips yet. Mark one shot to start.", "还没有片段。先标记一次投篮。"], noTrash: ["Trash is empty.", "回收站为空。"],
  preview: ["Preview", "预览"], review: ["Open review", "查看复盘"], trash: ["Trash", "回收站"], trashAction: ["Move to trash", "移到回收站"], restore: ["Restore", "恢复"],
  moved: ["Clip moved to trash.", "片段已移到回收站。"], undo: ["Undo", "撤销"], restored: ["Clip restored.", "片段已恢复。"], saved: ["Clip saved. Select it when you are ready to analyze.", "片段已保存。准备好后，选中它进行分析。"],
  trimSaved: ["Trim saved as a new clip. The previous version is in Trash; analysis can be run on the new clip.", "裁剪已保存为新片段。旧版保留在回收站；可对新片段重新分析。"],
  olderVersion: ["Previous trim", "裁剪前版本"], selectionHint: ["Select a clip to enable analysis.", "先选择需要分析的片段。"], maxLocalBatch: ["Select up to 30 clips for one local analysis batch.", "每批本地分析最多选择 30 个片段。"], maxBatch: ["Select up to 6 clips for one model review batch.", "每批模型复盘最多选择 6 个片段。"],
  uploading: ["Importing your video…", "正在导入视频…"], loading: ["Loading your videos…", "正在加载视频…"], analysisStarted: ["Analysis queued. Open a clip to follow its review.", "分析已加入队列。打开片段可查看复盘进展。"],
};
export const lifecycleText = (lang: string, key: string) => COPY[key]?.[lang === "zh" ? 1 : 0] || key;
export function videoLabel(video: TrainingVideo, lang: string) {
  if (video.kind === "source") return video.label;
  const date = video.created_at ? new Date(video.created_at) : null;
  const day = date && !Number.isNaN(date.getTime()) ? new Intl.DateTimeFormat(lang === "zh" ? "zh-CN" : "en-US", { month: "short", day: "numeric" }).format(date) : "";
  return `${lang === "zh" ? "已导入的投篮" : "Imported shots"}${day ? ` · ${day}` : ""}`;
}
export const timeLabel = (us: number) => { const seconds = Math.max(0, us / 1e6); return `${Math.floor(seconds / 60)}:${(seconds % 60).toFixed(1).padStart(4, "0")}`; };
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init);
  const body = await response.json();
  if (!response.ok) throw Error(typeof body.detail === "string" ? body.detail : "invalid_request");
  return body;
}
const json = (body: unknown, method = "POST"): RequestInit => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

type Props = {
  lang: string; videos: TrainingVideo[]; assets: ManagedClip[]; videoId: string; loaded: boolean; busy: boolean; active: boolean;
  jobs: LifecycleJob[]; refreshVersion: number; modeLabel: string; canAnalyze: boolean; analysisProblem?: string; remoteMode: boolean;
  onOpenVideo: (id: string) => void; onBack: () => void; onReview: (asset: ManagedClip) => void;
  onSettings: () => void; run: (work: () => Promise<void>) => Promise<boolean>; onAnalyze: (ids: string[]) => Promise<boolean>;
  tStatus: (key: string) => string;
};
export default function Lifecycle(props: Props) {
  const { lang, videos, assets, videoId, loaded, busy, active, refreshVersion, run } = props;
  const t = (key: string) => lifecycleText(lang, key);
  const fileInput = useRef<HTMLInputElement>(null);
  const source = useRef<HTMLVideoElement>(null);
  const editSection = useRef<HTMLDivElement>(null);
  const [detail, setDetail] = useState<VideoDetail>();
  const [detailError, setDetailError] = useState("");
  const [checked, setChecked] = useState<string[]>([]);
  const [trash, setTrash] = useState(false);
  const [editing, setEditing] = useState<ManagedClip>();
  const [previewClip, setPreviewClip] = useState<ManagedClip>();
  const [candidate, setCandidate] = useState("");
  const [start, setStart] = useState("0");
  const [end, setEnd] = useState("3");
  const [label, setLabel] = useState("");
  const [playhead, setPlayhead] = useState(0);
  const [message, setMessage] = useState("");
  const [undo, setUndo] = useState<ManagedClip>();
  const [formError, setFormError] = useState(false);
  const refreshIdentity = `${videoId}:${refreshVersion}`;
  useEffect(() => {
    if (!videoId) { setDetail(undefined); return; }
    let live = true;
    setDetailError("");
    void request<VideoDetail>(`/videos/${encodeURIComponent(videoId)}?include_trashed=true`).then((value) => {
      if (live) { setDetail(value); setChecked((ids) => ids.filter((id) => value.clips.some((clip) => clip.id === id && !clip.trashed_at))); }
    }).catch((error: Error) => { if (live) setDetailError(error.message); });
    return () => { live = false; };
  }, [refreshIdentity, videoId]);
  useEffect(() => { setDetail(undefined); setEditing(undefined); setPreviewClip(undefined); setChecked([]); setTrash(false); setCandidate(""); setStart("0"); setEnd("3"); setLabel(""); setMessage(""); setUndo(undefined); setPlayhead(0); }, [videoId]);
  const isSource = detail?.kind === "source";
  const allClips = detail?.clips || [];
  const clips = allClips.filter((clip) => trash ? !!clip.trashed_at : !clip.trashed_at);
  const pending = (detail?.candidates || []).filter((item) => item.status === "proposed");
  const mediaClip = isSource ? undefined : previewClip || editing || allClips.find((clip) => !clip.trashed_at);
  const mediaUrl = isSource ? detail?.preview_url : mediaClip?.preview_url;
  const offset = mediaClip?.source_start_us || 0;
  const mediaStart = isSource ? 0 : mediaClip?.source_start_us || 0;
  const mediaEnd = isSource ? detail?.duration_us || 0 : mediaClip?.source_end_us || (mediaStart + (mediaClip?.duration_us || 0));
  const startUs = Math.round(Number(start) * 1e6), endUs = Math.round(Number(end) * 1e6);
  const lower = editing && !isSource ? editing.source_start_us || 0 : 0;
  const upper = editing && !isSource ? editing.source_end_us || lower + editing.duration_us : detail?.duration_us || 0;
  const valid = start.trim() !== "" && end.trim() !== "" && Number.isFinite(startUs) && Number.isFinite(endUs) && startUs >= lower && endUs <= upper && endUs > startUs && endUs - startUs <= 30000000;
  function jump(us: number) { if (source.current) { source.current.pause(); source.current.currentTime = Math.max(0, (us - offset) / 1e6); } setPlayhead(us); }
  function resetDraft() { setEditing(undefined); setCandidate(""); setLabel(""); setFormError(false); }
  function editClip(clip: ManagedClip) { setEditing(clip); setPreviewClip(clip); setCandidate(""); setStart(String((clip.source_start_us || 0) / 1e6)); setEnd(String((clip.source_end_us || (clip.source_start_us || 0) + clip.duration_us) / 1e6)); setLabel(clip.label); setFormError(false); if (isSource) jump(clip.source_start_us || 0); editSection.current?.scrollIntoView({ block: "center", behavior: "smooth" }); }
  function preview(clip: ManagedClip) { if (!isSource && editing?.id !== clip.id) resetDraft(); setPreviewClip(clip); if (isSource) jump(clip.source_start_us || 0); else setPlayhead(clip.source_start_us || 0); source.current?.scrollIntoView({ block: "center", behavior: "smooth" }); }
  async function importFile(file: File) {
    await run(async () => { const form = new FormData(); form.append("file", file); const result = await request<{ video: TrainingVideo; job: unknown }>("/videos/upload", { method: "POST", body: form }); props.onOpenVideo(result.video.id); });
  }
  async function saveClip() {
    if (!valid) { setFormError(true); return; }
    const success = await run(async () => {
      let saved: ManagedClip;
      if (editing) {
        const changed = startUs !== editing.source_start_us || endUs !== editing.source_end_us;
        saved = changed ? await request<ManagedClip>(`/assets/${editing.id}/trim`, json({ start_us: startUs, end_us: endUs, expected_revision: editing.revision, expected_lifecycle_revision: editing.lifecycle_revision || 0 }, "PUT")) : editing;
        if (label.trim() && saved.label !== label.trim()) saved = await request<ManagedClip>(`/assets/${saved.id}`, json({ label: label.trim(), expected_revision: saved.revision, expected_lifecycle_revision: saved.lifecycle_revision || 0 }, "PATCH"));
        setMessage(changed ? "trimSaved" : "saved");
      } else {
        saved = await request<ManagedClip>(`/videos/${videoId}/clips`, json({ start_us: startUs, end_us: endUs, ...(label.trim() ? { label: label.trim() } : {}), ...(candidate ? { candidate_id: candidate } : {}) }));
        setMessage("saved");
      }
      setChecked((ids) => [...ids.filter((id) => id !== editing?.id && id !== saved.id), saved.id]);
    });
    if (success) resetDraft();
  }
  async function moveToTrash(clip: ManagedClip) {
    await run(async () => { const changed = await request<ManagedClip>(`/assets/${clip.id}/trash`, json({ expected_revision: clip.revision, expected_lifecycle_revision: clip.lifecycle_revision || 0 })); setUndo(changed); setMessage("moved"); if (editing?.id === clip.id) resetDraft(); });
  }
  async function restore(clip: ManagedClip) {
    await run(async () => { await request(`/assets/${clip.id}/restore`, json({ expected_revision: clip.revision, expected_lifecycle_revision: clip.lifecycle_revision || 0 })); setUndo(undefined); setMessage("restored"); });
  }
  const activeJobs = props.jobs.filter((job) => ["running", "queued"].includes(job.status) && (!videoId || job.payload?.video_id === videoId || job.payload?.asset_ids?.some((id) => allClips.some((clip) => clip.id === id))));
  const processing = activeJobs.length > 0 ? <div className="lifecycle-progress-list">{activeJobs.map((job) => <div className="lifecycle-progress" key={job.id} role="status"><div><strong>{job.payload?.video_id ? (videos.find((item) => item.id === job.payload?.video_id)?.label || detail?.label || t("sourceVideo")) : t("organized")}</strong><span>{props.tStatus(job.stage)}</span></div><button disabled={busy || job.cancel_requested} onClick={() => void run(async () => { await request(`/jobs/${job.id}/cancel`, json({})); })}>{t(job.cancel_requested ? "cancelling" : "cancelJob")}</button><progress {...(job.progress?.total_frames ? { value: job.progress.frames || 0, max: job.progress.total_frames } : {})} /></div>)}</div> : null;
  const upload = <input ref={fileInput} type="file" accept="video/*" hidden aria-label={t("import")} onChange={(event) => { const file = event.target.files?.[0]; if (file) void importFile(file); event.target.value = ""; }} />;
  const importButton = <button className="primary import-video-button" disabled={busy} onClick={() => fileInput.current?.click()}><span aria-hidden="true">＋</span> {busy ? t("uploading") : t("import")}</button>;
  if (!videoId) return <div className="lifecycle library-view">{upload}
    <section className="library-hero"><div><span className="eyebrow">{t("library")}</span><h1>{t("libraryTitle")}</h1><p>{t("libraryHelp")}</p><div className="import-cta">{importButton}<small>{t("importHelp")}</small></div></div><ol className="flow-overview"><li><span>01</span><strong>{t("stepImport")}</strong></li><li><span>02</span><strong>{t("stepClips")}</strong></li><li><span>03</span><strong>{t("stepReview")}</strong></li></ol></section>
    {processing}<section className="video-collection" aria-labelledby="video-library-title"><div className="section-heading"><h2 id="video-library-title">{t("collection")}</h2><span className="count">{videos.length} {t("videos")}</span></div>
      {!loaded ? <p role="status">{t("loading")}</p> : !videos.length ? <div className="library-empty"><span aria-hidden="true">↗</span><h3>{t("empty")}</h3><p>{t("emptyHelp")}</p></div> : <div className="video-grid">{videos.map((item) => {
        const first = assets.find((asset) => asset.session_id === item.id);
        const thumbnail = item.thumbnail_url || (first ? `/api/assets/${first.id}/frames/0` : null);
        return <article className="video-card" key={item.id}><button className="video-card-open" onClick={() => props.onOpenVideo(item.id)} aria-label={`${t("open")} · ${videoLabel(item, lang)}`}><div className="video-card-image">{thumbnail ? <img src={thumbnail} alt="" loading="lazy" /> : <span className="video-placeholder" aria-hidden="true">▷</span>}<span className="duration-tag">{timeLabel(item.duration_us)}</span></div><div className="video-card-copy"><span className="eyebrow">{t(item.kind === "source" ? "source" : "legacy")}</span><h3>{videoLabel(item, lang)}</h3>{item.kind !== "source" && <small className="session-short-id">{lang === "zh" ? "批次" : "Collection"} {item.id.slice(-6)}</small>}<div className="video-card-meta"><span>{item.clip_count} {t("clips")}</span><span>{item.status === "processing" ? t("preparing") : item.status === "failed" ? t("prepareFailed") : t("open")} <span aria-hidden="true">↗</span></span></div></div></button></article>;
      })}</div>}
    </section>
  </div>;
  return <div className="lifecycle clip-workspace">{upload}<button className="text-button back-to-videos" onClick={props.onBack}>← {t("back")}</button>
    {detailError ? <div className="error" role="alert">{props.tStatus(detailError)}</div> : !detail ? <p role="status">{t("loading")}</p> : <>
      {processing}<div className="manage-heading"><div><span className="eyebrow">02 / {t("stepClips")}</span><h1>{videoLabel(detail, lang)}</h1><p>{t("manageHelp")}</p></div><span className="source-duration">{timeLabel(detail.duration_us)}<small>{t(isSource ? "source" : "legacy")}</small></span></div>
      <div className="clip-management-grid"><section className="source-panel" aria-label={t("sourceVideo")}><div className="source-panel-heading"><h2>{t("sourceVideo")}</h2><span className="mono">{timeLabel(playhead)}</span></div>
        {isSource && <div className="scan-primary-action"><button disabled={busy || active || detail.status !== "ready"} onClick={() => void run(async () => { await request(`/videos/${videoId}/scan`, json({})); })}>{detail.scan_status === "running" || detail.scan_status === "queued" ? t("scanning") : t("scan")} <span aria-hidden="true">↗</span></button><small>{t("scanShort")}{pending.length ? ` · ${pending.length} ${t("candidate")}` : ""}</small></div>}
        {!isSource && <p className="legacy-source-note">{t("legacyHelp")}</p>}
        {mediaUrl ? <><video className="source-player" ref={source} src={mediaUrl} controls playsInline preload="metadata" aria-label={t("sourceVideo")} onLoadedMetadata={() => { setPlayhead(offset); }} onTimeUpdate={(event) => setPlayhead(Math.round(event.currentTarget.currentTime * 1e6) + offset)} /><div className="source-range"><span>{timeLabel(mediaStart)}</span><span>{timeLabel(mediaEnd)}</span></div>{isSource && <div className="clip-timeline" aria-label={lang === "zh" ? "原视频中的片段位置" : "Clip positions in the source video"}>{allClips.filter((clip) => !clip.trashed_at).map((clip) => <button key={clip.id} title={`${clip.label} · ${timeLabel(clip.source_start_us || 0)}`} aria-label={`${t("preview")} ${clip.label}`} style={{ left: `${100 * (clip.source_start_us || 0) / detail.duration_us}%`, width: `${Math.max(.6, 100 * clip.duration_us / detail.duration_us)}%` }} onClick={() => preview(clip)} />)}</div>}</> : <div className="source-placeholder" role="status"><span aria-hidden="true">▷</span><p>{t(detail.status === "failed" ? "prepareFailed" : "preparing")}</p>{detail.error_code && <p className="notice">{props.tStatus(detail.error_code)}</p>}{detail.status === "failed" && <button disabled={busy || active} onClick={() => void run(async () => { await request(`/videos/${videoId}/prepare`, json({})); })}>{t("retry")}</button>}</div>}
        {(isSource || editing) && <div className="clip-editor" ref={editSection}><div className="section-heading"><h3>{t(editing ? "edit" : "mark")}{candidate ? ` · ${t("candidate")}` : ""}</h3>{(editing || candidate) && <button className="text-button" onClick={resetDraft}>{t("cancel")}</button>}</div><p>{t(isSource ? "trimHelp" : "legacyTrimHelp")}</p><div className="trim-inputs"><div><label htmlFor="clip-start">{t("start")}</label><input id="clip-start" type="number" step="0.1" min={lower / 1e6} max={upper / 1e6} value={start} onChange={(event) => setStart(event.target.value)} /><button className="text-button" disabled={!mediaUrl} onClick={() => setStart((playhead / 1e6).toFixed(3))}>{t("setStart")}</button></div><div><label htmlFor="clip-end">{t("end")}</label><input id="clip-end" type="number" step="0.1" min={lower / 1e6} max={upper / 1e6} value={end} onChange={(event) => setEnd(event.target.value)} /><button className="text-button" disabled={!mediaUrl} onClick={() => setEnd((playhead / 1e6).toFixed(3))}>{t("setEnd")}</button></div></div><label className="clip-name">{t("label")}<input value={label} placeholder={t("optionalName")} maxLength={120} onChange={(event) => setLabel(event.target.value)} /></label>{formError && !valid && <p className="notice" role="alert">{t("trimRange")}</p>}<button className="primary save-clip" disabled={busy || !mediaUrl} onClick={() => void saveClip()}>{t(editing ? "save" : "create")} <span aria-hidden="true">＋</span></button></div>}
        {isSource && <details className="scan-disclosure" open><summary>{t("candidates")} <span className="count">{pending.length}</span></summary><p>{t("scanNote")}</p>{detail.scan_status === "failed" && <p className="notice" role="alert">{t(detail.scan_error === "cancelled" ? "scanCancelled" : "scanFailed")} {detail.scan_error && detail.scan_error !== "cancelled" ? props.tStatus(detail.scan_error) : ""}</p>}{pending.length ? <ul className="candidate-list">{pending.map((item, index) => <li key={item.id}><div><strong>{t("candidate")} {index + 1}</strong><span>{timeLabel(item.start_us)} – {timeLabel(item.end_us)}</span></div><div><button onClick={() => { setEditing(undefined); setCandidate(item.id); setStart(String(item.start_us / 1e6)); setEnd(String(item.end_us / 1e6)); setLabel(""); setFormError(false); jump(item.start_us); editSection.current?.scrollIntoView({ block: "center", behavior: "smooth" }); }}>{t("check")}</button><button className="text-button" disabled={busy} onClick={() => void run(async () => { await request(`/videos/${videoId}/candidates/${item.id}/dismiss`, json({})); })}>{t("dismiss")}</button></div></li>)}</ul> : <p className="muted">{t(detail.scan_status === "succeeded" ? "scanEmpty" : "noCandidates")}</p>}</details>}
      </section>
      <section className="managed-clips" aria-labelledby="managed-clips-title"><div className="section-heading"><h2 id="managed-clips-title">{t(trash ? "trash" : "organized")}</h2><button className={`trash-toggle ${trash ? "selected" : ""}`} aria-pressed={trash} onClick={() => setTrash(!trash)}>{t(trash ? "organized" : "trash")} · {allClips.filter((clip) => trash ? !clip.trashed_at : !!clip.trashed_at).length}</button></div>
        {message && <div className="clip-feedback" role="status">{t(message)}{undo && <button className="text-button" disabled={busy} onClick={() => void restore(undo)}>{t("undo")}</button>}</div>}
        {!trash && <div className="selection-toolbar"><label className="check"><input type="checkbox" aria-label={t("selectAll")} checked={clips.length > 0 && clips.every((clip) => checked.includes(clip.id))} onChange={(event) => setChecked(event.target.checked ? clips.map((clip) => clip.id) : [])} />{checked.length} {t("selected")}</label>{checked.length > 0 && <button className="text-button" onClick={() => setChecked([])}>{t("clear")}</button>}</div>}
        {!clips.length ? <div className="clips-empty"><span aria-hidden="true">{trash ? "↶" : "＋"}</span><p>{t(trash ? "noTrash" : "noClips")}</p></div> : <ul className="managed-clip-list">{clips.map((clip) => <li key={clip.id} className={checked.includes(clip.id) && !trash ? "selected" : ""}>{!trash && <input type="checkbox" aria-label={`${lang === "zh" ? "选择" : "Select"} ${clip.label}`} checked={checked.includes(clip.id)} onChange={(event) => setChecked((ids) => event.target.checked ? [...ids, clip.id] : ids.filter((id) => id !== clip.id))} />}<button className="clip-thumb" onClick={() => preview(clip)} aria-label={`${t("preview")} ${clip.label}`}><img src={`/api/assets/${clip.id}/frames/${Math.max(0, Math.min(10, clip.frame_index.length - 1))}`} loading="lazy" alt="" /><span aria-hidden="true">▷</span></button><div className="managed-clip-info"><h3>{clip.label}</h3><p className="mono">{timeLabel(clip.source_start_us || 0)} – {timeLabel(clip.source_end_us || (clip.source_start_us || 0) + clip.duration_us)} <span>· {(clip.duration_us / 1e6).toFixed(1)}s</span></p><span className={`clip-state status-${clip.status}`}>{clip.superseded_by ? t("olderVersion") : props.tStatus(clip.status)}</span><div className="clip-actions">{trash ? <button disabled={busy} onClick={() => void restore(clip)}>{t("restore")}</button> : <><button className="open-review" onClick={() => props.onReview(clip)}>{t("review")} ↗</button><button disabled={busy || active} onClick={() => editClip(clip)}>{t("edit")}</button><button className="trash-clip" disabled={busy || clip.status === "analyzing"} onClick={() => void moveToTrash(clip)} aria-label={`${t("trashAction")} · ${clip.label}`}>{t("trashAction")}</button></>}</div></div></li>)}</ul>}
        {!trash && <div className="analyze-selection"><div><span>{t("nextMethod")} · <strong>{props.modeLabel}</strong></span><button className="text-button" onClick={props.onSettings}>{t("settings")} ↗</button></div><button className="primary" disabled={!checked.length || !props.canAnalyze || (checked.length > (props.remoteMode ? 6 : 30))} onClick={() => void props.onAnalyze(checked).then((success) => { if (success) setMessage("analysisStarted"); })}>{t("analyze")} <span>{checked.length}</span> ↗</button>{!checked.length ? <p>{t("selectionHint")}</p> : checked.length > (props.remoteMode ? 6 : 30) ? <p className="notice">{t(props.remoteMode ? "maxBatch" : "maxLocalBatch")}</p> : props.analysisProblem ? <p className="notice">{props.analysisProblem}</p> : null}</div>}
      </section></div>
    </>}
  </div>;
}
