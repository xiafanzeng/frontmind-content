import {useCallback,useEffect,useRef,useState,type CSSProperties} from "react";
import {Check,ChevronDown,FileText,Loader2,Plus,RefreshCw,Sparkles,X} from "lucide-react";
import {Dialog,DialogContent,DialogDescription,DialogTitle} from "@frontmind/module-ui/components/ui/dialog";
import {useContentWorkspaceHost,type TaskResponse} from "./host";
import {contentProductionStagePosition,type ContentProductionDto,type ContentProductionInput,type ContentProductionJobKind,type ContentProductionMode} from "../contracts/content-production";
import ContentProductionConfirmation from "./ContentProductionConfirmation";
import {contentProductionArtifactName,contentProductionArtifactUrl,contentProductionTaskTitle} from "../contracts/content-production-public";
import "./content-production.css";
import "./content-workbench.css";
const contentTheme = {"--module-accent":"#8a6100","--module-color":"#8a6100"} as CSSProperties;
export const CONTENT_MODES: {
  value: ContentProductionMode;
  title: string;
  description: string;
}[] = [
  {
    value: "new_reference_pack",
    title: "新建品牌资料包",
    description: "整理企业资料，形成可复用的品牌事实、定位与写作资料包。",
  },
  {
    value: "refresh_reference_pack",
    title: "更新品牌资料包",
    description: "在已有资料包基础上，更新市场信息、品牌定位与表达。",
  },
  {
    value: "p0",
    title: "制作品牌深度文章",
    description: "确认资料包后，新建品牌深度文章，或导入已有文章继续编辑。",
  },
  {
    value: "single_article",
    title: "围绕问题写文章",
    description: "围绕一个问题，结合监控答案与引用信源开展研究和写作。",
  },
];

type LaneStep = { title: string; detail: string; position: number };
export function contentProductionLane(
  mode: ContentProductionMode,
  jobKind?: ContentProductionJobKind | null,
): LaneStep[] {
  const packSteps = [
    { title: "企业资料", detail: "接入企业材料，明确品牌与任务", position: 1 },
    { title: "市场研究", detail: "研究市场与可比较的选择", position: 3 },
    {
      title: "确认比较对象",
      detail: "区分比较对象、同类举例与不纳入的对象",
      position: 4,
    },
    {
      title: "确认核心定位",
      detail: "按确认的范围综合定位与选择理由",
      position: 5,
    },
    {
      title: "交付品牌资料包",
      detail: "导出定位已确认的新版本资料包",
      position: 7,
    },
  ];
  if (
    mode === "new_reference_pack" ||
    mode === "refresh_reference_pack" ||
    jobKind === "reference_pack" ||
    jobKind === "reference_pack_refresh"
  )
    return packSteps;
  const routeSteps = [
    {
      title: "选择品牌资料包",
      detail: "明确使用已有资料包或先创建新资料包",
      position: 1,
    },
    ...(["reference_pack", "reference_pack_refresh"].includes(jobKind ?? "")
      ? packSteps.slice(1)
      : []),
  ];
  if (
    mode === "p0" ||
    mode === "foundation_article" ||
    mode === "import_foundation"
  )
    return [
      ...routeSteps,
      {
        title: "制作品牌深度文章",
        detail: "使用已确认的定位与比较范围",
        position: 8,
      },
      {
        title: "选择例文",
        detail: "选择例文文风或默认写作规范",
        position: 9,
      },
      {
        title: "确认品牌文章写作方案",
        detail: "确认结构、材料与已有文章的编辑方案",
        position: 10,
      },
      { title: "正文与编辑", detail: "完成品牌文章与候选标题", position: 11 },
      {
        title: "交付品牌文章与资料包",
        detail: "正文文档、网页和新版品牌资料包",
        position: 12,
      },
    ];
  return [
    ...routeSteps,
    {
      title: "正式问题与应答要求",
      detail: "本题的两篇 AI 答案、企业要求与品牌认知",
      position: 13,
    },
    {
      title: "选择文章类型",
      detail: "阅读分析后，选择适合本题的文章类型",
      position: 15,
    },
    { title: "选择例文", detail: "确认文章文风与内容参考", position: 16 },
    {
      title: "问题定位",
      detail: "推荐类文章需确认本题的差异化定位",
      position: 17,
    },
    {
      title: "确认文章写作方案",
      detail: "结构、品牌角度与材料使用",
      position: 18,
    },
    {
      title: "正文与最终交付",
      detail: "正文、编辑、候选标题与交付文件",
      position: 19,
    },
  ];
}

function fileList(files: File[]) {
  return files.map((file) => file.name).join("、");
}

type Deliverable = { fileUrl: string; fileName: string; mimeType: string };
export function contentArtifactUrl(value: string): string | null {
  try {
    const url = new URL(value, window.location.origin);
    return url.origin === window.location.origin &&
      /^\/api\/frontmind\/v2\/artifacts\/[^/]+\/content$/.test(url.pathname)
      ? `${url.pathname}${url.search}`
      : null;
  } catch {
    return null;
  }
}
export function contentProductionFinished(
  progress: ContentProductionDto | null,
) {
  if (
    !progress ||
    progress.source !== "runner_job_state" ||
    progress.confirmation
  )
    return false;
  if (
    progress.jobKind === "reference_pack" ||
    progress.jobKind === "reference_pack_refresh"
  )
    return progress.workflowStatus === "positioning_ready";
  if (progress.jobKind === "p0") return progress.workflowStatus === "p0_ready";
  return (
    progress.jobKind === "article" && progress.workflowStatus === "completed"
  );
}
function ContentProductionInner({
  workbench = false,
  projectId = "content-production",
}: {
  workbench?: boolean;
  projectId?: string;
}) {
  const {useConversation,useSendMessage,captureWorkspaceRestOperation,retrieveTask,useWorkspaceDraftGuard,requestWorkspaceNavigation,Home,FilePreview,AgentWorkbenchShell,WorkbenchTaskToolbar,connections} = useContentWorkspaceHost();
  const currentStandaloneModule = () => !connections?.publishedKnowledge;
  const {
    state,
    activeConversation,
    createConversation,
    setActive,
    deleteConversation,
    hydrated,
  } = useConversation();
  const { sendMessage } = useSendMessage();
  const [showCreate, setShowCreate] = useState(false);
  const [showFiles, setShowFiles] = useState(false);
  const taskCenterTrigger = useRef<HTMLElement | null>(null);
  const [taskCenterTab, setTaskCenterTab] = useState<"new" | "existing">("new");
  const [mode, setMode] = useState<ContentProductionMode | null>(null);
  const [enterpriseName, setEnterpriseName] = useState("");
  const [knowledgeSource, setKnowledgeSource] = useState<"published" | "files">(
    currentStandaloneModule() ? "files" : "published",
  );
  const [questionId, setQuestionId] = useState("");
  const [question, setQuestion] = useState("");
  const [genre, setGenre] = useState<"default"|"industry_roundup">("default");
  const [subjects, setSubjects] = useState("");
  const [articleFocus, setArticleFocus] = useState("");
  const [readerQuestions, setReaderQuestions] = useState("");
  const [excludedTopics, setExcludedTopics] = useState("");
  const [comparisonDimensions, setComparisonDimensions] = useState("");
  const [rejectedClaimIds, setRejectedClaimIds] = useState("");
  const [materials, setMaterials] = useState<File[]>([]);
  const [handoffName, setHandoffName] = useState("");
  const [handoffFile, setHandoffFile] = useState<File | null>(null);
  const [handoffPending, setHandoffPending] = useState(false);
  const [selectedPack, setSelectedPack] = useState("");
  const [pendingStart, setPendingStart] = useState<{
    id: string;
    input: ContentProductionInput;
    files: File[];
    prompt: string;
  } | null>(null);
  const [failedStart, setFailedStart] = useState<{
    id: string;
    input: ContentProductionInput;
    prompt: string;
    files: File[];
  } | null>(null);
  const startSent = useRef(new Set<string>());
  const startLocked = useRef(false);
  const handoffLocked = useRef(false);
  const [draftInputs, setDraftInputs] = useState<
    Record<string, ContentProductionInput>
  >({});
  const [taskRead, setTaskRead] = useState<{
    conversationId: string;
    task: TaskResponse;
  } | null>(null);
  const [notice, setNotice] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [confirmationPending, setConfirmationPending] = useState(false);
  const [acceptedConfirmation, setAcceptedConfirmation] = useState<string | null>(null);
  const currentId = useRef(activeConversation?.id);
  const refreshSequence = useRef(0);
  const readController = useRef<AbortController | null>(null);
  const handoffController = useRef<AbortController | null>(null);
  currentId.current = activeConversation?.id;
  const taskId = activeConversation?.taskId;
  const task =
    taskRead &&
    taskRead.conversationId === activeConversation?.id &&
    taskRead?.task.id === taskId
      ? taskRead.task
      : null;
  const progress = task?.contentProduction ?? null;
  const input = activeConversation
    ? draftInputs[activeConversation.id]
    : undefined;
  const activeMode = progress?.mode ?? input?.mode ?? "new_reference_pack";
  const modeKnown = Boolean(progress || input);
  const modeLabel = !modeKnown
    ? taskId
      ? "正在读取任务信息"
      : (CONTENT_MODES.find((item) => item.value === mode)?.title ?? "尚未选择")
    : CONTENT_MODES.find(
        (item) =>
          item.value === activeMode ||
          (item.value === "p0" &&
            ["foundation_article", "import_foundation"].includes(activeMode)),
      )?.title;
  const busy =
    Boolean(pendingStart) ||
    ["running", "pending"].includes(activeConversation?.status ?? "");
  const createDirty = Boolean(
    mode ||
      enterpriseName.trim() ||
      question.trim() ||
      questionId.trim() ||
      genre !== "default" || subjects.trim() ||
      articleFocus.trim() || readerQuestions.trim() ||
      excludedTopics.trim() || comparisonDimensions.trim() ||
      materials.length,
  );
  useWorkspaceDraftGuard({ dirty: createDirty, label: "新建内容任务" });
  useWorkspaceDraftGuard({dirty: Boolean(rejectedClaimIds.trim()), label: "待提交的事实修复说明"});
  useWorkspaceDraftGuard({
    dirty: Boolean(pendingStart) || handoffPending,
    label: "内容任务正在提交",
  });

  useWorkspaceDraftGuard({
    dirty:
      failedStart?.id === activeConversation?.id &&
      Boolean(failedStart) &&
      !pendingStart,
    label: "待重试的内容任务开场信息和文件",
  });

  const refresh = useCallback(async () => {
    readController.current?.abort();
    const controller = new AbortController();
    readController.current = controller;
    const rest = captureWorkspaceRestOperation(controller.signal);
    const sequence = ++refreshSequence.current;
    const conversationId = currentId.current;
    if (!taskId || !conversationId) {
      setTaskRead(null);
      setRefreshing(false);
      return;
    }
    setRefreshing(true);
    try {
      const result = await retrieveTask(taskId, { signal: rest.signal });
      rest.assertActive();
      if (
        currentId.current === conversationId &&
        sequence === refreshSequence.current
      ) {
        if (
          result.id !== taskId ||
          (result.purpose && result.purpose !== "content_production")
        )
          throw new Error("任务状态与当前内容任务不匹配，请重新读取。");
        setTaskRead({ conversationId, task: result });
        // Acceptance can precede a CLI failure; the original pause is retryable.
        if (["error", "failed", "cancelled"].includes(result.status))
          setAcceptedConfirmation(null);
        setNotice("");
      }
    } catch (error) {
      if (
        !rest.signal.aborted &&
        currentId.current === conversationId &&
        sequence === refreshSequence.current
      )
        setNotice(
          error instanceof Error
            ? error.message
            : "暂时无法读取任务阶段，请稍后刷新。",
        );
    } finally {
      if (
        currentId.current === conversationId &&
        sequence === refreshSequence.current
      )
        setRefreshing(false);
    }
  }, [taskId]);
  useEffect(() => {
    setTaskRead(null);
    setNotice("");
    setSelectedPack("");
    setConfirmationPending(false);
    setAcceptedConfirmation(null);
    setRejectedClaimIds("");
    return () => {
      readController.current?.abort();
      handoffController.current?.abort();
    };
  }, [activeConversation?.id]);
  useEffect(() => {
    void refresh();
  }, [
    refresh,
    activeConversation?.status,
    activeConversation?.messages.length,
    activeConversation?.updatedAt,
  ]);
  useEffect(() => {
    if (
      !pendingStart ||
      activeConversation?.id !== pendingStart.id ||
      startSent.current.has(pendingStart.id)
    )
      return;
    const start = pendingStart;
    startSent.current.add(start.id);
    const rest = captureWorkspaceRestOperation();
    void (async () => {
      try {
        const accepted = await sendMessage(start.prompt, start.files, {
          purpose: "content_production",
          contentProduction: start.input,
        });
        rest.assertActive();
        if (accepted === false)
          throw new Error(
            "开场请求尚未确认成功。已保留本次说明与文件，可在当前任务重试同一开场请求。",
          );
        setFailedStart(null);
      } catch (error) {
        if (!rest.signal.aborted) {
          setFailedStart({
            id: start.id,
            input: start.input,
            prompt: start.prompt,
            files: start.files,
          });
          if (currentId.current === start.id)
            setNotice(
              error instanceof Error
                ? error.message
                : "任务开始未完成，请查看回复。",
            );
        }
      } finally {
        startLocked.current = false;
        if (!rest.signal.aborted)
          setPendingStart((previous) =>
            previous?.id === start.id ? null : previous,
          );
      }
    })();
  }, [pendingStart, activeConversation?.id, sendMessage]);

  function retryStart() {
    const failed = failedStart;
    if (
      !failed ||
      failed.id !== currentId.current ||
      startLocked.current ||
      busy
    )
      return;
    startLocked.current = true;
    startSent.current.delete(failed.id);
    setNotice("");
    // Same mounted sender, text and original File objects preserve its frozen
    // dispatch envelope after an uncertain response; never create a new task.
    setPendingStart({ ...failed });
  }
  function resetCreate() {
    setMode(null);
    setEnterpriseName("");
    setKnowledgeSource(currentStandaloneModule() ? "files" : "published");
    setQuestionId("");
    setQuestion("");
    setGenre("default");
    setSubjects("");
    setArticleFocus("");
    setReaderQuestions("");
    setExcludedTopics("");
    setComparisonDimensions("");
    setMaterials([]);
    setHandoffName("");
    setHandoffFile(null);
  }
  function openTaskCenter(tab: "new" | "existing") {
    if (!showCreate && document.activeElement instanceof HTMLElement)
      taskCenterTrigger.current = document.activeElement;
    setTaskCenterTab(tab);
    setShowCreate(true);
  }
  function openCreate() {
    openTaskCenter("new");
  }
  function closeCreate() {
    // Closing the task center only hides it; the draft and File objects stay
    // mounted until submission or an explicitly approved workspace departure.
    setShowCreate(false);
  }
  function startTask(event: React.FormEvent) {
    event.preventDefault();
    const name = enterpriseName.trim();
    if (
      startLocked.current ||
      !hydrated ||
      !mode ||
      !name
    )
      return;
    if (mode === "refresh_reference_pack" && materials.length === 0) {
      setNotice("请选择需要更新的已有品牌资料包。");
      return;
    }
    const subjectScope = subjects.split(/\r?\n/u).map((item)=>item.trim()).filter(Boolean);
    const questions = readerQuestions.split(/\r?\n/u).map((item)=>item.trim()).filter(Boolean);
    const exclusions = excludedTopics.split(/\r?\n/u).map((item)=>item.trim()).filter(Boolean);
    const dimensions = comparisonDimensions.split(/\r?\n/u).map((item)=>item.trim()).filter(Boolean);
    if (mode === "single_article" && genre === "industry_roundup" && (subjectScope.length < 3 || subjectScope.length > 12 || subjectScope[0]?.toLocaleLowerCase() !== name.toLocaleLowerCase() || new Set(subjectScope.map((item)=>item.toLocaleLowerCase())).size !== subjectScope.length)) {
      setNotice("行业盘点请每行填写一个品牌，共 3—12 个；第一行写本次企业，品牌不能重复。");
      return;
    }
    if (mode === "single_article" && genre === "industry_roundup" && (dimensions.length < 2 || dimensions.length > 8 || new Set(dimensions.map((item)=>item.toLocaleLowerCase())).size !== dimensions.length)) {
      setNotice("行业盘点请填写 2—8 个不重复的共同对比维度。");
      return;
    }
    startLocked.current = true;
    const config: ContentProductionInput = {
      mode,
      enterpriseName: name,
      knowledgeSource,
      monitoringAnswerAssetIds: [],
      ...(mode === "single_article"
        ? {
            question: question.trim(),
            ...(questionId.trim() ? { questionId: questionId.trim() } : {}),
            genre,...(genre === "industry_roundup" ? {subjectScope} : {}),
            ...(articleFocus.trim() ? {articleFocus: articleFocus.trim()} : {}),
            ...(questions.length ? {readerQuestions: questions} : {}),
            ...(exclusions.length ? {excludedTopics: exclusions} : {}),
            ...(genre === "industry_roundup" ? {comparisonDimensions: dimensions} : {}),
          }
        : {}),
    };
    const action = CONTENT_MODES.find((item) => item.value === mode)!.title;
    const prompt = [
      `企业名称：${name}`,
      `本次任务：${action}`,
      knowledgeSource === "published"
        ? "使用我的已发布企业知识库。"
        : materials.length
          ? "使用本次上传的企业材料。"
          : "企业材料或品牌资料包将在后续需要时上传，请先展示本任务的资料选择步骤。",
      mode === "single_article" &&
        question.trim() &&
        `正式问题：${question.trim()}`,
      mode === "single_article" &&
        questionId.trim() &&
        `问题编号：${questionId.trim()}`,
      mode === "single_article" && genre === "industry_roundup" && `文体：行业盘点；主体顺序：${subjectScope.join("、")}`,
      mode === "single_article" && articleFocus.trim() && `本篇聚焦：${articleFocus.trim()}`,
      mode === "single_article" && questions.length > 0 && `需回答的问题：${questions.join("；")}`,
      mode === "single_article" && exclusions.length > 0 && `不展开：${exclusions.join("；")}`,
      mode === "single_article" && genre === "industry_roundup" && `共同对比维度：${dimensions.join("、")}`,
      materials.length > 0 && `附件：${fileList(materials)}`,
      "请按内容制作流程开始，在需要我确认的内容阶段展示结果。",
    ]
      .filter(Boolean)
      .join("\n");
    try {
      const id = createConversation({
        title: `${name} · ${action}`,
        reuseEmpty: false,
        purpose: "content_production",
      });
      setDraftInputs((previous) => ({ ...previous, [id]: config }));
      setPendingStart({ id, input: config, files: [...materials], prompt });
      setShowCreate(false);
      setNotice("");
      resetCreate();
    } catch (error) {
      startLocked.current = false;
      setNotice(
        error instanceof Error ? error.message : "创建任务失败，请重试。",
      );
    }
  }
  const steps = contentProductionLane(activeMode, progress?.jobKind);
  const position = progress
    ? contentProductionStagePosition(progress.currentStage, progress.workflowStatus)
    : 0;
  const finished = contentProductionFinished(progress);
  const packFinished =
    finished &&
    (progress?.jobKind === "reference_pack" ||
      progress?.jobKind === "reference_pack_refresh");
  const handoffAvailable =
    finished && (packFinished || progress?.jobKind === "p0");
  const convertedToPack =
    packFinished &&
    !["new_reference_pack", "refresh_reference_pack"].includes(activeMode);
  const turnFailed = ["error", "failed", "cancelled"].includes(
    task?.status ?? activeConversation?.status ?? "",
  );
  const currentStep =
    position === 0
      ? 0
      : Math.max(
          0,
          steps.findLastIndex((step) => position >= step.position),
        );
  const statusLabel = !modeKnown
    ? taskId
      ? "任务信息待读取"
      : "尚未开始"
    : (task?.status??activeConversation?.status)==="cancelled"
      ? "本轮已取消"
    : turnFailed
      ? "本轮执行失败"
      : progress?.confirmation
        ? "等待内容确认"
        : finished
          ? packFinished
            ? "资料包已交付"
            : "本次任务已完成"
          : busy
            ? "正在执行"
            : progress?.source === "runner_job_state"
              ? "当前阶段"
              : "准备开始";
  const deliverables = [
    ...new Map(
      (activeConversation?.messages ?? [])
        .filter((message) => message.role === "assistant")
        .flatMap((message) => message.outputFiles ?? [])
        .filter(
          (file) =>
            contentArtifactUrl(file.fileUrl) &&
            !/frontmind_workflow_job_(?:snapshot|state)/i.test(file.fileName),
        )
        .map((file) => [file.fileUrl, file]),
    ).values(),
  ];
  const packFiles = deliverables.filter((file) =>
    /\.zip$/i.test(file.fileName),
  );

  async function prepareNextTask(
    nextMode: "p0" | "single_article",
    file: Deliverable,
  ) {
    if (
      handoffLocked.current ||
      !handoffAvailable ||
      !progress ||
      !currentId.current
    )
      return;
    const conversationId = currentId.current;
    const source = { ...file };
    const name = progress.enterpriseName;
    const url = contentArtifactUrl(source.fileUrl);
    if (!url || !/\.zip$/i.test(source.fileName)) return;
    handoffLocked.current = true;
    setHandoffPending(true);
    setNotice("");
    const controller = new AbortController();
    handoffController.current = controller;
    const rest = captureWorkspaceRestOperation(controller.signal);
    try {
      const response = await rest.fetch(url, { credentials: "include" });
      if (!response.ok)
        throw new Error("资料包读取失败，请刷新任务或重新下载后上传。");
      const blob = await response.blob();
      rest.assertActive();
      if (currentId.current !== conversationId) return;
      if (!blob.size || blob.size > 64 * 1024 * 1024)
        throw new Error("资料包为空或超过可复用的文件大小，请检查交付文件。");
      const signature = new Uint8Array(await blob.slice(0, 4).arrayBuffer());
      rest.assertActive();
      if (
        signature[0] !== 0x50 ||
        signature[1] !== 0x4b ||
        ![
          [3, 4],
          [5, 6],
          [7, 8],
        ].some(
          ([third, fourth]) =>
            signature[2] === third && signature[3] === fourth,
        )
      )
        throw new Error("该附件不是有效 ZIP 资料包，请选择正确文件。");
      if (currentId.current !== conversationId) return;
      resetCreate();
      setMode(nextMode);
      setEnterpriseName(name);
      setKnowledgeSource("files");
      const carriedFile = new File([blob], source.fileName, {
        type: "application/zip",
      });
      setHandoffFile(carriedFile);
      setMaterials([carriedFile]);
      setHandoffName(source.fileName);
      openTaskCenter("new");
    } catch (error) {
      if (!rest.signal.aborted && currentId.current === conversationId)
        setNotice(
          error instanceof Error
            ? error.message
            : "资料包复用失败，请重新选择。",
        );
    } finally {
      handoffLocked.current = false;
      setHandoffPending(false);
    }
  }
  const createForm = (
    <form className="cp-task-create-form" onSubmit={startTask}>
      <div className="cp-task-center-body">
        <fieldset className="cp-mode-list">
          <legend>本次要完成什么？</legend>
          {CONTENT_MODES.map((item) => (
            <label
              key={item.value}
              className={mode === item.value ? "is-selected" : ""}
            >
              <input
                type="radio"
                name="content-mode"
                value={item.value}
                checked={mode === item.value}
                onChange={() => setMode(item.value)}
              />
              <span>
                <strong>{item.title}</strong>
                <small>{item.description}</small>
              </span>
            </label>
          ))}
        </fieldset>
        {mode && (
          <>
            {handoffName && (
              <p className="cp-form-context">
                已带入资料包：{contentProductionArtifactName(handoffName)}
                。这是独立的新任务，开始后仍需确认使用已有资料包。
              </p>
            )}
            <label className="cp-field">
              企业名称
              <input
                required
                maxLength={200}
                value={enterpriseName}
                onChange={(event) => setEnterpriseName(event.target.value)}
                placeholder="输入本次任务的企业或品牌名称"
              />
            </label>
            <label className="cp-field">
              企业资料来源
              <select
                aria-label="企业资料来源"
                value={knowledgeSource}
                onChange={(event) =>
                  setKnowledgeSource(
                    event.target.value as "published" | "files",
                  )
                }
              >
                {!currentStandaloneModule() && <option value="published">使用我的已发布企业知识库</option>}
                <option value="files">上传材料（也可在后续步骤补充）</option>
              </select>
              <small>
                企业知识库提供企业事实材料。品牌资料包进一步汇总市场研究、已确认定位和写作资料。文章任务开始后，需要确认使用已有资料包，或先创建资料包。
              </small>
            </label>
            <label className="cp-field">
              {handoffFile
                ? "补充企业材料（可选，已保留带入的资料包）"
                : mode === "refresh_reference_pack"
                  ? "上传已有品牌资料包与补充资料"
                  : "上传材料或品牌资料包（可选）"}
              <input
                type="file"
                multiple
                accept=".zip,.pdf,.docx,.doc,.txt,.md,.json,.csv,.xlsx,.png,.jpg,.jpeg,.webp"
                onChange={(event) => {
                  const selected = Array.from(event.target.files ?? []);
                  if (handoffFile) {
                    setMaterials([
                      handoffFile,
                      ...selected.filter(
                        (file) => file.name !== handoffFile.name,
                      ),
                    ]);
                    if (selected.some((file) => file.name === handoffFile.name))
                      setNotice("已保留带入的资料包，同名附件未重复添加。");
                  } else setMaterials(selected);
                }}
              />
              <small>
                {materials.length
                  ? `已选择：${fileList(materials)}`
                  : "沿用原始文件内容，可在后续对话中补充资料。"}
              </small>
            </label>
            {mode === "single_article" && (
              <>
                <p className="cp-form-context">
                  问题文章需要含已完成品牌文章的品牌资料包，以及来自两个不同 AI
                  平台的两篇完整答案。也可以留空问题，随后从资料包的问题目录中选择，或导入监控问答表。
                </p>
                <label className="cp-field">
                  正式问题（可选）
                  <textarea
                    rows={2}
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    maxLength={20000}
                    placeholder="填写本篇文章要解决的问题，或留空后从资料包中选择"
                  />
                </label>
                <label className="cp-field">
                  问题编号（可选）
                  <input
                    maxLength={200}
                    value={questionId}
                    onChange={(event) => setQuestionId(event.target.value)}
                    placeholder="已有资料包中的问题编号；没有可留空"
                  />
                </label>
                <><label className="cp-field">
                  文章文体
                  <select value={genre} onChange={(event)=>setGenre(event.target.value as "default"|"industry_roundup")}>
                    <option value="default">默认问题文章</option>
                    <option value="industry_roundup">行业盘点（横向选购）</option>
                  </select>
                </label><label className="cp-field">
                  本篇聚焦的细分主题或功能（可选）
                  <input maxLength={300} value={articleFocus} onChange={(event)=>setArticleFocus(event.target.value)} placeholder="例如：高速吹风机的温控和噪音，不写全部个护产品" />
                </label><label className="cp-field">
                  要回答的读者问题（每行一个，可选）
                  <textarea rows={3} value={readerQuestions} onChange={(event)=>setReaderQuestions(event.target.value)} placeholder="例如：不同温控方式有什么区别？" />
                </label><label className="cp-field">
                  本篇不展开的内容（每行一个，可选）
                  <textarea rows={2} value={excludedTopics} onChange={(event)=>setExcludedTopics(event.target.value)} placeholder="例如：剃须刀和电动牙刷" />
                </label>{genre === "industry_roundup" && <><label className="cp-field">
                  对比品牌（每行一个，第一行须为本次企业；共 3—12 个）
                  <textarea rows={5} value={subjects} onChange={(event)=>setSubjects(event.target.value)} placeholder={`例如：\n${enterpriseName || "本次企业"}\n竞品甲\n竞品乙`}/>
                </label><label className="cp-field">
                  共同对比维度（每行一个，2—8 个）
                  <textarea rows={4} value={comparisonDimensions} onChange={(event)=>setComparisonDimensions(event.target.value)} placeholder="例如：\n转速\n温控\n噪音\n价格" />
                </label></>}</>
              </>
            )}
            {notice && (
              <p className="cp-notice" role="alert">
                {notice}
              </p>
            )}
          </>
        )}
      </div>
      {(mode || !workbench) && (
        <footer>
          <button type="button" className="cp-secondary" onClick={closeCreate}>
            取消
          </button>
          <button
            className="cp-primary"
            type="submit"
            disabled={
              !hydrated || !mode || Boolean(pendingStart) || handoffPending
            }
          >
            创建并开始
          </button>
        </footer>
      )}
    </form>
  );
  const showResult = Boolean(activeConversation);
  const confirmationConversation = activeConversation;
  const confirmationKey = confirmationConversation && progress?.confirmation
    ? `${confirmationConversation.id}:${taskId}:${progress.runnerRevision}:${progress.confirmation}`
    : null;
  const confirmationView =
    confirmationConversation && progress?.confirmation && progress.availableActions.length > 0 &&
    !busy && !["running", "pending"].includes(task?.status ?? "") && acceptedConfirmation !== confirmationKey ? (
      <ContentProductionConfirmation
        key={confirmationKey}
        progress={progress}
        busy={busy}
        onPendingChange={setConfirmationPending}
        onAction={async (prompt, files, action) => {
          const id = confirmationConversation.id;
          if (currentId.current !== id)
            throw new Error("任务已切换，请在当前任务重新确认。");
          setNotice("");
          const accepted = await sendMessage(prompt, files, {
            contentProductionAction: action,
          });
          if (accepted === false)
            throw new Error("本轮提交尚未确认成功，请查看任务回复中的提示。");
          if (currentId.current === id) {
            // Do not reopen the consumed pause while an older snapshot is still visible.
            setAcceptedConfirmation(confirmationKey);
            await refresh();
          }
        }}
        onNotice={setNotice}
      />
    ) : null;
  const resultView = showResult ? (
    <div className={`cp-result-surface ${workbench ? "is-agent" : ""}`}>
        <aside className="cp-results" aria-label="任务进度与交付成果">
          <header
            className={`cp-results-heading ${workbench ? "cp-results-heading--agent" : ""}`}
          >
            <div>
              <strong>制作档案</strong>
              <span>阶段进度与交付文件</span>
            </div>
            <button
              aria-label="刷新制作阶段"
              className="cp-icon-button"
              onClick={() => void refresh()}
              disabled={!taskId || refreshing}
            >
              {refreshing ? (
                <Loader2 className="animate-spin" size={18} />
              ) : (
                <RefreshCw size={18} />
              )}
            </button>
          </header>
          <div className="cp-results-scroll">
            {progress?.factGate && !progress.factGate.publishReady && <section className="cp-handoff" role="alert">
              <strong>事实校验未通过{progress.factGate.issueCount > 0 ? `：${progress.factGate.issueCount} 项` : ""}</strong>
              <p>{progress.factGate.categories.join("、")}。原稿和校验结果均已保存；返工会从全文编辑阶段重新运行。</p>
              <label className="cp-field">否决的事实编号（可选，逗号分隔，例如 F01,F03）
                <input value={rejectedClaimIds} onChange={(event)=>setRejectedClaimIds(event.target.value)} placeholder="留空则只按校验问题返工"/>
              </label>
              <button className="cp-primary" disabled={busy || confirmationPending || progress.runnerRevision == null || !progress.availableActions.includes("repair_article_facts")} onClick={async()=>{
                if (startLocked.current) return;
                const ids=[...new Set(rejectedClaimIds.split(/[,，\s]+/u).map((item)=>item.trim()).filter(Boolean))];
                if(ids.some((id)=>!/^F\d{2,4}$/u.test(id))){setNotice("事实编号须为 F01 这样的格式。");return;}
                if(ids.length>100){setNotice("一次最多否决 100 条事实。");return;}
                const conversationId=currentId.current;
                startLocked.current=true;setConfirmationPending(true);setNotice("");
                try {
                  const accepted=await sendMessage("按事实校验结果返工",[],{contentProductionAction:{kind:"repair_article_facts",revision:progress.runnerRevision!,rejectedClaimIds:ids}});
                  if(currentId.current===conversationId && accepted!==false){setRejectedClaimIds("");await refresh();}
                } catch(error) {
                  if(currentId.current===conversationId)setNotice(error instanceof Error?error.message:"事实修复提交失败，请重试。");
                } finally {startLocked.current=false;if(currentId.current===conversationId)setConfirmationPending(false);}
              }}>从编辑阶段返工</button>
            </section>}
            <details
              className="cp-progress"
              open={!finished}
            >
              <summary>
                制作进度 <span>{statusLabel}</span>
              </summary>
              {!modeKnown ? (
                <p className="cp-progress-empty">
                  制作阶段将在本任务的信息读取后显示。
                </p>
              ) : (
                <ol className="cp-lane">
                  {steps.map((step, index) => {
                    const done = finished || index < currentStep;
                    const current = !finished && index === currentStep;
                    return (
                      <li
                        key={step.title}
                      className={done ? "is-done" : current ? "is-current" : ""}
                        aria-current={current ? "step" : undefined}
                      >
                        <span className="cp-step-icon">
                          {done ? <Check size={16} /> : index + 1}
                        </span>
                        <div>
                          <strong>{step.title}</strong>
                          <p>{step.detail}</p>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              )}
            </details>
          {!workbench && confirmationView}
            {handoffAvailable && (
              <section className="cp-handoff">
                <strong>
                  {packFinished
                    ? "品牌资料包已完成"
                    : "品牌文章与新版资料包已完成"}
                </strong>
                <p>
                  {convertedToPack
                    ? "本次选择先创建资料包，文章尚未制作。"
                    : "资料包可用于后续品牌文章与问题文章。"}
                  请选择交付的资料包，创建独立的新任务。
                </p>
                {packFiles.length > 0 ? (
                  <>
                    <label className="cp-field">
                      用于下一任务的资料包
                      <select
                        value={selectedPack}
                      onChange={(event) => setSelectedPack(event.target.value)}
                        disabled={handoffPending}
                      >
                        <option value="">请选择已交付的品牌资料包</option>
                        {packFiles.map((file) => (
                          <option key={file.fileUrl} value={file.fileUrl}>
                            {contentProductionArtifactName(file.fileName)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="cp-confirm-actions">
                      {(["p0", "single_article"] as const).map((next) => (
                        <button
                          key={next}
                          className={
                            next === "p0" ? "cp-primary" : "cp-secondary"
                          }
                          disabled={!selectedPack || handoffPending}
                          onClick={() => {
                            const file = packFiles.find(
                              (item) => item.fileUrl === selectedPack,
                            );
                            if (file)
                              requestWorkspaceNavigation(() => {
                                void prepareNextTask(next, file);
                              });
                          }}
                        >
                          {handoffPending && (
                            <Loader2 size={16} className="animate-spin" />
                          )}
                          {next === "p0"
                            ? "使用此资料包制作品牌文章"
                            : "使用此资料包围绕问题写文章"}
                        </button>
                      ))}
                    </div>
                  </>
                ) : (
                  <p className="cp-muted">
                    交付 ZIP
                    尚未出现在任务附件中。可刷新任务，或下载后在新任务中上传。
                  </p>
                )}
              </section>
            )}
            {
              <section className="cp-deliverables">
                <header>
                  <strong>交付文件</strong>
                  <span>{deliverables.length} 份</span>
                </header>
                {deliverables.length ? (
                  deliverables.map((file) => (
                    <FilePreview
                      key={file.fileUrl}
                      file={{
                        id: file.fileUrl,
                        type: "file",
                        name: contentProductionArtifactName(file.fileName),
                        blobUrl: contentProductionArtifactUrl(
                          contentArtifactUrl(file.fileUrl)!,
                        ),
                      }}
                      className="cp-deliverable-file"
                    />
                  ))
                ) : (
                  <p>
                    任务生成的可用附件会显示在当前步骤，完整说明与表格保存在对话中。
                  </p>
                )}
              </section>
            }
          </div>
        </aside>
    </div>
  ) : null;
  const conversationView = (
    <div className="cp-dialogue">
      <div className="cp-dialogue-heading">
        <div>
          {!workbench && <Sparkles size={18} />}
          <strong>内容协作</strong>
        </div>
        <span>FrontMind 内容智能体</span>
      </div>
      {activeConversation ? (
        <>
          {failedStart?.id === activeConversation.id && (
            <details className="cp-start-recovery">
              <summary>查看已保留的开场信息</summary>
              <p>{failedStart.prompt}</p>
              {failedStart.files.length > 0 && (
                <small>文件：{fileList(failedStart.files)}</small>
              )}
              <div className="cp-confirm-actions">
                <button
                  className="cp-secondary"
                  onClick={retryStart}
                  disabled={busy}
                >
                  重试本次开场请求
                </button>
              </div>
            </details>
          )}
          <div className="cp-chat" id="cp-conversation-panel">
            <Home
              key={activeConversation.id}
              embedded
              operatorWorkspace
              knowledgeEditingBlocked={
                Boolean(pendingStart) || confirmationPending || handoffPending
              }
              hideSidebar
              hidePortalNavigation
              showKnowledgeBaseStarter={false}
              showAccountMenu={false}
              showSettings={false}
              purpose="content_production"
              contentProduction={input}
              standardWelcomeVariant="simple"
              conversationFooter={workbench && confirmationView ? <details className="cp-confirmation-disclosure"><summary><span>写作下一步</span><strong>{statusLabel}</strong><ChevronDown size={16}/></summary>{confirmationView}</details> : undefined}
            />
          </div>
        </>
      ) : (
        <div className="cp-entry-landing">
          <div>
            <h2>
              {state.conversations.length
                ? "继续一个内容任务"
                : "把品牌资料，写成好文章"}
            </h2>
            <p>从一个真实问题出发，研究资料、确认写作方案，再一起打磨正文。</p>
          </div>
          <div className="cp-entry-route" aria-label="内容制作流程"><span>明确任务</span><span>研究选材</span><span>确认方案</span><span>写作修改</span><span>交付稿件</span></div>
          <div className="cp-entry-actions">
            <button
              type="button"
              className="cp-primary"
              onClick={() => openTaskCenter("new")}
              disabled={!hydrated || handoffPending}
            >
              <Plus size={16} />
              新建任务
            </button>
            {state.conversations.length > 0 && (
              <button
                type="button"
                className="cp-secondary"
                onClick={() => openTaskCenter("existing")}
                disabled={!hydrated || Boolean(pendingStart) || handoffPending}
              >
                已有任务
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
  return (
    <section
      className={`cp-workspace ${workbench ? "cp-workspace--agent" : ""}`}
      style={contentTheme}
      aria-label="内容制作"
    >
      {!workbench && (
        <header className="cp-heading">
          <div>
            <span className="cp-kicker">内容工作台</span>
            <h1>内容制作</h1>
          </div>
          <button
            className="cp-primary"
            onClick={openCreate}
            disabled={!hydrated || Boolean(pendingStart) || handoffPending}
          >
            <Plus size={18} />
            新建任务
          </button>
        </header>
      )}
      {!workbench && (
        <div className="cp-taskbar">
          <label className="cp-field cp-task-select">
            当前任务
            <div>
              <select
                aria-label="选择内容制作任务"
                value={activeConversation?.id ?? ""}
                disabled={Boolean(pendingStart) || handoffPending}
                onChange={(event) => {
                  const id = event.target.value;
                  requestWorkspaceNavigation(() => {
                    setFailedStart(null);
                    setActive(id);
                  });
                }}
              >
                <option value="" disabled>
                  选择任务
                </option>
                {state.conversations.map((conversation) => (
                  <option key={conversation.id} value={conversation.id}>
                    {contentProductionTaskTitle(conversation.title)}
                    {["running", "pending"].includes(conversation.status)
                      ? " · 执行中"
                      : conversation.status==="cancelled"
                        ? " · 本轮已取消"
                      : ["error", "failed"].includes(conversation.status)
                        ? " · 本轮失败"
                        : ""}
                  </option>
                ))}
              </select>
              <ChevronDown size={16} />
            </div>
          </label>
          <div className="cp-task-context">
            <strong>
              {activeConversation ? modeLabel : "选择一种任务，开始内容制作"}
            </strong>
            <span>
              {progress?.knowledgeBase
                ? `企业知识库 v${progress.knowledgeBase.version} · ${progress.knowledgeBase.documentCount} 份资料`
                : input?.knowledgeSource === "files"
                  ? "使用上传材料，可在对话中继续补充"
                  : "资料与确认记录随任务保存"}
            </span>
          </div>
          {activeConversation && (
            <span className={`cp-status ${turnFailed ? "is-error" : ""}`}>
              {statusLabel}
            </span>
          )}
        </div>
      )}
      {notice && (
        <div className="cp-notice" role="status">
          {notice}
        </div>
      )}
      {workbench ? (
        <AgentWorkbenchShell
          embedded
          projectId={projectId}
          moduleId="content-production"
          title="内容工作台"
          resultTitle="制作与交付"
          taskTitle={
            activeConversation
              ? contentProductionTaskTitle(activeConversation.title)
              : "新任务"
          }
          taskKey={activeConversation?.id ?? "empty"}
          scrollMain={!activeConversation}
          showResult={showResult}
          topbarActions={
            <button
              type="button"
              className="cp-secondary cp-task-center-trigger"
              onClick={() => openTaskCenter("existing")}
              disabled={!hydrated || Boolean(pendingStart) || handoffPending}
            >
              任务中心
            </button>
          }
          main={
            <div
              className={`cp-main-flow ${activeConversation ? "has-conversation" : ""}`}
            >
              {activeConversation && <header className="cp-task-overview">
                <div className="cp-task-overview-title"><div><span className="cp-task-eyebrow">{modeLabel ?? "内容制作任务"}</span><h2>{progress?.enterpriseName || contentProductionTaskTitle(activeConversation.title)}</h2></div><span className={`cp-status ${turnFailed ? "is-error" : ""}`}>{statusLabel}</span></div>
                <p>{progress?.pauseTitle || (modeKnown ? steps[currentStep]?.detail : "正在读取本次任务的制作进度与成果。")}</p>
                <button type="button" className="cp-mobile-files" onClick={() => setShowFiles(true)}>制作档案 <FileText size={14}/></button>
              </header>}
              {conversationView}
            </div>
          }
          auxiliary={resultView}
          resultKey={activeConversation?.id ?? "empty"}
          status={statusLabel}
        />
      ) : (
        <div className={`cp-body ${!activeConversation ? "is-empty" : ""}`}>
          {conversationView}
          {resultView}
        </div>
      )}
      <Dialog open={showFiles} onOpenChange={setShowFiles}>
        <DialogContent className="cp-mobile-files-dialog" style={contentTheme}>
          <DialogTitle>制作进度与交付文件</DialogTitle>
          <DialogDescription>查看当前阶段与可用成果。</DialogDescription>
          {resultView}
        </DialogContent>
      </Dialog>
      <Dialog
        open={showCreate}
        onOpenChange={(open) => {
          if (!open) closeCreate();
        }}
      >
        <DialogContent
          className="cp-modal cp-task-center-dialog"
          style={contentTheme}
          overlayClassName="cp-modal-overlay"
          showCloseButton={false}
          onCloseAutoFocus={(event) => {
            if (taskCenterTrigger.current?.isConnected) {
              event.preventDefault();
              taskCenterTrigger.current.focus();
            }
          }}
        >
          <header>
            <div>
              <DialogTitle>
                {workbench ? "内容任务中心" : "新建内容任务"}
              </DialogTitle>
              <DialogDescription>
                选择交付目标，或继续已有的制作任务。关闭后保留未提交内容。
              </DialogDescription>
            </div>
            <button
              type="button"
              className="cp-icon-button"
              aria-label="关闭任务中心"
              onClick={closeCreate}
            >
              <X size={20} />
            </button>
          </header>
          <div
            className="cp-task-center-tabs"
            role="tablist"
            aria-label="内容任务中心"
          >
            <button
              type="button"
              role="tab"
              aria-selected={taskCenterTab === "new"}
              onClick={() => setTaskCenterTab("new")}
            >
              新建任务
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={taskCenterTab === "existing"}
              onClick={() => setTaskCenterTab("existing")}
            >
              已有任务
            </button>
          </div>
          {taskCenterTab === "new" ? (
            createForm
          ) : (
            <div className="cp-task-center-body">
            <WorkbenchTaskToolbar
              presentation="panel"
                labels={{
                  newAction: "新建任务",
                  history: "已有任务",
                  noun: "制作任务",
                }}
                tasks={state.conversations.map((item) => ({
                  ...item,
                  title: contentProductionTaskTitle(item.title),
                }))}
              currentId={activeConversation?.id}
              onNew={() => setTaskCenterTab("new")}
                onSelect={(id) => {
                  setFailedStart(null);
                  setActive(id);
                  setShowCreate(false);
                  setTaskCenterTab("new");
                }}
              onDelete={deleteConversation}
              disabled={!hydrated || Boolean(pendingStart) || handoffPending}
            />
            </div>
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}
export type ContentProductionWorkspaceProps = {workbench?:boolean;projectId?:string};
export default function ContentProductionWorkspace({
  workbench = false,
  projectId = "content-production",
}: ContentProductionWorkspaceProps = {}) {
  const {ConversationPurposeProvider} = useContentWorkspaceHost();
  return (
    <ConversationPurposeProvider purpose="content_production">
      <ContentProductionInner workbench={workbench} projectId={projectId} />
    </ConversationPurposeProvider>
  );
}
