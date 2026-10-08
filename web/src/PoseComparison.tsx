export type Bilingual = { en: string; zh: string };
export type ComparisonMode = "none" | "teaching" | "reference";
export type Landmark = { x: number; y: number; visibility: number };
type Evidence = { asset_id: string; frame_id: string; time_us: number; source_time_us: number };
export type ComparisonFrame = {
  frame_index: number;
  phase: string;
  available: boolean;
  reason?: string | Bilingual;
  reason_text?: Bilingual;
  target_landmarks: (Landmark | null)[];
  connections: number[][];
  own_evidence: Evidence;
  reference_evidence?: Evidence;
  deltas: { key: string; label: Bilingual; value: number | null; unit: string; own_value?: number; target_value?: number; interpretation?: Bilingual | string }[];
};
export type PoseComparison = {
  version: string;
  mode: "teaching" | "reference";
  label: Bilingual;
  description: Bilingual;
  source_type: string;
  source_ids: string[];
  coordinate_system: "normalized_own_frame";
  comparison_status: string;
  reason?: string | Bilingual;
  reason_text?: Bilingual;
  recommended_frame_index?: number | null;
  frames: ComparisonFrame[];
};

const copy = {
  en: {
    title: "See the movement difference", own: "You", teaching: "Teaching target illustration", reference: "Selected reference",
    off: "Turn on Pose overlay in Playback settings to compare the movement in the same frame.",
    settings: "Pose settings", noTarget: "Your pose is visible. Choose a teaching target or personal reference in Comparison settings.",
    loading: "Aligning the comparison…", error: "The pose comparison could not load. Your video is still available.",
    release: "Release", follow_through: "Follow-through", pre_release: "Before release", after_follow_through: "After the finish", loadingPhase: "Loading", other: "Outside the comparison phase",
    teachingHelp: "A drawing of the teaching cue, fitted to your visible arm lengths. It is not a measured ideal shooter or a form score.",
    referenceHelp: "Your selected shot, aligned in time and body size. A visible difference does not establish a technical fault.",
    phase: "Current phase", referenceTime: "Reference source time", noDifference: "Move through these moments to inspect the arm positions.",
    previewScope: "Overlay applies to this preview. Saved exports keep their existing comparison layout.",
    unavailable: "This frame does not have enough visible evidence for a comparison.",
    outside_phase: "The target appears around release and follow-through. Jump to one of those moments.",
    outside_teaching_window: "The target appears around release and follow-through. Jump to one of those moments.",
    outside_comparison_window: "The target appears around release and follow-through. Jump to one of those moments.",
    release_unknown: "The release interval is needed to align this comparison. Review it in the frame tools below.",
    release_interval_wide: "The release interval is too wide to align this pose reliably. Refine it in the frame tools below.",
    handedness_uncertain: "The shooting side is uncertain. Choose the shooting hand in Analysis settings before the next analysis.",
    track_gaps: "The arm or torso landmarks are not clear enough in this frame.",
    landmark_not_visible: "The arm or torso landmarks are not clear enough in this frame.",
    reference_not_selected: "Choose a personal reference in Comparison settings.",
    select_reference: "Choose a personal reference in Comparison settings.",
    reference_unanalyzed: "Analyze the selected reference before comparing its pose.",
    not_analyzed: "Analyze this shot to see the pose comparison.",
    view_unverified: "Confirm that both clips share the same fixed camera view in Comparison settings.",
    context_mismatch: "These shots have different types or camera views, so their poses cannot be aligned reliably.",
    handedness_mismatch: "These shots use different shooting hands.",
    reference_frame_unavailable: "The reference does not contain this part of the movement.",
    reference_release_unknown: "The reference needs a release interval to align its pose.",
    unsupported_view: "This camera view does not support the teaching overlay.",
    torso_lengths: "body lengths", degrees_projection: "projected °", degrees: "°", pixels: "px",
    differenceBasis: "Compared with the displayed target", moreBent: "Your elbow is more bent", straighter: "Your elbow is straighter", sameElbow: "Similar projected elbow angle", handLower: "Your hand is lower", handHigher: "Your hand is higher", sameHand: "Similar hand height",
  },
  zh: {
    title: "看清动作差在哪里", own: "本人", teaching: "教学目标示意", reference: "所选参照",
    off: "在播放设置中打开姿态叠加，即可在同一画面比较动作。",
    settings: "姿态设置", noTarget: "当前显示本人姿态。可在对比设置中选择教学目标或个人参照。",
    loading: "正在对齐姿态…", error: "姿态对比暂时无法加载，仍可回看原视频。",
    release: "离手", follow_through: "随挥", pre_release: "出手前", after_follow_through: "收势后", loadingPhase: "下沉", other: "当前不在对比阶段",
    teachingHelp: "根据你可见的手臂长度绘制教学提示；不是某位球员的实测理想动作，也不用于姿势评分。",
    referenceHelp: "所选投篮按动作时间和身体大小对齐。画面中的差异本身不能证明技术错误。",
    phase: "当前阶段", referenceTime: "参照源时间", noDifference: "在这些关键时刻前后移动，观察手臂位置。",
    previewScope: "叠加用于当前预览，已保存的导出沿用原有对比版式。",
    unavailable: "这一帧的可见证据不足，暂不能对比姿态。",
    outside_phase: "目标姿态显示在离手与随挥附近，请跳到对应时刻。",
    outside_teaching_window: "目标姿态显示在离手与随挥附近，请跳到对应时刻。",
    outside_comparison_window: "目标姿态显示在离手与随挥附近，请跳到对应时刻。",
    release_unknown: "对齐需要离手区间，可在下方逐帧工具中复核。",
    release_interval_wide: "离手区间过宽，暂不能可靠对齐；请在下方逐帧工具中缩小区间。",
    handedness_uncertain: "出手侧尚不确定，请在分析设置中选择出手侧后重新分析。",
    track_gaps: "这一帧的手臂或躯干关键点不够清楚。",
    landmark_not_visible: "这一帧的手臂或躯干关键点不够清楚。",
    reference_not_selected: "请在对比设置中选择个人参照球。",
    select_reference: "请在对比设置中选择个人参照球。",
    reference_unanalyzed: "先分析所选参照球，才能对比姿态。",
    not_analyzed: "分析这次投篮后，即可查看姿态对比。",
    view_unverified: "请在对比设置中确认两球使用相同的固定视角。",
    context_mismatch: "两球的投篮情境或视角不同，暂不能可靠对齐姿态。",
    handedness_mismatch: "两球使用不同的出手侧。",
    reference_frame_unavailable: "参照视频没有包含这一段动作。",
    reference_release_unknown: "参照球需要离手区间才能对齐姿态。",
    unsupported_view: "当前拍摄视角不适合显示教学叠加。",
    torso_lengths: "身体参考长度", degrees_projection: "投影度", degrees: "度", pixels: "像素",
    differenceBasis: "与画面中的目标相比", moreBent: "本人肘部更弯", straighter: "本人肘部更直", sameElbow: "投影肘角接近", handLower: "本人手的位置更低", handHigher: "本人手的位置更高", sameHand: "手的位置高度接近",
  },
};

export function TargetPose({ frame, width, height }: { frame?: ComparisonFrame; width: number; height: number }) {
  if (!frame?.available) return null;
  const visible = (p: Landmark | null | undefined): p is Landmark => !!p && p.visibility >= 0.5 && Number.isFinite(p.x) && Number.isFinite(p.y);
  const connected = new Set(frame.connections.flat());
  return <g className="target-pose" data-testid="target-pose">
    {frame.connections.map(([a, b]) => {
      const start = frame.target_landmarks[a], end = frame.target_landmarks[b];
      return visible(start) && visible(end) ? <line key={`${a}-${b}`} x1={start.x * width} y1={start.y * height} x2={end.x * width} y2={end.y * height} /> : null;
    })}
    {frame.target_landmarks.map((p, i) => connected.has(i) && visible(p) ? <circle key={i} cx={p.x * width} cy={p.y * height} r={4} /> : null)}
  </g>;
}

export function PoseLegend({ lang, mode }: { lang: string; mode: ComparisonMode }) {
  const strings = copy[lang === "zh" ? "zh" : "en"];
  return <div className="pose-legend" aria-label={lang === "zh" ? "姿态图例" : "Pose legend"}>
    <span><i className="own-key" aria-hidden="true" />{strings.own}</span>
    <span><i className="target-key" aria-hidden="true" />{mode === "reference" ? strings.reference : strings.teaching}</span>
  </div>;
}

export function PoseComparisonGuide({ comparison, frame, lang, enabled, mode, loading, failed, releaseFrame, followThroughFrame, onSeek, onSettings }: {
  comparison?: PoseComparison; frame?: ComparisonFrame; lang: string; enabled: boolean; mode: ComparisonMode;
  loading: boolean; failed: boolean; releaseFrame?: number; followThroughFrame?: number;
  onSeek: (frame: number) => void; onSettings: () => void;
}) {
  const language = lang === "zh" ? "zh" : "en";
  const tr = (key: string) => (copy[language] as Record<string, string>)[key] || "";
  const text = (value: Bilingual | undefined) => value?.[language] || value?.en || "";
  const reason = frame?.reason || comparison?.reason;
  const reasonText = text(frame?.reason_text || comparison?.reason_text) || (typeof reason === "object" ? text(reason) : reason ? tr(reason) || tr("unavailable") : tr("unavailable"));
  const phase = frame?.phase === "loading" ? tr("loadingPhase") : tr(frame?.phase || "other") || tr("other");
  const differenceLabel = (delta: ComparisonFrame["deltas"][number]) => {
    const rounded = Number(delta.value!.toFixed(delta.unit.includes("degree") ? 0 : 2));
    if (delta.key === "projected_elbow_angle_difference") return tr(rounded === 0 ? "sameElbow" : rounded < 0 ? "moreBent" : "straighter");
    if (delta.key === "wrist_height_difference") return tr(rounded === 0 ? "sameHand" : rounded < 0 ? "handLower" : "handHigher");
    return text(delta.label);
  };
  return <aside className="pose-guide" aria-label={tr("title")}>
    <span className="eyebrow">{tr("title")}</span>
    <h3>{text(comparison?.label) || tr(mode === "reference" ? "reference" : "teaching")}</h3>
    <div className="phase-jumps" aria-label={language === "zh" ? "跳到动作阶段" : "Jump to a shooting phase"}>
      {releaseFrame !== undefined && <button className={frame?.phase === "release" && frame.available ? "phase-active" : ""} onClick={() => onSeek(releaseFrame)}>{tr("release")} ↗</button>}
      {followThroughFrame !== undefined && <button className={frame?.phase === "follow_through" && frame.available ? "phase-active" : ""} onClick={() => onSeek(followThroughFrame)}>{tr("follow_through")} ↗</button>}
    </div>
    {!enabled ? <p className="pose-status">{tr("off")}</p> : mode === "none" ? <p className="pose-status">{tr("noTarget")}</p> : <>
      <p className="pose-explanation">{text(comparison?.description) || tr(mode === "reference" ? "referenceHelp" : "teachingHelp")}</p>
      {loading ? <p className="pose-status" role="status">{tr("loading")}</p> : failed ? <p className="pose-status" role="status">{tr("error")}</p> : <>
        {frame?.available ? <p className="pose-phase"><span>{tr("phase")}</span><strong>{phase}</strong></p> : <p className="pose-status" data-testid="pose-unavailable">{reasonText}</p>}
        {frame?.available && frame.deltas.length > 0 && <div className="pose-difference"><p>{tr("differenceBasis")}</p><dl className="pose-deltas">{frame.deltas.filter((d) => d.value !== null).slice(0, 2).map((d) => <div key={d.key}><dt>{differenceLabel(d)}</dt><dd><span>{text(d.label)}</span> {d.value! > 0 ? "+" : ""}{d.value!.toFixed(d.unit.includes("degree") ? 0 : 2)} {tr(d.unit) || d.unit}</dd>{d.interpretation && typeof d.interpretation === "object" && <p>{text(d.interpretation)}</p>}</div>)}</dl></div>}
        {frame?.reference_evidence && <p className="pose-reference-source">{tr("referenceTime")} · {(frame.reference_evidence.source_time_us / 1e6).toFixed(3)}s</p>}
      </>}
    </>}
    {(!enabled || mode === "none") && <button className="text-button pose-settings-link" onClick={onSettings}>{tr("settings")} ↗</button>}
    {enabled && mode !== "none" && <p className="pose-scope">{tr("previewScope")}</p>}
  </aside>;
}
