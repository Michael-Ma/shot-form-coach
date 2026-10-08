import { useEffect, useRef, useState } from "react";

type Point = { x: number; y: number; visibility: number };
type Frame = {
  frame_id: string;
  frame_index: number;
  time_us: number;
  source_time_us: number;
  source_frame_index: number | null;
};
type TrackFrame = {
  person_box: number[] | null;
  landmarks: Point[] | null;
  ball: { x: number; y: number; radius_px: number; score: number } | null;
  width: number;
  height: number;
};
type Metric = {
  key: string;
  value: number | null;
  unit: string;
  reason: string | null;
  evidence_frame_ids: string[];
};
type Phase = {
  range_us: number[];
  frame_range: number[];
  source: string;
  quality: string;
};
type Finding = {
  id: string;
  cue_id: string;
  evidence_frame_ids: string[];
  kind: string;
};
type Report = {
  id: string;
  locale: string;
  asset_revision: number;
  findings: Finding[];
  comparison: {
    status: string;
    reason: string;
    differences: { key: string; difference: number; unit: string }[];
  };
  sources: { id: string; url: string; title?: string }[];
};
type Asset = {
  id: string;
  label: string;
  revision: number;
  width: number;
  height: number;
  duration_us: number;
  status: string;
  preview_url: string;
  frame_index: Frame[];
  phases: Record<string, Phase | null>;
  measurements?: {
    curve: { time_us: number; wrist_height: number | null }[];
    measurements: Metric[];
    flags: string[];
    side: string;
    visible_frames: number;
    total_frames: number;
  };
  report: Report | null;
  report_request?: { reference_asset_id?: string };
  model_error?: string;
  analysis_config?: { mode: string };
  model_assist?: {
    observations: {
      attribute: string;
      interpretation: string;
      evidence_frame_ids: string[];
    }[];
  };
};
type Job = {
  id: string;
  kind: string;
  status: string;
  stage: string;
  completed?: number;
  total?: number;
  progress: { frames?: number; total_frames?: number };
  error_code?: string;
  errors: { code: string }[];
  receipts: {
    status: string;
    cost: { estimated_usd: number | null; status: string };
  }[];
};
const EN: Record<string, string> = {
  title: "Shot Form Coach",
  focus: "Focus on movement",
  subtitle: "Observe a movement. Test one change.",
  session: "Your shots",
  import: "Import a clip",
  workbench: "Import Workbench clips",
  empty: "Import a shooting clip to begin.",
  review: "Movement review",
  loading: "Loading…",
  analyze: "Analyze this shot",
  all: "Analyze all shots",
  local: "Local vision",
  gemini: "Gemini",
  astra_codex: "Astra (Codex)",
  astra_api: "Astra (API)",
  codexHint: "Uses your signed-in Codex plan and its usage limits.",
  apiHint: "Uses the configured API key; billed by the provider.",
  codex_not_installed: "Codex is not installed or cannot run.",
  codex_needs_update: "Update Codex to a recent version, then restart.",
  codex_login_required: "Sign in to Codex with ChatGPT, then restart the app.",
  openai_key_missing: "The OpenAI API key is not configured.",
  codexPlan: "Codex plan usage",
  modelReview: "Model observations",
  follow_through: "Follow-through",
  rhythm: "Rhythm",
  model_visibility: "Visibility",
  visible_change: "Visible change",
  repeatable: "Appears steady within these frames",
  uncertain: "Uncertain",
  mode: "Analysis method",
  hand: "Shooting hand",
  auto: "Estimate",
  right: "Right",
  left: "Left",
  view: "Camera view",
  oblique: "Oblique",
  side: "Side",
  front: "Front",
  unknown: "Unknown",
  shot: "Shot context",
  stationary_jump_shot: "Stationary jump shot",
  set_shot: "Set shot",
  comparator: "Compare with your own shot",
  noReference: "Teaching schematic only",
  reference_unanalyzed: "Analyze this comparator first.",
  sameView: "These clips use the same fixed camera view",
  report: "Update comparison & exports",
  exports: "Export this review",
  text: "Written review",
  image: "Comparison image",
  video: "Slow-motion video",
  json: "Evidence JSON",
  release: "Release interval",
  candidate: "Automatic candidate",
  reviewed: "Reviewed interval",
  notKnown: "Contact is not clear enough to propose an interval.",
  phaseHelp:
    "Optional: step to the last contact, then the first clear separation. Save both frames.",
  last: "Last contact",
  first: "First clear separation",
  save: "Save interval & rebuild",
  reset: "Reset selection",
  source: "Source",
  clip: "Clip",
  frame: "Frame",
  prev: "Previous frame",
  next: "Next frame",
  play: "Play",
  pause: "Pause",
  pose: "Pose overlay",
  ball: "Ball candidate",
  projection: "Visible projection",
  metrics: "What is visible",
  cue: "One thing to try",
  repeatable_finish:
    "After release, let your fingertips continue toward the chosen target with a relaxed finish. Review a set from a comfortable distance.",
  coordinated_rise:
    "Try a comfortable, continuous rise and ball lift; compare attempts at the same location.",
  hypothesis: "Practice hypothesis · verify with a matched retest",
  limits:
    "A visible difference does not establish a technical fault or explain a miss.",
  schematic: "Original teaching schematic",
  schematicNote: "Illustration of a finish cue; no measured Curry motion.",
  noMetrics: "Analyze the clip to see movement evidence.",
  wrist_height_early: "Early wrist height",
  wrist_height_late: "Later wrist height",
  arm_lowering: "Wrist-height change",
  elbow_extension_change: "Projected elbow change",
  loading_to_release: "Loading → release",
  torso_lengths: "body lengths",
  degrees_projection: "projected °",
  milliseconds: "ms",
  release_unknown: "Release is not sufficiently visible.",
  track_gaps: "Required body points are not visible in enough frames.",
  post_context_short: "Not enough later follow-through in this clip.",
  handedness_uncertain: "Check the estimated shooting side.",
  ball_not_visible: "Ball tracking is incomplete.",
  loading_unknown: "Loading phase is not available.",
  context_mismatch: "The shot type or camera view differs.",
  handedness_mismatch: "The shooting hands differ.",
  view_unverified: "Matching camera view is not established.",
  select_reference: "Select a personal comparator to compare this attribute.",
  same_view_assumed: "Comparison assumes a matching fixed camera view.",
  jobs: "Activity",
  cancel: "Cancel",
  queued: "Queued",
  running: "Running",
  succeeded: "Complete",
  partial: "Complete with an issue",
  failed: "Failed",
  cancelled: "Cancelled",
  pose_and_ball: "Tracking body & ball",
  rendering: "Preparing your exports",
  model_assist: "Model review",
  starting: "Starting",
  complete: "Complete",
  retry: "You can correct the interval or try another clip.",
  usage: "Model calls",
  localCost: "Local processing · no model API charge",
  unknownCost: "Cost unknown",
  estimated: "Estimated",
  noKey: "Gemini requires a server API key.",
  missingModels:
    "Vision models are missing. Run the model download command in the README.",
  invalid_or_long_video: "Choose a readable video of at most 30 seconds.",
  workbench_import_failed:
    "Could not import this run. Check the configured Workbench data folder.",
  stale_revision: "This shot changed. Refresh and try again.",
  stale_reference_revision: "The comparator changed. Update the report again.",
  request_unknown: "The model response is unknown. It was not retried.",
  model_reply_invalid:
    "The model reply failed evidence validation. The local review remains available.",
  unresolved_request_blocks_resubmission:
    "An earlier model request is unresolved; another paid request is blocked.",
  empty_upload: "The selected file is empty.",
  api_key_missing: "Gemini is not configured.",
  revision: "Review version",
  evidence: "View evidence",
  visibility: "Frames with visible wrist",
  reportLanguage: "Export language",
  analyzing: "Analyzing",
  analysis_failed: "Analysis failed",
  ready: "Ready",
  analyzed: "Analyzed",
  busy: "Working…",
  costScope: "List-price estimate; actual billing may differ.",
  cameraHint: "Use a fixed camera and keep the full body and ball visible.",
  refs: "Teaching sources",
  curve: "Wrist height over the clip",
  sourceMap: "Original timeline retained",
  noFindings:
    "The required evidence is incomplete. Review the release interval and visibility.",
  modelTitle: "Gemini candidate",
  noLive: "Optional image-sequence review",
  upload_too_large: "The clip exceeds 512 MB.",
  not_analyzed: "Analyze the clip first.",
  invalid_reference: "Choose another analyzed shot.",
  duplicate_assets: "Each clip must be selected once.",
  model_call_budget_exhausted: "This selection exceeds the model-call limit.",
  interrupted_request_unknown:
    "The app stopped during a model call. Its outcome remains unknown.",
  worker_interrupted: "Processing stopped when the app closed.",
  self_reference: "Choose a different shot for comparison.",
};
const ZH: Record<string, string> = {
  title: "投篮动作复盘",
  focus: "放大动作区域",
  subtitle: "看清一个变化，检验一个调整。",
  session: "我的投篮",
  import: "导入投篮片段",
  workbench: "导入 Workbench 片段",
  empty: "先导入一次投篮，开始复盘。",
  review: "动作观察",
  loading: "加载中…",
  analyze: "分析这次投篮",
  all: "分析全部片段",
  local: "本地视觉",
  gemini: "Gemini",
  astra_codex: "Astra（Codex）",
  astra_api: "Astra（API）",
  codexHint: "使用当前 Codex 登录和订阅额度。",
  apiHint: "使用已配置的 API key，由模型服务商计费。",
  codex_not_installed: "未安装 Codex，或当前安装无法运行。",
  codex_needs_update: "请更新到较新的 Codex 版本后重新启动。",
  codex_login_required: "请通过 ChatGPT 登录 Codex 后重新启动。",
  openai_key_missing: "尚未配置 OpenAI API key。",
  codexPlan: "Codex 订阅额度",
  modelReview: "模型观察",
  follow_through: "随挥",
  rhythm: "节奏",
  model_visibility: "可见性",
  visible_change: "可见变化",
  repeatable: "这些帧中看起来较稳定",
  uncertain: "无法确定",
  mode: "分析方式",
  hand: "出手侧",
  auto: "自动估计",
  right: "右手",
  left: "左手",
  view: "拍摄视角",
  oblique: "斜侧",
  side: "侧面",
  front: "正面",
  unknown: "未知",
  shot: "投篮情境",
  stationary_jump_shot: "原地跳投",
  set_shot: "原地投篮",
  comparator: "选择自己的另一球作参照",
  noReference: "仅显示教学示意",
  reference_unanalyzed: "请先分析这个参照片段。",
  sameView: "这两个片段使用相同的固定视角",
  report: "更新对比和导出",
  exports: "导出这次复盘",
  text: "文字报告",
  image: "对比图片",
  video: "慢放对比视频",
  json: "证据 JSON",
  release: "离手区间",
  candidate: "自动候选",
  reviewed: "已复核区间",
  notKnown: "接触证据不足，暂时无法提出离手区间。",
  phaseHelp: "可选：逐帧选最后接触，再选首次明确离手，保存这两个时刻。",
  last: "最后接触",
  first: "首次明确离手",
  save: "保存区间并重算",
  reset: "清除选择",
  source: "源时间",
  clip: "片段",
  frame: "帧",
  prev: "上一帧",
  next: "下一帧",
  play: "播放",
  pause: "暂停",
  pose: "姿态叠加",
  ball: "球候选",
  projection: "可见画面投影",
  metrics: "看到了什么",
  cue: "试一个小调整",
  repeatable_finish:
    "离手后让指尖继续指向选定目标，保持自然放松的结束动作；做一组舒适距离投篮后再回看。",
  coordinated_rise: "尝试自然连贯的起身和举球，再比较相同位置的多次动作。",
  hypothesis: "训练假设 · 用同条件重拍检验",
  limits: "可见差异本身不证明技术错误，也不能解释未进原因。",
  schematic: "原创教学示意",
  schematicNote: "结束姿势提示示意，非库里实测动作。",
  noMetrics: "分析后可查看动作证据。",
  wrist_height_early: "较早的腕部高度",
  wrist_height_late: "较晚的腕部高度",
  arm_lowering: "腕部高度变化",
  elbow_extension_change: "投影肘部角度变化",
  loading_to_release: "下沉低点 → 离手",
  torso_lengths: "身体参考长度",
  degrees_projection: "投影度",
  milliseconds: "毫秒",
  release_unknown: "球与手的接触证据不足。",
  track_gaps: "足够多的帧中缺少所需身体点。",
  post_context_short: "片段缺少足够的后续随挥。",
  handedness_uncertain: "请检查估计的出手侧。",
  ball_not_visible: "球的跟踪不完整。",
  loading_unknown: "下沉阶段不可用。",
  context_mismatch: "投篮类型或视角不同。",
  handedness_mismatch: "出手侧不同。",
  view_unverified: "尚未确认两个视角可比。",
  select_reference: "选择个人比较样本，查看这个属性的差异。",
  same_view_assumed: "比较以相同固定视角为前提。",
  jobs: "处理记录",
  cancel: "取消",
  queued: "排队中",
  running: "处理中",
  succeeded: "已完成",
  partial: "已完成，部分结果需检查",
  failed: "处理失败",
  cancelled: "已取消",
  pose_and_ball: "跟踪人体与球",
  rendering: "生成报告与视频",
  model_assist: "模型辅助复盘",
  starting: "开始处理",
  complete: "完成",
  retry: "可以修正离手区间，或换一个片段。",
  usage: "模型调用",
  localCost: "本地处理 · 无模型 API 费用",
  unknownCost: "费用未知",
  estimated: "估算",
  noKey: "Gemini 需要在服务端配置 API key。",
  missingModels: "缺少视觉模型，请运行 README 中的模型下载命令。",
  invalid_or_long_video: "请选择可读取、30 秒以内的投篮片段。",
  workbench_import_failed: "无法导入这组片段，请检查 Workbench 数据目录配置。",
  stale_revision: "片段版本已变化，请刷新后重试。",
  stale_reference_revision: "参照片段已变化，请重新更新报告。",
  request_unknown: "模型返回结果未知，系统没有自动重试。",
  model_reply_invalid: "模型输出未通过证据校验，仍可使用本地观察结果。",
  unresolved_request_blocks_resubmission:
    "之前的模型请求结果未确认，已阻止新的付费请求。",
  empty_upload: "所选文件为空。",
  api_key_missing: "Gemini 尚未配置。",
  revision: "复盘版本",
  evidence: "查看证据",
  visibility: "腕部可见帧",
  reportLanguage: "导出语言",
  analyzing: "分析中",
  analysis_failed: "分析失败",
  ready: "待分析",
  analyzed: "已分析",
  busy: "处理中…",
  costScope: "按公开单价估算，实际账单可能不同。",
  cameraHint: "固定镜头，保持全身和球在画面内。",
  refs: "教学来源",
  curve: "片段内的腕部高度",
  sourceMap: "已保留原视频时间轴",
  noFindings: "所需证据不完整，请检查离手区间与可见性。",
  modelTitle: "Gemini 候选",
  noLive: "可选的图像序列复盘",
  upload_too_large: "片段超过 512 MB。",
  not_analyzed: "请先分析片段。",
  invalid_reference: "请选择另一个已分析片段。",
  duplicate_assets: "同一片段只能选择一次。",
  model_call_budget_exhausted: "所选片段超过模型调用上限。",
  interrupted_request_unknown: "程序在模型调用期间停止，结果仍未确认。",
  worker_interrupted: "程序退出时处理被中断。",
  self_reference: "请选择另一个片段作为参照。",
};
function crop(a: Asset, frames: TrackFrame[], enabled: boolean) {
  const boxes = frames.flatMap((f) => (f.person_box ? [f.person_box] : []));
  if (!enabled || !boxes.length) return [0, 0, a.width, a.height];
  const x0 = Math.min(...boxes.map((b) => b[0])),
    y0 = Math.min(...boxes.map((b) => b[1])),
    x1 = Math.max(...boxes.map((b) => b[2])),
    y1 = Math.max(...boxes.map((b) => b[3])),
    pad = (y1 - y0) * 0.28;
  return [
    Math.max(0, x0 - pad),
    Math.max(0, y0 - pad),
    Math.min(a.width, x1 + pad),
    Math.min(a.height, y1 + pad),
  ];
}
function cropStyle(a: Asset, b: number[]) {
  return {
    width: `${(a.width / (b[2] - b[0])) * 100}%`,
    height: `${(a.height / (b[3] - b[1])) * 100}%`,
    left: `${(-b[0] / (b[2] - b[0])) * 100}%`,
    top: `${(-b[1] / (b[3] - b[1])) * 100}%`,
  };
}
const edges = [
  [11, 12],
  [11, 13],
  [13, 15],
  [12, 14],
  [14, 16],
  [11, 23],
  [12, 24],
  [23, 24],
  [23, 25],
  [25, 27],
  [24, 26],
  [26, 28],
];
const anchor = (a: Asset) =>
  a.phases.release
    ? (a.phases.release.range_us[0] + a.phases.release.range_us[1]) / 2
    : null;
const nearest = (a: Asset, time: number) =>
  a.frame_index.reduce(
    (best, f, i) =>
      Math.abs(f.time_us - time) < Math.abs(a.frame_index[best].time_us - time)
        ? i
        : best,
    0,
  );
async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const r = await fetch("/api" + path, options);
  if (!r.ok) {
    let e;
    try {
      e = await r.json();
    } catch {
      e = { detail: "Request failed" };
    }
    throw Error(typeof e.detail === "string" ? e.detail : "invalid_request");
  }
  return r.json();
}
const post = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
function Pose({
  frame,
  show,
}: {
  frame: TrackFrame | undefined;
  show: boolean;
}) {
  if (!show || !frame) return null;
  const valid = (p: Point) =>
    p?.visibility >= 0.5 && p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1;
  return (
    <svg
      className="pose"
      viewBox={`0 0 ${frame.width} ${frame.height}`}
      aria-label="Pose and ball overlay"
    >
      {edges.map(([a, b]) =>
        frame.landmarks &&
        valid(frame.landmarks[a]) &&
        valid(frame.landmarks[b]) ? (
          <line
            key={`${a}-${b}`}
            x1={frame.landmarks[a].x * frame.width}
            y1={frame.landmarks[a].y * frame.height}
            x2={frame.landmarks[b].x * frame.width}
            y2={frame.landmarks[b].y * frame.height}
          />
        ) : null,
      )}
      {frame.landmarks?.map((p, i) =>
        valid(p) ? (
          <circle
            key={i}
            cx={p.x * frame.width}
            cy={p.y * frame.height}
            r={3}
          />
        ) : null,
      )}
      {frame.ball && (
        <circle
          className="ball"
          cx={frame.ball.x * frame.width}
          cy={frame.ball.y * frame.height}
          r={frame.ball.radius_px}
        />
      )}
    </svg>
  );
}
function Sketch({ t }: { t: (key: string) => string }) {
  return (
    <div className="sketch">
      <svg viewBox="0 0 320 280" aria-label={t("schematic")}>
        <path className="target" d="M240 49h48m-42 0 5 18h20l5-18" />
        <path className="flight" d="M120 63 Q192 -7 260 45" />
        <circle cx="126" cy="112" r="17" />
        <path d="M125 130 130 179 110 227 118 258m12-79 30 46 20 34M125 137 101 108 99 69 114 64m15 79 23-35 12-23" />
      </svg>
      <strong>{t("schematic")}</strong>
      <p>{t("schematicNote")}</p>
    </div>
  );
}
function Curve({
  asset,
  current,
  onSeek,
  t,
}: {
  asset: Asset;
  current: number;
  onSeek: (i: number) => void;
  t: (key: string) => string;
}) {
  const data = asset.measurements?.curve || [];
  const vals = data.filter((v) => v.wrist_height !== null);
  if (!vals.length) return null;
  const lo = Math.min(...vals.map((v) => v.wrist_height!)) - 0.1,
    hi = Math.max(...vals.map((v) => v.wrist_height!)) + 0.1;
  const x = (time: number) => 20 + (time / asset.duration_us) * 570,
    y = (value: number) => 100 - ((value - lo) / (hi - lo)) * 75;
  let path = "";
  let connected = false;
  for (const v of data) {
    if (v.wrist_height === null) {
      connected = false;
      continue;
    }
    path += `${connected ? "L" : "M"}${x(v.time_us)} ${y(v.wrist_height)} `;
    connected = true;
  }
  const phase = asset.phases.release;
  return (
    <div className="curve">
      <span>{t("curve")}</span>
      <svg
        viewBox="0 0 610 125"
        role="img"
        aria-label={t("curve")}
        onClick={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          onSeek(
            nearest(
              asset,
              Math.max(
                0,
                ((e.clientX - rect.left) / rect.width) * asset.duration_us,
              ),
            ),
          );
        }}
      >
        <line className="grid" x1="20" x2="590" y1="100" y2="100" />
        {phase && (
          <rect
            className="band"
            x={x(phase.range_us[0])}
            y="12"
            width={Math.max(4, x(phase.range_us[1]) - x(phase.range_us[0]))}
            height="88"
          />
        )}
        <path d={path} />
        <line
          className="cursor"
          x1={x(asset.frame_index[current]?.time_us || 0)}
          x2={x(asset.frame_index[current]?.time_us || 0)}
          y1="10"
          y2="105"
        />
        <text x="20" y="122">
          0s
        </text>
        <text x="550" y="122">
          {(asset.duration_us / 1e6).toFixed(1)}s
        </text>
      </svg>
    </div>
  );
}
export default function App() {
  const [lang, setLang] = useState(
    () => localStorage.getItem("sfc-lang") || "en",
  );
  const t = (k: string) => (lang === "zh" ? ZH : EN)[k] || EN[k] || k;
  const [assets, setAssets] = useState<Asset[]>([]),
    [selected, setSelected] = useState(""),
    [tracks, setTracks] = useState<TrackFrame[]>([]),
    [refTracks, setRefTracks] = useState<TrackFrame[]>([]),
    [reference, setReference] = useState(""),
    [sameView, setSameView] = useState(false),
    [jobs, setJobs] = useState<Job[]>([]),
    [health, setHealth] = useState<{
      gemini_configured: boolean;
      astra_api_configured: boolean;
      codex: { ready: boolean; reason: string | null };
      models_ready: boolean;
    }>(),
    [runs, setRuns] = useState<{ id: string; clip_count: number }[]>([]),
    [run, setRun] = useState("");
  const [focused, setFocused] = useState(true);
  const [index, setIndex] = useState(0),
    [playing, setPlaying] = useState(false),
    [showPose, setShowPose] = useState(true),
    [last, setLast] = useState<number | null>(null),
    [first, setFirst] = useState<number | null>(null),
    [mode, setMode] = useState("local"),
    [hand, setHand] = useState("auto"),
    [view, setView] = useState("oblique"),
    [shot, setShot] = useState("stationary_jump_shot"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const video = useRef<HTMLVideoElement>(null),
    refVideo = useRef<HTMLVideoElement>(null),
    upload = useRef<HTMLInputElement>(null);
  const chosen = assets.find((a) => a.id === selected),
    ref = assets.find((a) => a.id === reference);
  const active = jobs.some(
    (j) => j.status === "running" || j.status === "queued",
  );
  async function refresh() {
    const [a, j] = await Promise.all([
      api<Asset[]>("/assets"),
      api<Job[]>("/jobs"),
    ]);
    setAssets(a);
    setJobs(j);
    setSelected((s) => s || a[a.length - 1]?.id || "");
  }
  useEffect(() => {
    void refresh().catch((e) => setError(e.message));
    void api<typeof health>("/health").then(setHealth);
    void api<typeof runs>("/workbench/runs").then((r) => {
      setRuns(r);
      setRun(r[0]?.id || "");
    });
  }, []);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(
      () => void refresh().catch((e) => setError(e.message)),
      1200,
    );
    return () => clearInterval(timer);
  }, [active]);
  useEffect(() => {
    setIndex(0);
    setPlaying(false);
    setLast(null);
    setFirst(null);
    setReference(chosen?.report_request?.reference_asset_id || "");
    setTracks([]);
    if (selected)
      void api<{ frames: TrackFrame[] }>(`/assets/${selected}/tracks`)
        .then((r) => setTracks(r.frames))
        .catch(() => {});
  }, [selected]);
  useEffect(() => {
    if (chosen?.measurements && !tracks.length)
      void api<{ frames: TrackFrame[] }>(`/assets/${selected}/tracks`)
        .then((r) => setTracks(r.frames))
        .catch(() => {});
  }, [chosen?.measurements, tracks.length, selected]);
  useEffect(() => {
    setRefTracks([]);
    if (reference)
      void api<{ frames: TrackFrame[] }>(`/assets/${reference}/tracks`)
        .then((r) => setRefTracks(r.frames))
        .catch(() => {});
  }, [reference]);
  useEffect(() => {
    document.documentElement.lang = lang;
    localStorage.setItem("sfc-lang", lang);
  }, [lang]);
  const ownCrop = chosen ? crop(chosen, tracks, focused) : [0, 0, 1, 1],
    refCrop = ref ? crop(ref, refTracks, focused) : [0, 0, 1, 1];
  const ownAnchor = chosen ? anchor(chosen) : null,
    refAnchor = ref ? anchor(ref) : null,
    relative = chosen
      ? (chosen.frame_index[index]?.time_us || 0) -
        (ownAnchor ?? chosen.duration_us / 2)
      : 0,
    refIndex = ref
      ? nearest(ref, (refAnchor ?? ref.duration_us / 2) + relative)
      : 0;
  useEffect(() => {
    if (!refVideo.current || !ref) return;
    const target = ref.frame_index[refIndex].time_us / 1e6;
    if (Math.abs(refVideo.current.currentTime - target) > 0.04)
      refVideo.current.currentTime = target;
  }, [refIndex, reference]);
  async function action(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function analyze(ids: string[]) {
    await api("/analyses", {
      ...post({
        asset_ids: ids,
        config: {
          mode,
          handedness: hand,
          camera_view: view,
          shot_type: shot,
          locale: lang,
          max_model_calls: 6,
        },
      }),
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
    });
  }
  function seek(n: number) {
    if (!chosen) return;
    setPlaying(false);
    video.current?.pause();
    const i = Math.max(0, Math.min(chosen.frame_index.length - 1, n));
    setIndex(i);
    if (video.current)
      video.current.currentTime = chosen.frame_index[i].time_us / 1e6;
  }
  async function save() {
    if (!chosen || last === null || first === null) return;
    await api(`/assets/${chosen.id}/phases`, {
      ...post({
        expected_revision: chosen.revision,
        locale: lang,
        last_contact_frame: last,
        first_clear_frame: first,
      }),
      method: "PUT",
    });
    setLast(null);
    setFirst(null);
  }
  const report = chosen?.report;
  const ready = !!chosen?.measurements;
  const generating = active || busy;
  const validSave = last !== null && first !== null && last <= first;
  return (
    <>
      <header>
        <a className="brand" href="/">
          <span className="mark">↗</span>
          <div>
            <strong>{t("title")}</strong>
            <small>{t("subtitle")}</small>
          </div>
        </a>
        <div className="language" aria-label="Language">
          <button
            className={lang === "en" ? "selected" : ""}
            onClick={() => setLang("en")}
          >
            EN
          </button>
          <button
            className={lang === "zh" ? "selected" : ""}
            onClick={() => setLang("zh")}
          >
            中文
          </button>
        </div>
      </header>
      <main>
        <aside className="sidebar">
          <div className="section-title">
            <h2>{t("session")}</h2>
            <span className="count">{assets.length}</span>
          </div>
          <p className="muted">{t("cameraHint")}</p>
          <input
            type="file"
            accept="video/*"
            hidden
            ref={upload}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f)
                void action(async () => {
                  const form = new FormData();
                  form.append("file", f);
                  const a = await api<Asset>("/assets/upload", {
                    method: "POST",
                    body: form,
                  });
                  setSelected(a.id);
                  await analyze([a.id]);
                });
              e.target.value = "";
            }}
          />
          <button
            className="import"
            disabled={generating}
            onClick={() => upload.current?.click()}
          >
            ＋ {t("import")}
          </button>
          {runs.length > 0 && (
            <div className="workbench">
              <select
                aria-label={t("workbench")}
                value={run}
                onChange={(e) => setRun(e.target.value)}
              >
                {runs.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.id.slice(-8)} · {r.clip_count}
                  </option>
                ))}
              </select>
              <button
                disabled={generating || !run}
                onClick={() =>
                  void action(async () => {
                    const a = await api<Asset[]>(
                      "/workbench/import",
                      post({ run_id: run }),
                    );
                    if (a.length) {
                      setSelected(a[0].id);
                      await analyze(a.map((v) => v.id));
                    }
                  })
                }
              >
                {t("workbench")}
              </button>
            </div>
          )}
          <div className="shot-list">
            {assets
              .slice()
              .reverse()
              .map((a, n) => (
                <button
                  className={`shot ${selected === a.id ? "current" : ""}`}
                  key={a.id}
                  onClick={() => setSelected(a.id)}
                >
                  <img
                    src={`/api/assets/${a.id}/frames/${Math.min(10, a.frame_index.length - 1)}`}
                    alt=""
                  />
                  <span>
                    <strong>{a.label}</strong>
                    <small>
                      {t(a.status)} · {(a.duration_us / 1e6).toFixed(1)}s
                    </small>
                  </span>
                  <i>{String(n + 1).padStart(2, "0")}</i>
                </button>
              ))}
          </div>
          <div className="settings">
            <label>
              {t("mode")}
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="local">{t("local")}</option>
                <option value="gemini" disabled={!health?.gemini_configured}>
                  {t("gemini")}
                </option>
                <option value="astra_codex" disabled={!health?.codex.ready}>
                  {t("astra_codex")}
                </option>
                <option
                  value="astra_api"
                  disabled={!health?.astra_api_configured}
                >
                  {t("astra_api")}
                </option>
              </select>
            </label>
            {mode !== "local" && (
              <p className="muted">
                {t(mode === "astra_codex" ? "codexHint" : "apiHint")}
              </p>
            )}
            <div className="settings-row">
              <label>
                {t("hand")}
                <select value={hand} onChange={(e) => setHand(e.target.value)}>
                  {["auto", "right", "left"].map((v) => (
                    <option key={v} value={v}>
                      {t(v)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("view")}
                <select value={view} onChange={(e) => setView(e.target.value)}>
                  {["oblique", "side", "front", "unknown"].map((v) => (
                    <option key={v} value={v}>
                      {t(v)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label>
              {t("shot")}
              <select value={shot} onChange={(e) => setShot(e.target.value)}>
                {["stationary_jump_shot", "set_shot", "unknown"].map((v) => (
                  <option key={v} value={v}>
                    {t(v)}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="primary"
              disabled={generating || !chosen}
              onClick={() => void action(() => analyze([selected]))}
            >
              {t("analyze")}
            </button>
            <button
              disabled={generating || !assets.length}
              onClick={() =>
                void action(() => analyze(assets.map((a) => a.id)))
              }
            >
              {t("all")}
            </button>
            {!health?.models_ready && (
              <p className="notice">{t("missingModels")}</p>
            )}
          </div>
        </aside>
        <section className="workspace">
          {error && (
            <div className="error" role="alert">
              {t(error)}
            </div>
          )}
          {chosen ? (
            <>
              <div className="review-heading">
                <div>
                  <span className="eyebrow">{t("review")}</span>
                  <h1>{chosen.label}</h1>
                </div>
                <div>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={focused}
                      onChange={(e) => setFocused(e.target.checked)}
                    />
                    {t("focus")}
                  </label>
                  <span className="pill">
                    {t("revision")} {chosen.revision}
                  </span>
                </div>
              </div>
              <div className="viewers">
                <div className="viewer-block">
                  <div className="viewer-top">
                    <strong>{chosen.label}</strong>
                    <label className="check">
                      <input
                        type="checkbox"
                        checked={showPose}
                        onChange={(e) => setShowPose(e.target.checked)}
                      />
                      {t("pose")}
                    </label>
                  </div>
                  <div
                    className="viewer"
                    style={{
                      aspectRatio: `${ownCrop[2] - ownCrop[0]}/${ownCrop[3] - ownCrop[1]}`,
                    }}
                  >
                    <video
                      style={cropStyle(chosen, ownCrop)}
                      ref={video}
                      src={chosen.preview_url}
                      className={!playing ? "hidden-video" : ""}
                      playsInline
                      preload="metadata"
                      onEnded={() => setPlaying(false)}
                      onTimeUpdate={(e) => {
                        if (playing)
                          setIndex(
                            nearest(chosen, e.currentTarget.currentTime * 1e6),
                          );
                      }}
                    />
                    {!playing && (
                      <img
                        style={cropStyle(chosen, ownCrop)}
                        src={`/api/assets/${chosen.id}/frames/${index}`}
                        alt={`${chosen.label}, ${t("frame")} ${index}`}
                      />
                    )}
                    <div
                      className="overlay-space"
                      style={cropStyle(chosen, ownCrop)}
                    >
                      <Pose frame={tracks[index]} show={showPose} />
                    </div>
                  </div>
                  <div className="source-caption">
                    <span>
                      {t("source")}{" "}
                      {(
                        chosen.frame_index[index]?.source_time_us / 1e6
                      ).toFixed(3)}
                      s
                    </span>
                    <span>
                      {t("frame")}{" "}
                      {chosen.frame_index[index]?.source_frame_index ?? index}
                    </span>
                  </div>
                </div>
                <div className="viewer-block">
                  <div className="viewer-top">
                    <strong>{ref?.label || t("schematic")}</strong>
                    <span className="muted">
                      {ref && ownAnchor !== null && refAnchor !== null
                        ? `${relative / 1e6 >= 0 ? "+" : ""}${(relative / 1e6).toFixed(2)}s`
                        : ""}
                    </span>
                  </div>
                  {ref ? (
                    <>
                      <div
                        className="viewer"
                        style={{
                          aspectRatio: `${refCrop[2] - refCrop[0]}/${refCrop[3] - refCrop[1]}`,
                        }}
                      >
                        <video
                          style={cropStyle(ref, refCrop)}
                          className="hidden-video"
                          ref={refVideo}
                          src={ref.preview_url}
                          preload="metadata"
                          playsInline
                        />
                        <img
                          style={cropStyle(ref, refCrop)}
                          src={`/api/assets/${ref.id}/frames/${refIndex}`}
                          alt={`${ref.label}, ${t("frame")} ${refIndex}`}
                        />
                        <div
                          className="overlay-space"
                          style={cropStyle(ref, refCrop)}
                        >
                          <Pose frame={refTracks[refIndex]} show={showPose} />
                        </div>
                      </div>
                      <div className="source-caption">
                        <span>
                          {t("source")}{" "}
                          {(
                            ref.frame_index[refIndex]?.source_time_us / 1e6
                          ).toFixed(3)}
                          s
                        </span>
                        <span>
                          {t("frame")}{" "}
                          {ref.frame_index[refIndex]?.source_frame_index ??
                            refIndex}
                        </span>
                      </div>
                    </>
                  ) : (
                    <Sketch t={t} />
                  )}
                </div>
              </div>
              <div className="transport">
                <button
                  onClick={() => {
                    if (playing) {
                      video.current?.pause();
                      setPlaying(false);
                    } else {
                      setPlaying(true);
                      void video.current?.play().catch(() => setPlaying(false));
                    }
                  }}
                >
                  {t(playing ? "pause" : "play")}
                </button>
                <button aria-label={t("prev")} onClick={() => seek(index - 1)}>
                  ‹
                </button>
                <input
                  aria-label={t("frame")}
                  type="range"
                  min="0"
                  max={chosen.frame_index.length - 1}
                  value={index}
                  onChange={(e) => seek(Number(e.target.value))}
                />
                <button aria-label={t("next")} onClick={() => seek(index + 1)}>
                  ›
                </button>
                <span>
                  {(chosen.frame_index[index]?.time_us / 1e6).toFixed(2)}s
                </span>
              </div>
              <div className="phase-panel">
                <div className="section-title">
                  <h2>{t("release")}</h2>
                  <span
                    className={`pill ${chosen.phases.release?.source === "user_corrected" ? "" : "amber"}`}
                  >
                    {t(
                      chosen.phases.release?.source === "user_corrected"
                        ? "reviewed"
                        : "candidate",
                    )}
                  </span>
                </div>
                {chosen.phases.release ? (
                  <p className="interval">
                    {chosen.phases.release.range_us
                      .map((v) => (v / 1e6).toFixed(3))
                      .join(" – ")}
                    s <span className="muted">{t("clip")}</span>
                    <button
                      className="text-button"
                      onClick={() =>
                        seek(chosen.phases.release!.frame_range[0])
                      }
                    >
                      {t("evidence")} ↗
                    </button>
                  </p>
                ) : (
                  <p className="muted">
                    {ready ? t("notKnown") : t("noMetrics")}
                  </p>
                )}
                {ready && (
                  <>
                    <p className="muted">{t("phaseHelp")}</p>
                    <div className="phase-actions">
                      <button
                        className={last !== null ? "chosen" : ""}
                        onClick={() => {
                          setLast(index);
                          setPlaying(false);
                          video.current?.pause();
                        }}
                      >
                        {t("last")}
                        {last !== null ? ` · ${last}` : ""}
                      </button>
                      <button
                        className={first !== null ? "chosen" : ""}
                        onClick={() => {
                          setFirst(index);
                          setPlaying(false);
                          video.current?.pause();
                        }}
                      >
                        {t("first")}
                        {first !== null ? ` · ${first}` : ""}
                      </button>
                      <button
                        className="primary"
                        disabled={!validSave || generating}
                        onClick={() => void action(save)}
                      >
                        {t("save")}
                      </button>
                      {(last !== null || first !== null) && (
                        <button
                          className="text-button"
                          onClick={() => {
                            setLast(null);
                            setFirst(null);
                          }}
                        >
                          {t("reset")}
                        </button>
                      )}
                    </div>
                  </>
                )}
              </div>
              {ready && (
                <Curve asset={chosen} current={index} onSeek={seek} t={t} />
              )}
              <div className="comparison-controls">
                <label>
                  {t("comparator")}
                  <select
                    value={reference}
                    onChange={(e) => setReference(e.target.value)}
                  >
                    <option value="">{t("noReference")}</option>
                    {assets
                      .filter((a) => a.id !== selected)
                      .map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.label}
                          {!a.measurements ? " · " + t("ready") : ""}
                        </option>
                      ))}
                  </select>
                </label>
                {reference && (
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={sameView}
                      onChange={(e) => setSameView(e.target.checked)}
                    />
                    {t("sameView")}
                  </label>
                )}
                <button
                  disabled={
                    !ready || generating || !!(ref && !ref.measurements)
                  }
                  onClick={() =>
                    void action(async () => {
                      await api(
                        `/assets/${selected}/reports`,
                        post({
                          expected_revision: chosen.revision,
                          reference_asset_id: reference || null,
                          locale: lang,
                          assume_same_view: sameView,
                        }),
                      );
                    })
                  }
                >
                  {t("report")}
                </button>
                {ref && !ref.measurements && (
                  <p className="notice">{t("reference_unanalyzed")}</p>
                )}
              </div>
            </>
          ) : (
            <div className="empty">
              <span className="mark">↗</span>
              <h1>{t("title")}</h1>
              <p>{t("empty")}</p>
            </div>
          )}
        </section>
        <aside className="insights">
          <span className="eyebrow">{t("projection")}</span>
          <h2>{t("metrics")}</h2>
          {ready && chosen ? (
            <>
              <p className="muted">
                {t("visibility")} {chosen.measurements!.visible_frames}/
                {chosen.measurements!.total_frames}
              </p>
              <div className="metric-list">
                {chosen.measurements!.measurements.map((m) => (
                  <div key={m.key}>
                    <span>{t(m.key)}</span>
                    <strong>
                      {m.value === null
                        ? "—"
                        : m.value.toFixed(
                            m.unit === "milliseconds" ? 0 : 2,
                          )}{" "}
                      <small>{t(m.unit)}</small>
                    </strong>
                    {m.reason && <p>{t(m.reason)}</p>}
                    <button
                      className="text-button"
                      disabled={!m.evidence_frame_ids.length}
                      onClick={() => {
                        const n = chosen.frame_index.findIndex(
                          (f) => f.frame_id === m.evidence_frame_ids[0],
                        );
                        if (n >= 0) seek(n);
                      }}
                    >
                      {t("evidence")} ↗
                    </button>
                  </div>
                ))}
              </div>
              {chosen.measurements!.flags.length > 0 && (
                <div className="quality">
                  {chosen.measurements!.flags.map((f) => (
                    <p key={f}>{t(f)}</p>
                  ))}
                </div>
              )}
              {report?.comparison.differences.length ? (
                <div className="difference">
                  <h3>{t("comparator")}</h3>
                  {report.comparison.differences.map((d) => (
                    <p key={d.key}>
                      {t(d.key)}{" "}
                      <strong>
                        {d.difference >= 0 ? "+" : ""}
                        {d.difference.toFixed(2)}
                      </strong>{" "}
                      {t(d.unit)}
                    </p>
                  ))}
                </div>
              ) : (
                report && <p className="muted">{t(report.comparison.reason)}</p>
              )}
              {chosen.model_assist && (
                <div className="model-observations">
                  <h3>
                    {t("modelReview")} ·{" "}
                    {t(chosen.analysis_config?.mode || "unknown")}
                  </h3>
                  {chosen.model_assist.observations.map((o, i) => (
                    <div key={i}>
                      <p>
                        {t(
                          o.attribute === "visibility"
                            ? "model_visibility"
                            : o.attribute,
                        )}{" "}
                        · {t(o.interpretation)}
                      </p>
                      <button
                        className="text-button"
                        onClick={() => {
                          const frame = chosen.frame_index.findIndex(
                            (f) => f.frame_id === o.evidence_frame_ids[0],
                          );
                          if (frame >= 0) seek(frame);
                        }}
                      >
                        {t("evidence")} ↗
                      </button>
                    </div>
                  ))}
                </div>
              )}
              <div className="cue">
                <span className="eyebrow">{t("cue")}</span>
                <p>
                  {report?.findings[0]
                    ? t(report.findings[0].cue_id)
                    : t("noFindings")}
                </p>
                <small>{t("hypothesis")}</small>
              </div>
              <p className="limits">{t("limits")}</p>
              {chosen.model_error && (
                <p className="notice">{t(chosen.model_error)}</p>
              )}
              {report && (
                <>
                  <h3>{t("exports")}</h3>
                  <p className="muted">
                    {t("reportLanguage")}:{" "}
                    {report.locale === "zh" ? "中文" : "English"}
                  </p>
                  <div className="exports">
                    {["text", "image", "video", "json"].map((k) => (
                      <a
                        key={k}
                        href={`/api/reports/${report.id}/${k}`}
                        download
                      >
                        {t(k)} <span>↓</span>
                      </a>
                    ))}
                  </div>
                  <div className="sources">
                    <h3>{t("refs")}</h3>
                    {report.sources.map((s) => (
                      <a
                        key={s.id}
                        href={s.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {s.title || s.id} ↗
                      </a>
                    ))}
                  </div>
                </>
              )}
            </>
          ) : (
            <p className="muted">{t("noMetrics")}</p>
          )}
          <div className="activity">
            <h3>{t("jobs")}</h3>
            {jobs.slice(0, 4).map((j) => (
              <div className="job" key={j.id}>
                <strong>{t(j.status)}</strong>
                <span>{t(j.stage)}</span>
                {j.status === "running" &&
                  j.stage === "pose_and_ball" &&
                  j.progress.total_frames && (
                    <progress
                      value={j.progress.frames || 0}
                      max={j.progress.total_frames}
                    />
                  )}
                <small>
                  {j.completed ?? 0}
                  {j.total ? ` / ${j.total}` : ""}
                </small>
                {["running", "queued"].includes(j.status) && (
                  <button
                    onClick={() =>
                      void action(async () => {
                        await api(`/jobs/${j.id}/cancel`, post({}));
                      })
                    }
                  >
                    {t("cancel")}
                  </button>
                )}
                {j.error_code && <p className="notice">{t(j.error_code)}</p>}
                {j.errors.map((e, i) => (
                  <p className="notice" key={i}>
                    {t(e.code)}
                  </p>
                ))}
                {j.receipts.length > 0 ? (
                  <p className="cost">
                    {t("usage")}: {j.receipts.length}
                    <br />
                    {j.receipts.every(
                      (r) => r.cost.status === "subscription_usage",
                    )
                      ? t("codexPlan")
                      : j.receipts.some((r) => r.cost.estimated_usd === null)
                        ? t("unknownCost")
                        : `${t("estimated")} $${j.receipts.reduce((s, r) => s + (r.cost.estimated_usd || 0), 0).toFixed(5)}`}
                    <small>
                      {t(
                        j.receipts.every(
                          (r) => r.cost.status === "subscription_usage",
                        )
                          ? "codexHint"
                          : "costScope",
                      )}
                    </small>
                  </p>
                ) : (
                  <p className="cost">{t("localCost")}</p>
                )}
              </div>
            ))}
          </div>
        </aside>
      </main>
      <footer>
        {t("sourceMap")} <span>Shot Form Coach · V1</span>
      </footer>
    </>
  );
}
