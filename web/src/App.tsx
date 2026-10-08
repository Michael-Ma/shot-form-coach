import { useEffect, useRef, useState, type KeyboardEvent } from "react";

type Bilingual = { en: string; zh: string };
type CoachingIssue = {
  id: string; rubric_id: string; rank: number;
  severity: "high" | "medium" | "low"; confidence: "high" | "medium" | "low";
  title: Bilingual; observation: Bilingual; standard_gap: Bilingual;
  why_it_matters: Bilingual; action: Bilingual; drill: Bilingual;
  evidence_frame_ids: string[]; source_ids: string[]; basis: "measurement" | "model";
};
type Coaching = {
  version: string; assessment_source?: "model" | "measurements"; status: "reviewed" | "limited" | "awaiting_analysis";
  overall: { headline: Bilingual; summary: Bilingual };
  metrics: { id: string; label: Bilingual; display_value: Bilingual; interpretation: Bilingual; status: "measured" | "unavailable"; evidence_frame_ids: string[] }[];
  strengths: { title: Bilingual; detail: Bilingual; evidence_frame_ids: string[] }[];
  issues: CoachingIssue[];
  next_practice: { title: Bilingual; instruction: Bilingual; success_check: Bilingual };
  limitations: Bilingual[]; rubric_version: string;
};
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
  coaching?: Coaching;
  reference_id?: string | null;
  reference_revision?: number | null;
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
  coaching?: Coaching;
  report: Report | null;
  report_request?: { reference_asset_id?: string; assume_same_view?: boolean };
  model_error?: string;
  analysis_config?: { mode: string };
  model_assist?: {
    asset_revision?: number;
    coaching?: unknown;
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
const REVIEW_EN: Record<string, string> = {
  release_wrist_height: "Wrist height at release", release_wrist_above_face: "Wrist position above the face", release_elbow_angle: "Elbow angle at release", finish_above_shoulder_ms: "Visible raised-hand finish",
  release_interval_wide: "The release interval is too wide for a precise measurement.", finish_position_uncertain: "The shooting hand position is not clear enough.",
  movementSummary: "Movement summary", visualReview: "Visual coaching review", upgradeReview: "This is a movement summary. Choose Gemini or Astra, then analyze to add a broader review and practice priorities.", providerReady: "Available", reviewedInterval: "Reviewed interval",
  subtitle: "Know what to work on. Take it to your next session.",
  review: "Your shooting review", overview: "The takeaway", priorities: "What to work on first",
  priorityNote: "Ranked by training attention. Confidence describes how clearly this video supports the observation.",
  high: "First priority", medium: "Main focus", low: "Refine later", confidence: "Evidence confidence",
  confidence_high: "High", confidence_medium: "Medium", confidence_low: "Limited",
  observation: "In your shot", standardGap: "Teaching goal", why: "Why it matters", tryThis: "Try this",
  drill: "Practice drill", detail: "Reasoning & drill", nextPractice: "Your next practice", success: "What to check",
  strengths: "Keep doing", metrics: "Your movement, in numbers", metricsNote: "Measurements describe this clip. They are not a universal form score.",
  noIssues: "No supported correction to rank yet", noIssuesHelp: "A clear release and enough follow-through help identify a useful change. This is not a clean bill of technique.",
  limited: "Partial review", reviewed: "Review ready", awaiting_analysis: "Ready to analyze",
  reviewPending: "Let's look at this shot", reviewPendingHelp: "Analyze the clip to get a short review, your main practice priorities, and the frames behind them.",
  legacyHelp: "This clip has movement measurements. Run analysis to generate the new coaching review.",
  analyzingTitle: "Looking at your movement", analyzingHelp: "We are finding the shooting phases and preparing your review. You can keep browsing other shots.",
  evidenceSection: "See it in your shot", evidenceNote: "Play the movement, or jump directly to the frames behind a finding.",
  timeline: "Video position", releaseJump: "Go to release", slow: "Playback speed", currentShot: "This shot",
  selectedEvidence: "Showing the evidence for", reviewTools: "Frame tools & release correction",
  advanced: "Analysis settings", providers: "Model availability", methodHint: "Local vision measures movement. Gemini or Astra can add a visual coaching review.",
  uploadHint: "Up to 30 seconds · video only", moreImport: "Import from Workbench", noReference: "No comparison selected",
  comparator: "Compare with another of your shots", comparisonNote: "Your reference is a personal example, not an ideal or standard shot.",
  compare: "Update comparison", comparisonDraft: "The reference changed. Update the comparison to see matching results and exports.",
  comparisonLabel: "Saved comparison", noComparison: "Choose a reference to explore your consistency.",
  matchingRelease: "Aligned at release", approximateAlignment: "Approximate alignment · release not confirmed",
  refreshExports: "Prepare matching exports", exportPending: "Prepare exports for the current shot, reference, and language.",
  downloads: "Save or share this review", sourceDetail: "Teaching basis & review limits", raw: "Detailed measurements", rawHelp: "Projected measurements depend on camera angle and visible landmarks.",
  unavailable: "Not measurable", showEvidence: "Show this moment", returnReview: "Back to review", analyzingOther: "Processing your clips",
  fresh: "New review", report: "Prepare review & exports", modelReview: "Additional model observations",
  noShots: "Your next improvement starts with one shot.", emptyHelp: "Upload a short clip with your full body and the ball visible. We'll help you choose what to practice first.",
  import: "Add a shot", local: "Local vision", release: "Correct the release interval", details: "More details",
  referenceUsed: "Reference used", loadingShots: "Loading your shots…", setup: "Setup needed", exportsLanguage: "Saved export language",
};
const REVIEW_ZH: Record<string, string> = {
  release_wrist_height: "离手时腕部高度", release_wrist_above_face: "腕部高于面部的位置", release_elbow_angle: "离手时肘部投影角度", finish_above_shoulder_ms: "可见的抬手保持时长",
  release_interval_wide: "离手区间较宽，暂不能精确测量。", finish_position_uncertain: "投篮手的位置不够清楚。",
  movementSummary: "动作摘要", visualReview: "画面综合复盘", upgradeReview: "当前为动作摘要。选择 Gemini 或 Astra 后点击分析，可补充综合评价与练习重点。", providerReady: "可用", reviewedInterval: "已复核区间",
  subtitle: "看懂问题，把一个调整带到下次训练。",
  review: "这次投篮复盘", overview: "先看结论", priorities: "先练这几件事",
  priorityNote: "按训练关注优先级排序；证据把握表示这段视频能否清楚支持观察。",
  high: "优先改善", medium: "主要关注", low: "后续打磨", confidence: "证据把握",
  confidence_high: "较高", confidence_medium: "中等", confidence_low: "有限",
  observation: "你这一球", standardGap: "教学目标", why: "为什么值得关注", tryThis: "怎么调整",
  drill: "具体练法", detail: "展开依据与练法", nextPractice: "下一次这样练", success: "练完检查什么",
  strengths: "继续保持", metrics: "几个看得懂的动作数据", metricsNote: "这些数值描述这次动作，不代表统一的姿势评分。",
  noIssues: "目前还不能可靠地列出技术问题", noIssuesHelp: "清楚的离手过程和完整的随挥有助于找到调整方向。没有列出问题，并不代表动作已经达标。",
  limited: "部分可判断", reviewed: "复盘已就绪", awaiting_analysis: "等待分析",
  reviewPending: "来看看这次投篮", reviewPendingHelp: "分析后，你会看到整体评价、主要调整方向，以及支持判断的视频画面。",
  legacyHelp: "这段视频已有动作数据。重新分析后，可以生成新版综合复盘。",
  analyzingTitle: "正在观察你的动作", analyzingHelp: "正在识别投篮阶段并整理复盘。期间仍可查看其他投篮。",
  evidenceSection: "回到视频，看清这个动作", evidenceNote: "播放完整动作，也可以从问题卡片直接跳到对应画面。",
  timeline: "视频位置", releaseJump: "跳到离手", slow: "播放速度", currentShot: "这一球",
  selectedEvidence: "当前查看", reviewTools: "逐帧工具与离手修正",
  advanced: "分析设置", providers: "模型可用情况", methodHint: "本地视觉测量动作；Gemini 或 Astra 可补充画面复盘。",
  uploadHint: "30 秒以内 · 视频片段", moreImport: "从 Workbench 导入", noReference: "暂不对比",
  comparator: "和自己的另一球对比", comparisonNote: "参照是你自己的一个样本，不会被当作标准或理想动作。",
  compare: "更新对比", comparisonDraft: "参照已变化。更新对比后，再查看对应结果与导出文件。",
  comparisonLabel: "当前已保存的对比", noComparison: "选一球作参照，看看自己的动作是否一致。",
  matchingRelease: "按离手时刻对齐", approximateAlignment: "近似对齐 · 离手尚未确认",
  refreshExports: "准备对应导出文件", exportPending: "为当前投篮、参照和语言准备导出文件。",
  downloads: "保存或分享这次复盘", sourceDetail: "教学依据与判断范围", raw: "查看详细测量", rawHelp: "画面投影测量受拍摄视角和关键点可见性影响。",
  unavailable: "暂无法测量", showEvidence: "看这个动作", returnReview: "回到评价", analyzingOther: "正在处理投篮片段",
  fresh: "本次复盘", report: "生成复盘与导出", modelReview: "模型补充观察",
  noShots: "从一球开始，找到下一步。", emptyHelp: "上传一个能看清全身和篮球的短片段，先找到最值得练习的调整。",
  import: "添加投篮", local: "本地视觉", release: "修正离手区间", details: "更多细节",
  referenceUsed: "使用的参照", loadingShots: "正在加载你的投篮…", setup: "需要配置", exportsLanguage: "已保存报告语言",
};
const SETTINGS_EN: Record<string, string> = {
  settingsTitle: "Settings", settingsHelp: "Everything you need for your next review.", closeSettings: "Close settings", doneSettings: "Back to review",
  analysisSection: "Analysis", importSection: "Add shots", comparisonSection: "Comparison", playbackSection: "Playback", languageSection: "Language",
  nextAnalysis: "These choices apply when you next analyze. Changing a setting does not rerun a review.",
  selectedMethod: "Next analysis", configureAnalysis: "Choose in Settings", uploadAnalyze: "Choose a video & analyze", importAnalyze: "Import & analyze",
  importMethod: "New clips will be analyzed with", fromDevice: "From this device", fromDeviceHelp: "Choose a short video containing one complete shot.",
  workbench: "Import pre-cut shots", workbenchHelp: "From Video Event Workbench: imports shooting clips from completed runs and keeps their original video times. It is not another analysis model.",
  workbenchWhen: "Use this if you have already split a longer video into shots in Workbench. Otherwise, choose a video above.",
  workbenchRun: "Completed Workbench run", workbenchClips: "clips", workbenchUnconfigured: "Workbench is not connected. You can still add a video from this device.",
  workbenchEmpty: "No completed runs with clips are available yet.", workbenchLoading: "Checking completed Workbench runs…", workbenchLoadError: "Could not load Workbench runs. Try again.", reloadRuns: "Check again",
  settingsSaved: "Preferences are saved in this browser.", playbackHelp: "These preferences apply immediately to the video preview.",
  languageHelp: "Changes the interface and the language used for your next report export.",
  comparisonScope: "For the selected shot", comparisonEmpty: "Add a shot first, then choose a personal reference here.",
  referenceMissing: "Add another shot to compare your movement.", noReferenceHelp: "Choose a reference in Settings to view your shots side by side.",
  settingsEmpty: "Open Settings to add your first shot", playbackNow: "Playback", comparisonResults: "Personal comparison",
};
const SETTINGS_ZH: Record<string, string> = {
  settingsTitle: "设置", settingsHelp: "下一次复盘需要的选项，都在这里。", closeSettings: "关闭设置", doneSettings: "回到复盘",
  analysisSection: "分析", importSection: "添加投篮", comparisonSection: "对比", playbackSection: "播放", languageSection: "语言",
  nextAnalysis: "这些选项用于下一次分析。修改设置不会自动重新分析。",
  selectedMethod: "下次分析", configureAnalysis: "在设置中选择", uploadAnalyze: "选择视频并分析", importAnalyze: "导入并分析",
  importMethod: "新片段将使用以下方式分析", fromDevice: "从电脑选择视频", fromDeviceHelp: "选择一个包含完整投篮动作的短视频。",
  workbench: "导入已截好的投篮", workbenchHelp: "来自 Video Event Workbench：读取已完成任务中的投篮短片段，并保留原视频时间；不是另一种分析模型。",
  workbenchWhen: "如果你已经用 Workbench 把长视频截成一球一段，可以从这里导入；否则直接在上方选择视频即可。",
  workbenchRun: "已完成的 Workbench 任务", workbenchClips: "个片段", workbenchUnconfigured: "尚未连接 Workbench，仍可直接从电脑添加视频。",
  workbenchEmpty: "暂时没有包含投篮片段的已完成任务。", workbenchLoading: "正在查找已完成的 Workbench 任务…", workbenchLoadError: "暂时无法读取 Workbench 任务，请重试。", reloadRuns: "重新查找",
  settingsSaved: "偏好设置已保存在当前浏览器。", playbackHelp: "这些选项会立即应用到视频预览。",
  languageHelp: "切换界面语言，同时用于下一次生成的报告。",
  comparisonScope: "用于当前投篮", comparisonEmpty: "添加投篮后，可在这里选择自己的参照球。",
  referenceMissing: "再添加一球，就可以比较自己的动作。", noReferenceHelp: "在设置中选择参照球，可并排回看自己的动作。",
  settingsEmpty: "打开设置，添加第一球", playbackNow: "播放", comparisonResults: "个人动作对比",
};
function savedChoice(key: string, allowed: string[], fallback: string) {
  try { const value = localStorage.getItem(key); return value && allowed.includes(value) ? value : fallback; } catch { return fallback; }
}
function savePreference(key: string, value: string) {
  try { localStorage.setItem(key, value); } catch { /* The app still works when browser storage is unavailable. */ }
}
function keepSettingsFocus(event: KeyboardEvent<HTMLDialogElement>) {
  if (event.key !== "Tab" || event.altKey || event.ctrlKey || event.metaKey) return;
  const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>("a[href], button, input:not([type=hidden]), select, textarea, summary, [tabindex]"))
    .filter((element) => element.tabIndex >= 0 && !element.matches(":disabled") && element.getClientRects().length > 0 && getComputedStyle(element).visibility !== "hidden");
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (!first || !last) return;
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault(); last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault(); first.focus();
  }
}
export default function App() {
  const [lang, setLang] = useState(() => savedChoice("sfc-lang", ["en", "zh"], "en"));
  const t = (k: string) => (lang === "zh" ? SETTINGS_ZH : SETTINGS_EN)[k] || (lang === "zh" ? REVIEW_ZH : REVIEW_EN)[k] || (lang === "zh" ? ZH : EN)[k] || EN[k] || k;
  const cText = (value: Bilingual | undefined) => value ? value[lang === "zh" ? "zh" : "en"] || value.en || "" : "";
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selected, setSelected] = useState("");
  const [tracks, setTracks] = useState<TrackFrame[]>([]);
  const [refTracks, setRefTracks] = useState<TrackFrame[]>([]);
  const [reference, setReference] = useState("");
  const [sameView, setSameView] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [health, setHealth] = useState<{ gemini_configured: boolean; astra_api_configured: boolean; codex: { ready: boolean; reason: string | null }; models_ready: boolean; workbench_configured?: boolean }>();
  const [runs, setRuns] = useState<{ id: string; clip_count: number }[]>([]);
  const [run, setRun] = useState("");
  const [focused, setFocused] = useState(() => savedChoice("sfc-focus", ["true", "false"], "true") === "true");
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [showPose, setShowPose] = useState(() => savedChoice("sfc-pose", ["true", "false"], "false") === "true");
  const [last, setLast] = useState<number | null>(null);
  const [first, setFirst] = useState<number | null>(null);
  const [mode, setMode] = useState(() => savedChoice("sfc-mode", ["local", "gemini", "astra_codex", "astra_api"], "local"));
  const [hand, setHand] = useState(() => savedChoice("sfc-hand", ["auto", "right", "left"], "auto"));
  const [view, setView] = useState(() => savedChoice("sfc-view", ["oblique", "side", "front", "unknown"], "oblique"));
  const [shot, setShot] = useState(() => savedChoice("sfc-shot", ["stationary_jump_shot", "set_shot", "unknown"], "stationary_jump_shot"));
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [speed, setSpeed] = useState(() => savedChoice("sfc-speed", ["0.25", "0.5", "1"], "0.5"));
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [runsState, setRunsState] = useState<"loading" | "ready" | "error">("loading");
  const settingsDialog = useRef<HTMLDialogElement>(null);
  const settingsTrigger = useRef<HTMLButtonElement>(null);
  const settingsOpener = useRef<HTMLElement | null>(null);
  const settingsBody = useRef<HTMLDivElement>(null);
  function openSettings() {
    settingsOpener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setSettingsOpen(true);
  }
  function closeSettings() { setSettingsOpen(false); }
  async function loadRuns() {
    setRunsState("loading");
    try {
      const available = await api<typeof runs>("/workbench/runs");
      setRuns(available); setRun((value) => available.some((item) => item.id === value) ? value : available[0]?.id || "");
      setRunsState("ready");
    } catch { setRunsState("error"); }
  }
  const [evidenceLabel, setEvidenceLabel] = useState("");
  const video = useRef<HTMLVideoElement>(null);
  const upload = useRef<HTMLInputElement>(null);
  const evidenceSection = useRef<HTMLElement>(null);
  const summarySection = useRef<HTMLElement>(null);
  const chosen = assets.find((a) => a.id === selected);
  const ref = assets.find((a) => a.id === reference);
  const active = jobs.some((j) => ["running", "queued"].includes(j.status));
  const generating = active || busy;
  const analyzingChosen = chosen?.status === "analyzing";
  const ready = !!chosen?.measurements;
  const report = chosen?.report;
  const coaching = chosen?.coaching || (report?.asset_revision === chosen?.revision ? report?.coaching : undefined);
  const hasVisualReview = coaching?.assessment_source === "model";
  const issues = [...(coaching?.issues || [])].sort((a, b) => a.rank - b.rank).slice(0, 3);
  const reportReference = report?.reference_id ?? chosen?.report_request?.reference_asset_id ?? "";
  const reportMatches = !!report && report.asset_revision === chosen?.revision && reportReference === reference &&
    (!ref || report.reference_revision === ref.revision) &&
    (!reference || sameView === !!chosen?.report_request?.assume_same_view);
  const exportMatches = reportMatches && report?.locale === lang && !!report?.coaching && report.coaching.version === coaching?.version;
  const validSave = last !== null && first !== null && last <= first;
  async function refresh() {
    const [a, j] = await Promise.all([api<Asset[]>("/assets"), api<Job[]>("/jobs")]);
    setAssets(a); setJobs(j); setLoaded(true);
    setSelected((s) => a.some((v) => v.id === s) ? s : a[a.length - 1]?.id || "");
  }
  useEffect(() => {
    void refresh().catch((e) => { setError(e.message); setLoaded(true); });
    void api<typeof health>("/health").then(setHealth).catch((e) => setError(e.message));
    void loadRuns();
  }, []);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => void refresh().catch((e) => setError(e.message)), 1200);
    return () => clearInterval(timer);
  }, [active]);
  useEffect(() => {
    setIndex(0); setPlaying(false); setLast(null); setFirst(null); setEvidenceLabel("");
    setReference(chosen?.report_request?.reference_asset_id || "");
    setSameView(!!chosen?.report_request?.assume_same_view);
  }, [selected]);
  useEffect(() => {
    let live = true;
    setTracks([]);
    if (selected && ready) void api<{ frames: TrackFrame[] }>(`/assets/${selected}/tracks`).then((r) => { if (live) setTracks(r.frames); }).catch(() => {});
    return () => { live = false; };
  }, [selected, chosen?.revision, ready]);
  useEffect(() => {
    let live = true;
    setRefTracks([]);
    if (reference) void api<{ frames: TrackFrame[] }>(`/assets/${reference}/tracks`).then((r) => { if (live) setRefTracks(r.frames); }).catch(() => {});
    return () => { live = false; };
  }, [reference, ref?.revision]);
  useEffect(() => { document.documentElement.lang = lang; savePreference("sfc-lang", lang); setEvidenceLabel(""); }, [lang]);
  useEffect(() => { savePreference("sfc-mode", mode); }, [mode]);
  useEffect(() => { if (video.current) video.current.playbackRate = Number(speed); }, [speed, selected]);
  useEffect(() => {
    savePreference("sfc-hand", hand); savePreference("sfc-view", view); savePreference("sfc-shot", shot);
    savePreference("sfc-speed", speed); savePreference("sfc-focus", String(focused)); savePreference("sfc-pose", String(showPose));
  }, [hand, view, shot, speed, focused, showPose]);
  useEffect(() => {
    const dialog = settingsDialog.current;
    if (!dialog) return;
    if (settingsOpen) {
      dialog.showModal();
      if (settingsBody.current) settingsBody.current.scrollTop = 0;
      const previousOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => { document.body.style.overflow = previousOverflow; };
    }
    if (dialog.open) {
      dialog.close();
      (settingsOpener.current?.isConnected ? settingsOpener.current : settingsTrigger.current)?.focus();
    }
  }, [settingsOpen]);
  const ownCrop = chosen ? crop(chosen, tracks, focused) : [0, 0, 1, 1];
  const refCrop = ref ? crop(ref, refTracks, focused) : [0, 0, 1, 1];
  const ownAnchor = chosen ? anchor(chosen) : null;
  const refAnchor = ref ? anchor(ref) : null;
  const relative = chosen ? (chosen.frame_index[index]?.time_us || 0) - (ownAnchor ?? chosen.duration_us / 2) : 0;
  const refIndex = ref ? nearest(ref, (refAnchor ?? ref.duration_us / 2) + relative) : 0;
  async function action(fn: () => Promise<void>) {
    setBusy(true); setError("");
    try { await fn(); await refresh(); return true; } catch (e) { setError((e as Error).message); if (settingsBody.current) settingsBody.current.scrollTop = 0; return false; } finally { setBusy(false); }
  }
  async function analyze(ids: string[]) {
    await api("/analyses", { ...post({ asset_ids: ids, config: { mode, handedness: hand, camera_view: view, shot_type: shot, locale: lang, max_model_calls: 6 } }), headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() } });
  }
  function seek(n: number) {
    if (!chosen?.frame_index.length) return;
    setPlaying(false); video.current?.pause();
    const i = Math.max(0, Math.min(chosen.frame_index.length - 1, n));
    setIndex(i);
    if (video.current) video.current.currentTime = chosen.frame_index[i].time_us / 1e6;
  }
  const scrollBehavior = (): ScrollBehavior => window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ? "auto" : "smooth";
  function showEvidence(ids: string[], label: string) {
    if (!chosen) return;
    const n = chosen.frame_index.findIndex((f) => ids.includes(f.frame_id));
    if (n < 0) return;
    seek(n); setEvidenceLabel(label);
    evidenceSection.current?.scrollIntoView({ behavior: scrollBehavior(), block: "start" });
    evidenceSection.current?.focus({ preventScroll: true });
  }
  async function save() {
    if (!chosen || last === null || first === null) return;
    await api(`/assets/${chosen.id}/phases`, { ...post({ expected_revision: chosen.revision, locale: lang, last_contact_frame: last, first_clear_frame: first }), method: "PUT" });
    setLast(null); setFirst(null);
  }
  async function updateReport() {
    if (!chosen) return;
    await api(`/assets/${selected}/reports`, post({ expected_revision: chosen.revision, reference_asset_id: reference || null, locale: lang, assume_same_view: sameView }));
  }
  const evidenceButton = (ids: string[], label: string) => ids.length > 0 ? <button className="text-button evidence-link" onClick={() => showEvidence(ids, label)}>{t("showEvidence")} <span aria-hidden="true">↗</span></button> : null;
  const modeReady = mode === "local" || (mode === "gemini" ? !!health?.gemini_configured : mode === "astra_codex" ? !!health?.codex?.ready : !!health?.astra_api_configured);
  const modeProblem = mode === "gemini" ? "noKey" : mode === "astra_codex" ? health?.codex?.reason || "codex_not_installed" : "openai_key_missing";
  const canStart = !generating && health?.models_ready !== false && modeReady;
  const canAnalyze = canStart && !!chosen;
  const methodSelect = <label className="method-select">{t("mode")}<select value={mode} onChange={(e) => setMode(e.target.value)} disabled={generating}>
    <option value="local">{t("local")}</option><option value="gemini" disabled={!health?.gemini_configured}>{t("gemini")}{!health?.gemini_configured ? ` · ${t("setup")}` : ""}</option><option value="astra_codex" disabled={!health?.codex?.ready}>{t("astra_codex")}{!health?.codex?.ready ? ` · ${t("setup")}` : ""}</option><option value="astra_api" disabled={!health?.astra_api_configured}>{t("astra_api")}{!health?.astra_api_configured ? ` · ${t("setup")}` : ""}</option>
  </select></label>;
  return (
    <>
      <header className="app-header">
        <a className="brand" href="/"><span className="mark" aria-hidden="true">↗</span><div><strong>{t("title")}</strong><small>{t("subtitle")}</small></div></a>
        <button className="settings-trigger" ref={settingsTrigger} onClick={openSettings} aria-haspopup="dialog" aria-expanded={settingsOpen} aria-controls="settings-dialog"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M4 7h16M4 17h16M8 4v6M16 14v6" /></svg><span>{t("settingsTitle")}</span></button>
      </header>
      <main>
        <aside className="sidebar" aria-label={t("session")}>
          <div className="section-title"><h2>{t("session")}</h2><span className="count">{assets.length}</span></div>
          <nav className="shot-list" aria-label={t("session")}>
            {assets.slice().reverse().map((a) => <button className={`shot ${selected === a.id ? "current" : ""}`} aria-current={selected === a.id ? "true" : undefined} key={a.id} onClick={() => setSelected(a.id)}>
              <img src={`/api/assets/${a.id}/frames/${Math.max(0, Math.min(10, a.frame_index.length - 1))}`} alt="" loading="lazy" />
              <span><strong>{a.label}</strong><small>{t(a.status)} · {(a.duration_us / 1e6).toFixed(1)}s</small></span>
              {selected === a.id && <span className="shot-arrow" aria-hidden="true">↗</span>}
            </button>)}
          </nav>
        </aside>
        <div className="workspace">
          {error && !settingsOpen && <div className="error" role="alert">{t(error)}</div>}
          {!loaded ? <div className="empty" role="status">{t("loadingShots")}</div> : chosen ? <>
            <div className="review-heading"><div><span className="eyebrow">{t("review")}</span><h1>{chosen.label}</h1></div><div className="review-actions"><span className="analysis-method-summary">{t("selectedMethod")} · <strong>{t(mode)}</strong></span><button className="primary analyze-button" disabled={!canAnalyze} onClick={() => void action(() => analyze([selected]))}>{analyzingChosen ? t("analyzing") : t("analyze")} <span aria-hidden="true">↗</span></button>{!modeReady && <p className="mode-note">{t(modeProblem)}</p>}{health?.models_ready === false && <p className="mode-note">{t("missingModels")}</p>}</div></div>
            {analyzingChosen ? <section className="coaching-summary processing" role="status"><span className="eyebrow">{t("analyzing")}</span><h2>{t("analyzingTitle")}</h2><p>{t("analyzingHelp")}</p><progress aria-label={t("analyzing")} /></section> : coaching && coaching.status !== "awaiting_analysis" ? <>
              <section className="coaching-summary" ref={summarySection} tabIndex={-1} data-testid="coaching-summary" aria-label={t("overview")}>
                <div className="summary-kicker"><span className="eyebrow">{t("overview")}</span><span className={`pill ${coaching.status === "limited" ? "amber" : ""}`}>{t(coaching.status === "limited" ? "limited" : hasVisualReview ? "visualReview" : "movementSummary")}</span></div>
                <h2>{cText(coaching.overall.headline)}</h2><p>{cText(coaching.overall.summary)}</p>{!hasVisualReview && <div className="review-upgrade-note">{t("upgradeReview")}</div>}
                {coaching.strengths.length > 0 && <div className="strength-line"><span className="strength-check" aria-hidden="true">✓</span><div><strong>{t("strengths")} · {cText(coaching.strengths[0].title)}</strong><span>{cText(coaching.strengths[0].detail)}</span></div></div>}
              </section>
              <div className={`coaching-layout ${issues.length ? "" : "no-priorities"}`}>
                <section className="priorities" aria-labelledby="priorities-heading"><div className="section-heading"><h2 id="priorities-heading">{t("priorities")}</h2>{issues.length > 0 && <span className="count">{String(issues.length).padStart(2, "0")}</span>}</div><p className="section-help">{t("priorityNote")}</p>
                  {issues.length ? <ol className="issue-list">{issues.map((issue, i) => <li key={issue.id} className={`issue-card severity-${issue.severity}`} data-testid="issue-card">
                    <div className="issue-heading"><span className="rank">{String(i + 1).padStart(2, "0")}</span><div><div className="issue-meta"><span className="priority-label">{t(issue.severity)}</span><span>{t("confidence")} · {t(`confidence_${issue.confidence}`)}</span></div><h3>{cText(issue.title)}</h3></div></div>
                    <p className="issue-observation">{cText(issue.observation)}</p><div className="standard-gap"><span>{t("standardGap")}</span><p>{cText(issue.standard_gap)}</p></div>
                    <p className="issue-action"><strong>{t("tryThis")}</strong>{cText(issue.action)}</p>
                    <div className="issue-bottom">{evidenceButton(issue.evidence_frame_ids, cText(issue.title))}<details><summary>{t("detail")}</summary><div><h4>{t("why")}</h4><p>{cText(issue.why_it_matters)}</p><h4>{t("drill")}</h4><p>{cText(issue.drill)}</p></div></details></div>
                  </li>)}</ol> : <div className="insufficient"><span className="evidence-icon" aria-hidden="true">◌</span><h3>{t("noIssues")}</h3><p>{t("noIssuesHelp")}</p><button className="text-button" onClick={() => evidenceSection.current?.scrollIntoView({ behavior: scrollBehavior() })}>{t("evidenceSection")} ↗</button></div>}
                </section>
                <aside className="practice-card" aria-labelledby="practice-heading"><span className="eyebrow">{t("nextPractice")}</span><span className="practice-mark" aria-hidden="true">↗</span><h2 id="practice-heading">{cText(coaching.next_practice.title)}</h2><p>{cText(coaching.next_practice.instruction)}</p><div className="success-check"><strong>{t("success")}</strong><p>{cText(coaching.next_practice.success_check)}</p></div></aside>
              </div>
              {coaching.metrics.length > 0 && <section className="human-metrics" aria-labelledby="metrics-heading"><div className="section-heading"><h2 id="metrics-heading">{t("metrics")}</h2></div><p className="section-help">{t("metricsNote")}</p><div className="metric-grid">{coaching.metrics.map((metric) => <article className={`human-metric ${metric.status === "unavailable" ? "unavailable" : ""}`} key={metric.id} data-testid="coaching-metric"><h3>{cText(metric.label)}</h3><strong className="metric-value">{cText(metric.display_value) || t("unavailable")}</strong><p>{cText(metric.interpretation)}</p>{evidenceButton(metric.evidence_frame_ids, cText(metric.label))}</article>)}</div></section>}
            </> : <section className="coaching-summary pending" data-testid="coaching-summary"><span className="eyebrow">{t("awaiting_analysis")}</span><h2>{t("reviewPending")}</h2><p>{ready ? t("legacyHelp") : t("reviewPendingHelp")}</p></section>}
            {chosen.model_error && <p className="notice model-notice" role="status">{t(chosen.model_error)}</p>}
            <section className="evidence-section" ref={evidenceSection} tabIndex={-1} data-testid="evidence-section" aria-labelledby="evidence-heading">
              <div className="section-heading"><h2 id="evidence-heading">{t("evidenceSection")}</h2><button className="text-button back-review" onClick={() => { summarySection.current?.scrollIntoView({ behavior: scrollBehavior() }); summarySection.current?.focus({ preventScroll: true }); }}>{t("returnReview")} ↑</button></div>
              <p className="section-help">{t("evidenceNote")}</p>
              {evidenceLabel && <p className="evidence-context" role="status">{t("selectedEvidence")} · <strong>{evidenceLabel}</strong></p>}
              <div className={`video-layout ${ref ? "has-reference" : ""}`}>
                <div className="video-main"><div className="viewer-top"><strong>{chosen.label}</strong><span>{t("currentShot")}</span></div><div className="viewer" style={{ aspectRatio: `${ownCrop[2] - ownCrop[0]}/${ownCrop[3] - ownCrop[1]}`, maxWidth: `${440 * (ownCrop[2] - ownCrop[0]) / (ownCrop[3] - ownCrop[1])}px`, marginInline: "auto" }}>
                  <video style={cropStyle(chosen, ownCrop)} ref={video} src={chosen.preview_url} className={!playing ? "hidden-video" : ""} playsInline preload="metadata" onLoadedMetadata={(e) => { e.currentTarget.playbackRate = Number(speed); }} onEnded={() => setPlaying(false)} onTimeUpdate={(e) => { if (playing) setIndex(nearest(chosen, e.currentTarget.currentTime * 1e6)); }} />
                  {!playing && <img style={cropStyle(chosen, ownCrop)} src={`/api/assets/${chosen.id}/frames/${index}`} alt={`${chosen.label}, ${t("frame")} ${index}`} />}
                  <div className="overlay-space" style={cropStyle(chosen, ownCrop)}><Pose frame={tracks[index]} show={showPose} /></div>
                </div><div className="source-caption"><span>{t("source")} {((chosen.frame_index[index]?.source_time_us || 0) / 1e6).toFixed(3)}s</span><span>{t("frame")} {chosen.frame_index[index]?.source_frame_index ?? index}</span></div></div>
                {ref ? <div className="video-reference"><div className="viewer-top"><strong>{ref.label}</strong><span>{relative >= 0 ? "+" : ""}{(relative / 1e6).toFixed(2)}s</span></div><div className="viewer" style={{ aspectRatio: `${refCrop[2] - refCrop[0]}/${refCrop[3] - refCrop[1]}`, maxWidth: `${440 * (refCrop[2] - refCrop[0]) / (refCrop[3] - refCrop[1])}px`, marginInline: "auto" }}><img style={cropStyle(ref, refCrop)} src={`/api/assets/${ref.id}/frames/${refIndex}`} alt={`${ref.label}, ${t("frame")} ${refIndex}`} /><div className="overlay-space" style={cropStyle(ref, refCrop)}><Pose frame={refTracks[refIndex]} show={showPose} /></div></div><div className="source-caption"><span>{t("source")} {((ref.frame_index[refIndex]?.source_time_us || 0) / 1e6).toFixed(3)}s</span><span>{t("frame")} {ref.frame_index[refIndex]?.source_frame_index ?? refIndex}</span></div><p className="alignment-note">{t(ownAnchor !== null && refAnchor !== null ? "matchingRelease" : "approximateAlignment")}</p></div> : <div className="video-guide"><span className="eyebrow">{t("details")}</span><h3>{t("evidence")}</h3><p>{t("evidenceNote")}</p>{chosen.phases.release && <button onClick={() => seek(chosen.phases.release!.frame_range[0])}>{t("releaseJump")} ↗</button>}</div>}
              </div>
              <div className="transport"><button aria-label={t(playing ? "pause" : "play")} onClick={() => { if (playing) { video.current?.pause(); setPlaying(false); } else { if (video.current && video.current.ended) video.current.currentTime = 0; setPlaying(true); void video.current?.play().catch(() => setPlaying(false)); } }}>{playing ? "Ⅱ" : "▶"}<span>{t(playing ? "pause" : "play")}</span></button><input aria-label={t("timeline")} type="range" min="0" max={Math.max(0, chosen.frame_index.length - 1)} value={index} onChange={(e) => seek(Number(e.target.value))} /><span className="clip-time">{((chosen.frame_index[index]?.time_us || 0) / 1e6).toFixed(2)} / {(chosen.duration_us / 1e6).toFixed(1)}s</span><span className="playback-speed" aria-label={`${t("slow")} ${speed}×`}>{speed}×</span></div>

              <details className="disclosure frame-tools"><summary>{t("reviewTools")}</summary><div className="disclosure-body"><div className="step-buttons"><button onClick={() => seek(index - 1)} disabled={index === 0}>← {t("prev")}</button><button onClick={() => seek(index + 1)} disabled={index >= chosen.frame_index.length - 1}>{t("next")} →</button><span>{t("frame")} {index}</span></div><h3>{t("release")}</h3>{chosen.phases.release ? <p className="interval">{chosen.phases.release.range_us.map((v) => (v / 1e6).toFixed(3)).join(" – ")}s <span className="pill">{t(["manual", "user_corrected"].includes(chosen.phases.release.source) ? "reviewedInterval" : "candidate")}</span></p> : <p className="muted">{ready ? t("notKnown") : t("noMetrics")}</p>}{ready && <><p className="muted">{t("phaseHelp")}</p><div className="phase-actions"><button className={last !== null ? "chosen" : ""} onClick={() => { setLast(index); seek(index); }}>{t("last")}{last !== null ? ` · ${last}` : ""}</button><button className={first !== null ? "chosen" : ""} onClick={() => { setFirst(index); seek(index); }}>{t("first")}{first !== null ? ` · ${first}` : ""}</button><button className="primary" disabled={!validSave || generating} onClick={() => void action(save)}>{t("save")}</button>{(last !== null || first !== null) && <button onClick={() => { setLast(null); setFirst(null); }}>{t("reset")}</button>}</div></>}</div></details>
              <details className="disclosure comparison-disclosure"><summary>{t("comparisonResults")}<span>{ref?.label || t("noReference")}</span></summary><div className="disclosure-body"><p className="muted">{reference ? t("comparisonNote") : t("noReferenceHelp")}</p>{reference && <button className="primary" disabled={!ready || generating || !!(ref && !ref.measurements)} onClick={() => void action(updateReport)}>{t("compare")}</button>}{ref && !ref.measurements && <p className="notice">{t("reference_unanalyzed")}</p>}{!reportMatches && report && <p className="notice" data-testid="comparison-stale">{t("comparisonDraft")}</p>}{reportMatches && reference && <div className="comparison-result"><h3>{t("comparisonLabel")} · {ref?.label}</h3>{report.comparison.differences.length ? <dl>{report.comparison.differences.map((d) => <div key={d.key}><dt>{t(d.key)}</dt><dd>{d.difference >= 0 ? "+" : ""}{d.difference.toFixed(d.unit === "milliseconds" ? 0 : 2)} {t(d.unit)}</dd></div>)}</dl> : <p className="muted">{t(report.comparison.reason)}</p>}</div>}</div></details>
            </section>
            <section className="secondary-details" aria-label={t("details")}>
              {ready && <details className="disclosure"><summary>{t("raw")}</summary><div className="disclosure-body"><p className="muted">{t("rawHelp")} {t("visibility")} {chosen.measurements!.visible_frames}/{chosen.measurements!.total_frames}</p><div className="raw-metrics">{chosen.measurements!.measurements.map((m) => <div key={m.key}><span>{t(m.key)}</span><strong>{m.value === null ? "—" : m.value.toFixed(m.unit === "milliseconds" ? 0 : 2)} <small>{t(m.unit)}</small></strong>{m.reason && <p>{t(m.reason)}</p>}{evidenceButton(m.evidence_frame_ids, t(m.key))}</div>)}</div><Curve asset={chosen} current={index} onSeek={seek} t={t} />{chosen.measurements!.flags.length > 0 && <ul className="limits-list">{chosen.measurements!.flags.map((f) => <li key={f}>{t(f)}</li>)}</ul>}{chosen.model_assist && <div className="model-observations"><h3>{t("modelReview")} · {t(chosen.analysis_config?.mode || "unknown")}</h3>{chosen.model_assist.observations.map((o, i) => <div key={i}><p>{t(o.attribute === "visibility" ? "model_visibility" : o.attribute)} · {t(o.interpretation)}</p>{evidenceButton(o.evidence_frame_ids, t(o.attribute))}</div>)}</div>}</div></details>}
              <details className="disclosure"><summary>{t("sourceDetail")}</summary><div className="disclosure-body"><p className="muted">{t("limits")}</p>{coaching?.limitations.length ? <ul className="limits-list">{coaching.limitations.map((l, i) => <li key={i}>{cText(l)}</li>)}</ul> : null}<div className="sources">{report?.sources.map((s) => <a key={s.id} href={s.url} target="_blank" rel="noreferrer">{s.title || s.id} ↗</a>)}</div></div></details>
              <details className="disclosure downloads"><summary>{t("downloads")}</summary><div className="disclosure-body">{exportMatches ? <><p className="muted">{chosen.label} · {t("revision")} {chosen.revision} · {t("exportsLanguage")}: {report.locale === "zh" ? "中文" : "English"}{ref ? ` · ${t("referenceUsed")}: ${ref.label}` : ""}</p><div className="exports">{["text", "image", "video", "json"].map((kind) => <a key={kind} href={`/api/reports/${report.id}/${kind}`} download>{t(kind)} <span aria-hidden="true">↓</span></a>)}</div></> : <><p className="muted">{t("exportPending")}</p><button disabled={!ready || generating || !!(ref && !ref.measurements)} onClick={() => void action(updateReport)}>{t("refreshExports")}</button></>}</div></details>
            </section>
          </> : <div className="empty"><span className="mark" aria-hidden="true">↗</span><h1>{t("noShots")}</h1><p>{t("emptyHelp")}</p><button className="primary" onClick={openSettings}>{t("settingsEmpty")} ↗</button></div>}
          {jobs.length > 0 && <details className="disclosure activity"><summary>{t("jobs")}{active && <span role="status">{t("analyzingOther")}</span>}</summary><div className="disclosure-body">{jobs.slice(0, 4).map((j) => <div className="job" key={j.id}><div className="job-heading"><strong>{t(j.status)}</strong><span>{t(j.stage)}</span><small>{j.completed ?? 0}{j.total ? ` / ${j.total}` : ""}</small></div>{j.status === "running" && j.stage === "pose_and_ball" && j.progress.total_frames && <progress aria-label={t(j.stage)} value={j.progress.frames || 0} max={j.progress.total_frames} />}{["running", "queued"].includes(j.status) && <button onClick={() => void action(async () => { await api(`/jobs/${j.id}/cancel`, post({})); })}>{t("cancel")}</button>}{j.error_code && <p className="notice">{t(j.error_code)}</p>}{j.errors.map((e, i) => <p className="notice" key={i}>{t(e.code)}</p>)}{j.receipts.length > 0 ? <p className="cost">{t("usage")}: {j.receipts.length} · {j.receipts.every((r) => r.cost.status === "subscription_usage") ? t("codexPlan") : j.receipts.some((r) => r.cost.estimated_usd === null) ? t("unknownCost") : `${t("estimated")} $${j.receipts.reduce((s, r) => s + (r.cost.estimated_usd || 0), 0).toFixed(5)}`}<small>{t(j.receipts.every((r) => r.cost.status === "subscription_usage") ? "codexHint" : "costScope")}</small></p> : <p className="cost">{t("localCost")}</p>}</div>)}</div></details>}
        </div>
      </main>
      <dialog className="settings-dialog" id="settings-dialog" ref={settingsDialog} aria-labelledby="settings-title" aria-describedby="settings-description" onKeyDown={keepSettingsFocus} onCancel={(e) => { e.preventDefault(); closeSettings(); }} onClose={() => setSettingsOpen(false)} onClick={(e) => {
        if (e.target !== e.currentTarget) return;
        const bounds = e.currentTarget.getBoundingClientRect();
        if (e.clientX < bounds.left || e.clientX > bounds.right || e.clientY < bounds.top || e.clientY > bounds.bottom) closeSettings();
      }}>
        <div className="settings-header"><div><span className="eyebrow">Shot Form Coach</span><h2 id="settings-title">{t("settingsTitle")}</h2><p id="settings-description">{t("settingsHelp")}</p></div><button className="settings-close" aria-label={t("closeSettings")} onClick={closeSettings} autoFocus>×</button></div>
        <nav className="settings-nav" aria-label={t("settingsTitle")}>{["analysis", "import", "comparison", "playback", "language"].map((section) => <a key={section} href={`#settings-${section}`} onClick={(e) => { e.preventDefault(); document.getElementById(`settings-${section}`)?.scrollIntoView({ behavior: scrollBehavior(), block: "start" }); }}>{t(`${section}Section`)}</a>)}</nav>
        <div className="settings-body" ref={settingsBody}>
          {error && settingsOpen && <div className="error" role="alert">{t(error)}</div>}
          <section className="setting-section" id="settings-analysis" aria-labelledby="settings-analysis-title"><div className="setting-section-heading"><span>01</span><h3 id="settings-analysis-title">{t("analysisSection")}</h3></div><p className="settings-help">{t("nextAnalysis")}</p>
            {methodSelect}<p className="settings-method-hint">{t(mode === "local" ? "methodHint" : mode === "astra_codex" ? "codexHint" : "apiHint")}</p>
            {!modeReady && <p className="notice">{t(modeProblem)}</p>}
            <details className="provider-help"><summary>{t("providers")}</summary><ul><li>Gemini · {t(health?.gemini_configured ? "providerReady" : "noKey")}</li><li>Astra / Codex · {t(health?.codex?.ready ? "providerReady" : health?.codex?.reason || "codex_not_installed")}</li><li>Astra / API · {t(health?.astra_api_configured ? "providerReady" : "openai_key_missing")}</li></ul></details>
            <div className="settings-fields"><label>{t("hand")}<select value={hand} onChange={(e) => setHand(e.target.value)}>{["auto", "right", "left"].map((v) => <option key={v} value={v}>{t(v)}</option>)}</select></label><label>{t("view")}<select value={view} onChange={(e) => setView(e.target.value)}>{["oblique", "side", "front", "unknown"].map((v) => <option key={v} value={v}>{t(v)}</option>)}</select></label><label className="full-width">{t("shot")}<select value={shot} onChange={(e) => setShot(e.target.value)}>{["stationary_jump_shot", "set_shot", "unknown"].map((v) => <option key={v} value={v}>{t(v)}</option>)}</select></label></div>
            {health?.models_ready === false && <p className="notice">{t("missingModels")}</p>}
            {assets.length > 0 && <button className="batch-analysis" disabled={!canStart} onClick={() => void action(() => analyze(assets.map((a) => a.id))).then((success) => { if (success) closeSettings(); })}>{t("all")} · {assets.length}</button>}
          </section>
          <section className="setting-section" id="settings-import" aria-labelledby="settings-import-title"><div className="setting-section-heading"><span>02</span><h3 id="settings-import-title">{t("importSection")}</h3></div>
            <p className="import-method-note">{t("importMethod")} <strong>{t(mode)}</strong></p>
            <div className="import-option"><h4>{t("fromDevice")}</h4><p>{t("fromDeviceHelp")}</p>
              <input type="file" accept="video/*" hidden ref={upload} onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void action(async () => {
              const form = new FormData(); form.append("file", file);
              const a = await api<Asset>("/assets/upload", { method: "POST", body: form });
              setSelected(a.id); await analyze([a.id]);
            }).then((success) => { if (success) closeSettings(); });
            e.target.value = "";
          }} />
              <button className="primary" disabled={!canStart} onClick={() => upload.current?.click()}>＋ {t("uploadAnalyze")}</button><small>{t("uploadHint")}</small></div>
            <div className="import-option workbench-option"><h4>{t("workbench")}</h4><p>{t("workbenchHelp")}</p><p className="workbench-when">{t("workbenchWhen")}</p>
              {health?.workbench_configured === false ? <p className="settings-empty-state">{t("workbenchUnconfigured")}</p> : runsState === "loading" ? <p className="settings-empty-state" role="status">{t("workbenchLoading")}</p> : runsState === "error" ? <p className="settings-empty-state" role="status">{t("workbenchLoadError")}</p> : !runs.length ? <p className="settings-empty-state">{t("workbenchEmpty")}</p> : <div className="workbench"><label>{t("workbenchRun")}<select value={run} onChange={(e) => setRun(e.target.value)}>{runs.map((r) => <option key={r.id} value={r.id}>{r.id.slice(-8)} · {r.clip_count} {t("workbenchClips")}</option>)}</select></label><button disabled={!canStart || !run} onClick={() => void action(async () => { const imported = await api<Asset[]>("/workbench/import", post({ run_id: run })); if (imported.length) { setSelected(imported[0].id); await analyze(imported.map((item) => item.id)); } }).then((success) => { if (success) closeSettings(); })}>{t("importAnalyze")}</button></div>}
              {health?.workbench_configured !== false && runsState !== "loading" && <button className="text-button" onClick={() => void loadRuns()}>{t("reloadRuns")}</button>}
            </div>
          </section>
          <section className="setting-section" id="settings-comparison" aria-labelledby="settings-comparison-title"><div className="setting-section-heading"><span>03</span><h3 id="settings-comparison-title">{t("comparisonSection")}</h3></div>
            {chosen ? <><p className="settings-help">{t("comparisonScope")} · <strong>{chosen.label}</strong></p><label>{t("comparator")}<select value={reference} onChange={(e) => { setReference(e.target.value); setSameView(false); }}><option value="">{t("noReference")}</option>{assets.filter((a) => a.id !== selected).map((a) => <option key={a.id} value={a.id}>{a.label}{!a.measurements ? ` · ${t("ready")}` : ""}</option>)}</select></label><p className="settings-help comparison-help">{t(assets.length < 2 ? "referenceMissing" : "comparisonNote")}</p>{reference && <label className="check"><input type="checkbox" checked={sameView} onChange={(e) => setSameView(e.target.checked)} />{t("sameView")}</label>}{ref && !ref.measurements && <p className="notice">{t("reference_unanalyzed")}</p>}{!reportMatches && report && <p className="notice">{t("comparisonDraft")}</p>}<button disabled={!ready || generating || !!(ref && !ref.measurements)} onClick={() => void action(updateReport).then((success) => { if (success) closeSettings(); })}>{t("compare")}</button></> : <p className="settings-empty-state">{t("comparisonEmpty")}</p>}
          </section>
          <section className="setting-section" id="settings-playback" aria-labelledby="settings-playback-title"><div className="setting-section-heading"><span>04</span><h3 id="settings-playback-title">{t("playbackSection")}</h3></div><p className="settings-help">{t("playbackHelp")}</p>
            <label>{t("slow")}<select value={speed} onChange={(e) => setSpeed(e.target.value)}>{["0.25", "0.5", "1"].map((v) => <option key={v} value={v}>{v}×</option>)}</select></label>
            <div className="settings-toggles"><label className="check"><input type="checkbox" checked={focused} onChange={(e) => setFocused(e.target.checked)} />{t("focus")}</label><label className="check"><input type="checkbox" checked={showPose} onChange={(e) => setShowPose(e.target.checked)} />{t("pose")}</label></div>
          </section>
          <section className="setting-section" id="settings-language" aria-labelledby="settings-language-title"><div className="setting-section-heading"><span>05</span><h3 id="settings-language-title">{t("languageSection")}</h3></div><p className="settings-help">{t("languageHelp")}</p><div className="language" role="group" aria-label={t("languageSection")}><button aria-pressed={lang === "en"} className={lang === "en" ? "selected" : ""} onClick={() => setLang("en")}>English</button><button aria-pressed={lang === "zh"} className={lang === "zh" ? "selected" : ""} onClick={() => setLang("zh")}>中文</button></div></section>
        </div>
        <div className="settings-footer"><span>{busy ? t("busy") : t("settingsSaved")}</span><button className="primary" onClick={closeSettings}>{t("doneSettings")}</button></div>
      </dialog>
      <footer><span>{t("sourceMap")}</span><span>Shot Form Coach</span></footer>
    </>
  );
}
