const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const MODE_TEXT = {
  topic: { label: "주제", ph: "예: 철근 콘크리트가 강한 이유", hint: "한 줄이면 충분합니다. 리서치 → 대본 → 음성 → 이미지 → 영상까지 자동으로 만듭니다." },
  url: { label: "링크 (유튜브 / 뉴스 / 글)", ph: "https://www.youtube.com/watch?v=...\nhttps://n.news.naver.com/article/...", hint: "유튜브는 자막을 분석하고, 뉴스·커뮤니티 글은 본문과 이미지까지 가져옵니다. 여러 개면 줄바꿈으로 구분하세요." },
  upload: { label: "메모 (선택)", ph: "예: 이 영상과 같은 인물의 최근 인터뷰를 찾아줘", hint: "아래에 참고 영상을 올리고 선택하세요. 음성 내용을 분석하며, Gemini 키 또는 GPT를 쓰면 화면도 분석합니다." },
  auto: { label: "키워드 힌트 (선택)", ph: "비워두면 지금 뜨는 트렌드에서 프리셋에 맞는 주제를 자동으로 고릅니다", hint: "Google Trends(KR) + 뉴스에서 지금 핫한 키워드를 가져와 Claude 가 카테고리에 맞는 걸 고릅니다." },
};
const STAGE_LABEL = { queued: "대기", research: "리서치", script: "대본", tts: "음성", images: "이미지", render: "렌더링", done: "완료", error: "오류" };
const MODE_LABEL = { topic: "주제", url: "URL", upload: "업로드 영상", auto: "핫이슈" };

let mode = "topic";
const streams = {};

// ---------- 모드 탭 ----------
$$(".tab").forEach(b => b.addEventListener("click", () => {
  $$(".tab").forEach(x => x.classList.remove("active"));
  b.classList.add("active");
  mode = b.dataset.mode;
  document.body.dataset.mode = mode;
  const t = MODE_TEXT[mode];
  $("#input-label").textContent = t.label;
  $("#input").placeholder = t.ph;
  $("#input-hint").textContent = t.hint;
  $("#up-label").textContent = mode === "upload" ? "참고 영상 올리기" : "내 파일 첨부";
  $("#up-optional").classList.toggle("hidden", mode === "upload");
  $("#up-hint").textContent = mode === "upload"
    ? "참고 영상의 음성을 분석하고, Gemini 키 또는 GPT를 쓰면 여러 화면도 읽습니다. 관련 영상을 찾아 편집하며 사진을 함께 올릴 수도 있습니다."
    : "AI가 내용을 보고 어울리는 장면에 배치합니다. 남는 장면은 기사 이미지나 AI 생성으로 채웁니다.";
}));
document.body.dataset.mode = mode;

// ---------- 잡 생성 ----------
$("#submit").addEventListener("click", async () => {
  const btn = $("#submit"), msg = $("#submit-msg");
  btn.disabled = true; msg.textContent = "";
  try {
    const problem = llmRequirement();
    if (problem) throw new Error(problem);
    if (mode === "upload" && !$("#reference-file").value) throw new Error("② 소재에서 분석할 영상 파일을 올리고 선택해 주세요.");
    if (!["auto", "upload"].includes(mode) && !$("#input").value.trim()) throw new Error("② 소재에서 주제나 링크를 입력해 주세요.");
    if (referenceLinks($("#instructions").value).length) {
      msg.textContent = "참고 영상 자막을 분석해 지침을 만드는 중입니다...";
      await analyzeInstructionLinks();
    }
    const body = {
      mode,
      input: $("#input").value.trim(),
      preset: $("input[name=preset]:checked").value,
      options: {
        target_seconds: Number($("#opt-seconds").value) || undefined,
        tts_provider: $("#opt-tts").value,
        image_provider: $("#opt-images").value || undefined,
        ...selectedLLM(),
        voice: $("#opt-voice").value.trim() || undefined,
        review: $("#opt-review").checked,
        clip_mode: mode === "url" && $("#opt-clip").checked,
        visual_mode: mode === "url" && $("#opt-related").checked && /(?:youtu\.be|youtube\.com)\//i.test($("#input").value)
          ? "broll" : undefined,
        instructions: $("#instructions").value.trim() || undefined,
        subtitles: $("#opt-subtitles").checked,
        titles: $("#opt-titles").checked,
        style_id: $("#opt-style").value || undefined,
        upload_token: $("#up-list").children.length ? uploadToken : undefined,
        reference_name: mode === "upload" ? $("#reference-file").value : undefined,
      },
    };
    msg.textContent = "";
    const r = await fetch("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || r.statusText);
    onJob(data);
    watch(data.id);
    selectJob(data.id);
    if (mode !== "auto") $("#input").value = "";
    if (body.options.upload_token) {   // 첨부는 잡으로 옮겨가므로 새 토큰으로 갈아끼운다
      uploadToken = Math.random().toString(36).slice(2, 14);
      localStorage.setItem("uploadToken", uploadToken);
      renderUploads([]);
    }
  } catch (e) {
    msg.textContent = "오류: " + e.message;
  } finally {
    btn.disabled = false;
  }
});

// ---------- 파일 첨부 ----------
let uploadToken = localStorage.getItem("uploadToken") || (Math.random().toString(36).slice(2, 14));
localStorage.setItem("uploadToken", uploadToken);

function fmtSize(n) {
  return n >= 1048576 ? (n / 1048576).toFixed(1) + "MB" : Math.max(1, Math.round(n / 1024)) + "KB";
}

function renderUploads(files) {
  const previousReference = $("#reference-file").value;
  const videos = files.filter(f => f.kind === "video");
  $("#reference-file").innerHTML = '<option value="">영상 파일 선택</option>'
    + videos.map(f => `<option value="${esc(f.name)}">${esc(f.name)}</option>`).join("");
  if (videos.some(f => f.name === previousReference)) $("#reference-file").value = previousReference;
  else if (videos.length === 1) $("#reference-file").value = videos[0].name;
  $("#up-count").textContent = files.length ? `${files.length}개 첨부됨` : "";
  $("#up-list").innerHTML = files.map(f => `
    <div class="up-item">
      <span class="up-kind">${f.kind === "video" ? "🎬" : "🖼"}</span>
      <span class="up-name">${esc(f.name)}</span>
      <span class="hint">${fmtSize(f.size)}</span>
      <button class="del" data-name="${esc(f.name)}">✕</button>
    </div>`).join("");
  $$("#up-list .del").forEach(b => b.addEventListener("click", async () => {
    await fetch(`/api/uploads/${uploadToken}?name=${encodeURIComponent(b.dataset.name)}`, { method: "DELETE" });
    refreshUploads();
  }));
}

async function refreshUploads() {
  const r = await fetch("/api/uploads/" + uploadToken);
  if (r.ok) renderUploads((await r.json()).files || []);
}

async function sendFiles(fileList) {
  const files = [...fileList];
  if (!files.length) return;
  const fd = new FormData();
  fd.append("token", uploadToken);
  files.forEach(f => fd.append("files", f));
  $("#up-count").textContent = `올리는 중... (${files.length}개)`;
  try {
    const r = await fetch("/api/uploads", { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || r.statusText);
    if (data.skipped?.length) alert("건너뛴 파일:\n" + data.skipped.join("\n"));
    await refreshUploads();
  } catch (e) {
    $("#up-count").textContent = "업로드 실패: " + e.message;
  }
}

const dz = $("#dropzone");
dz.addEventListener("click", () => $("#up-input").click());
$("#up-input").addEventListener("change", e => { sendFiles(e.target.files); e.target.value = ""; });
["dragenter", "dragover"].forEach(ev => dz.addEventListener(ev, e => {
  e.preventDefault(); dz.classList.add("over");
}));
["dragleave", "drop"].forEach(ev => dz.addEventListener(ev, e => {
  e.preventDefault(); dz.classList.remove("over");
}));
dz.addEventListener("drop", e => sendFiles(e.dataTransfer.files));

// ---------- 스타일 지침 ----------
let styleCache = {};
let editingStyleId = null;

const SM_FIELDS = {
  name: "#sm-name", hook_pattern: "#sm-hook", structure: "#sm-structure", tone: "#sm-tone",
  emotional_arc: "#sm-emotion", sentence_style: "#sm-sentence", pacing: "#sm-pacing", cta: "#sm-cta", notes: "#sm-notes",
};

function selectedLLM() {
  const [llm_provider, llm_model] = $("#opt-llm").value.split("|");
  return { llm_provider, llm_model };
}

let currentServer = null;
async function ensureCurrentServer() {
  if (currentServer === null) {
    const r = await fetch("/openapi.json");
    const spec = await r.json();
    currentServer = !!spec.paths?.["/api/settings/openai-key"];
  }
  if (!currentServer) throw new Error("새 기능을 사용하려면 진행 중인 대본 검토를 마친 뒤 실행 창을 닫고 AI Shorts를 다시 실행해 주세요.");
}

ensureCurrentServer().catch(e => { $("#server-update-msg").textContent = e.message; });

function llmRequirement() {
  const { llm_provider } = selectedLLM();
  if (llm_provider === "openai" && !window.KEYS.openai) return "GPT 사용에는 OpenAI API 키가 필요합니다. 아래에서 키를 등록해 주세요.";
  if (llm_provider === "claude" && !window.KEYS.claude_cli) return "Claude Code 로그인 도구를 찾지 못했습니다. 프로그램을 다시 실행해 주세요.";
  return "";
}

function updateLLMWarning() {
  $("#llm-warn").textContent = llmRequirement();
  if (selectedLLM().llm_provider === "openai" && !window.KEYS.openai) $("#openai-key-setup").open = true;
}
$("#opt-llm").addEventListener("change", updateLLMWarning);
updateLLMWarning();

$("#openai-key-save").addEventListener("click", async () => {
  const key = $("#openai-key-input").value.trim();
  const status = $("#openai-key-status"), btn = $("#openai-key-save");
  if (!key) { status.textContent = "키를 붙여넣어 주세요."; return; }
  btn.disabled = true;
  status.textContent = "저장 중...";
  try {
    await ensureCurrentServer();
    const r = await fetch("/api/settings/openai-key", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: key }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || r.statusText);
    $("#openai-key-input").value = "";
    window.KEYS.openai = true;
    $("#openai-key-badge").classList.replace("no", "ok");
    status.textContent = "저장됨 ✓";
    updateLLMWarning();
  } catch (e) {
    status.textContent = "오류: " + e.message;
  } finally {
    btn.disabled = false;
  }
});

$("#youtube-key-save").addEventListener("click", async () => {
  const key = $("#youtube-key-input").value.trim();
  const status = $("#youtube-key-status");
  if (!key) { status.textContent = "키를 붙여넣어 주세요."; return; }
  const button = $("#youtube-key-save");
  button.disabled = true;
  status.textContent = "저장 중...";
  try {
    const response = await fetch("/api/settings/youtube-key", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: key }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || response.statusText);
    $("#youtube-key-input").value = "";
    window.KEYS.youtube = true;
    $("#youtube-key-badge").classList.replace("no", "ok");
    status.textContent = "저장됨 ✓ 다음 작업부터 댓글 후보가 표시됩니다.";
  } catch (error) { status.textContent = "오류: " + error.message; }
  finally { button.disabled = false; }
});

$("#gemini-key-save").addEventListener("click", async () => {
  const key = $("#gemini-key-input").value.trim();
  const status = $("#gemini-key-status"), button = $("#gemini-key-save");
  if (!key) { status.textContent = "키를 붙여넣어 주세요."; return; }
  button.disabled = true;
  status.textContent = "저장 중...";
  try {
    const response = await fetch("/api/settings/gemini-key", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: key }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || response.statusText);
    $("#gemini-key-input").value = "";
    window.KEYS.gemini = true;
    $("#gemini-key-badge").classList.replace("no", "ok");
    status.textContent = "저장됨 ✓ 다음 작업부터 화면 분석에 사용됩니다.";
    updateImageInfo();
  } catch (error) { status.textContent = "오류: " + error.message; }
  finally { button.disabled = false; }
});

function referenceLinks(text) {
  const refs = [];
  const pattern = /(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com|youtu\.be)\/[^\s<>"']+/gi;
  for (const match of text.matchAll(pattern)) {
    if (match.index > 0 && /[\w.-]/.test(text[match.index - 1])) continue;
    const source = match[0].replace(/[),.;!?]+$/, "");
    const url = /^https?:\/\//i.test(source) ? source : "https://" + source;
    try {
      const parsed = new URL(url);
      const host = parsed.hostname.toLowerCase();
      const isVideo = ["youtube.com", "www.youtube.com", "m.youtube.com"].includes(host)
        ? (parsed.pathname === "/watch" && parsed.searchParams.has("v")) || /^\/(shorts|live)\/[^/]+/.test(parsed.pathname)
        : (host === "youtu.be" || host === "www.youtu.be") && parsed.pathname.length > 1;
      if (isVideo && !refs.some(r => r.url === url)) refs.push({ source, url });
    } catch (_) { /* 입력 중인 불완전한 URL은 무시 */ }
  }
  return refs;
}

function updateInstructionLinks() {
  const count = referenceLinks($("#instructions").value).length;
  $("#instr-analyze").classList.toggle("hidden", !count);
  $("#instr-count").textContent = count ? `참고 영상 ${count}개` : "";
}
$("#instructions").addEventListener("input", updateInstructionLinks);

async function analyzeInstructionLinks() {
  const original = $("#instructions").value;
  const refs = referenceLinks(original);
  if (!refs.length) return;
  if (refs.length > 5) throw new Error("참고 영상은 최대 5개까지 넣을 수 있습니다.");
  const problem = llmRequirement();
  if (problem) throw new Error(problem);
  const btn = $("#instr-analyze"), status = $("#instr-count");
  btn.disabled = true;
  status.textContent = `영상 ${refs.length}개 자막 분석 중...`;
  try {
    await ensureCurrentServer();
    let note = original;
    for (const ref of refs) note = note.replace(ref.source, "");
    const r = await fetch("/api/styles/analyze", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls: refs.map(ref => ref.url), hint: note.trim(), save: false, ...selectedLLM() }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || r.statusText);
    const s = data.style;
    const rows = [
      ["후킹", s.hook_pattern], ["전개 방식", s.structure], ["감정 흐름", s.emotional_arc],
      ["말투", s.tone], ["문장 서술 방식", s.sentence_style], ["호흡·장면 전환", s.pacing],
      ["마무리", s.cta], ["기타", s.notes],
    ];
    $("#instructions").value = "[참고 영상 분석 지침 — " + s.name + "]\n"
      + rows.filter(([, value]) => value).map(([label, value]) => `${label}: ${value}`).join("\n")
      + (note.trim() ? "\n\n[내가 추가한 지침]\n" + note.trim() : "");
    $("#instr-findings-list").innerHTML = (data.findings || []).map(f => `<li>${esc(f)}</li>`).join("");
    $("#instr-findings").classList.toggle("hidden", !(data.findings || []).length);
    updateInstructionLinks();
    status.textContent = `참고 영상 ${refs.length}개 분석 완료 · 지침을 확인하고 수정할 수 있습니다.`;
  } finally {
    btn.disabled = false;
  }
}

$("#instr-analyze").addEventListener("click", async () => {
  try { await analyzeInstructionLinks(); }
  catch (e) { $("#instr-count").textContent = "오류: " + e.message; }
});

async function loadStyleList(selectId) {
  const list = await (await fetch("/api/styles")).json();
  styleCache = Object.fromEntries(list.map(s => [s.id, s]));
  const sel = $("#opt-style");
  const keep = selectId ?? sel.value;
  sel.innerHTML = '<option value="">자동 — 소재를 보고 AI가 구성을 정함</option>'
    + list.map(s => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("");
  if (keep && styleCache[keep]) sel.value = keep;
  onStyleChange();
}

function onStyleChange() {
  const id = $("#opt-style").value;
  $("#edit-style").classList.toggle("hidden", !id);
  $("#style-hint").textContent = id
    ? "이 스타일의 구성·말투를 그대로 따라 대본을 씁니다."
    : "참고할 채널의 영상을 넣으면 그 구성·말투를 분석해 지침으로 저장하고, 그 스타일대로 대본을 씁니다.";
}
$("#opt-style").addEventListener("change", onStyleChange);

let editingSlots = [];      // 스타일의 댓글 자동 배치 자리 (참고 영상 화면 분석 결과)
let editingPattern = "";

function openStyleModal({ analyze, style, findings }) {
  editingStyleId = style ? style.id : null;
  editingSlots = (style && style.comment_slots) || [];
  editingPattern = (style && style.comment_pattern) || "";
  $("#sm-comment-box").classList.toggle("hidden", !editingSlots.length);
  $("#sm-comment-pattern").textContent = editingPattern || `댓글 ${editingSlots.length}개 자리`;
  $("#sm-title").textContent = style ? "스타일 편집" : "스타일 만들기";
  $("#sm-analyze").classList.toggle("hidden", !analyze);
  $("#sm-form").classList.toggle("hidden", analyze);
  $("#sm-delete").classList.toggle("hidden", !style);
  $("#sm-msg").textContent = "";
  $("#sm-progress").textContent = "";
  $("#sm-run").disabled = false;
  for (const [k, sel] of Object.entries(SM_FIELDS)) $(sel).value = (style && style[k]) || "";
  const fbox = $("#sm-findings-box");
  fbox.classList.toggle("hidden", !(findings && findings.length));
  if (findings) $("#sm-findings").innerHTML = findings.map(f => `<li>${esc(f)}</li>`).join("");
  $("#style-modal").classList.remove("hidden");
}

function closeStyleModal() { $("#style-modal").classList.add("hidden"); }
$("#sm-close").addEventListener("click", closeStyleModal);
$("#sm-comment-clear").addEventListener("click", () => {
  editingSlots = [];
  $("#sm-comment-box").classList.add("hidden");
  $("#sm-msg").textContent = "「저장」을 누르면 댓글 자동 배치가 꺼집니다.";
});
$("#style-modal").addEventListener("click", e => { if (e.target.id === "style-modal") closeStyleModal(); });

$("#new-style").addEventListener("click", () => openStyleModal({ analyze: true }));
$("#edit-style").addEventListener("click", () => {
  const s = styleCache[$("#opt-style").value];
  if (s) openStyleModal({ analyze: false, style: s });
});

$("#sm-run").addEventListener("click", async () => {
  const urls = $("#sm-urls").value.split(/\n+/).map(s => s.trim()).filter(Boolean);
  if (!urls.length) return alert("참고 영상 주소를 1개 이상 넣어주세요.");
  const btn = $("#sm-run"), prog = $("#sm-progress");
  const problem = llmRequirement();
  if (problem) { prog.textContent = "오류: " + problem; return; }
  const commentLayout = $("#sm-comment-layout").checked;
  if (commentLayout && !window.KEYS.gemini && !window.KEYS.openai) {
    prog.textContent = "오류: 댓글 배치 분석에는 Gemini 또는 OpenAI 키가 필요합니다. ⚙ 설정에서 등록하거나 체크를 끄세요.";
    return;
  }
  btn.disabled = true;
  let dots = 0;
  const timer = setInterval(() => { dots = (dots + 1) % 4; prog.textContent = `영상 ${urls.length}개 분석 중${".".repeat(dots)}`; }, 600);
  try {
    await ensureCurrentServer();
    const r = await fetch("/api/styles/analyze", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls, hint: $("#sm-hint").value.trim(), save: true, comment_layout: commentLayout, ...selectedLLM() }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || r.statusText);
    await loadStyleList(data.style.id);
    openStyleModal({ analyze: false, style: data.style, findings: data.findings });
    $("#sm-msg").textContent = "분석 완료 · 저장됨 ✓ 내용을 고친 뒤 다시 저장할 수 있습니다";
  } catch (e) {
    prog.textContent = "오류: " + e.message;
  } finally {
    clearInterval(timer);
    btn.disabled = false;
  }
});

$("#sm-save").addEventListener("click", async () => {
  const body = Object.fromEntries(Object.entries(SM_FIELDS).map(([k, sel]) => [k, $(sel).value.trim()]));
  if (!body.name) return alert("스타일 이름을 입력하세요.");
  body.source_urls = (editingStyleId && styleCache[editingStyleId]?.source_urls) || [];
  body.comment_slots = editingSlots;
  body.comment_pattern = editingSlots.length ? editingPattern : "";
  const btn = $("#sm-save");
  btn.disabled = true;
  try {
    const url = editingStyleId ? "/api/styles/" + editingStyleId : "/api/styles";
    const r = await fetch(url, {
      method: editingStyleId ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || r.statusText);
    await loadStyleList(data.id);
    $("#sm-msg").textContent = "저장됨 ✓";
    setTimeout(closeStyleModal, 800);
  } catch (e) {
    $("#sm-msg").textContent = "오류: " + e.message;
  } finally {
    btn.disabled = false;
  }
});

$("#sm-delete").addEventListener("click", async () => {
  if (!editingStyleId || !confirm("이 스타일을 삭제할까요?")) return;
  await fetch("/api/styles/" + editingStyleId, { method: "DELETE" });
  await loadStyleList("");
  closeStyleModal();
});

// ---------- 이미지 provider: 키 경고 + 예상 비용 ----------
// [필요한 키, 경고 문구, 장당 원화]
const IMG_INFO = {
  none: [null, "AI 생성을 하지 않습니다. 첨부·기사 이미지로 못 채운 장면은 단색 카드가 됩니다.", 0],
  "gemini-lite": ["gemini", "GEMINI_API_KEY 가 없어 단색 카드로 만들어집니다. aistudio.google.com/apikey 에서 발급", 49],
  "gemini": ["gemini", "GEMINI_API_KEY 가 없어 단색 카드로 만들어집니다. aistudio.google.com/apikey 에서 발급", 97],
  "gemini-pro": ["gemini", "GEMINI_API_KEY 가 없어 단색 카드로 만들어집니다. aistudio.google.com/apikey 에서 발급", 194],
  fal: ["fal", "FAL_KEY 가 없어 단색 카드로 만들어집니다. fal.ai 에서 발급", 4],
  huggingface: ["hf", "HF_TOKEN 이 없어 단색 카드로 만들어집니다. huggingface.co/settings/tokens 에서 무료 발급", 0],
  openai: ["openai", "OPENAI_API_KEY 가 없어 단색 카드로 만들어집니다.", 150],
  pollinations: [null, "무료지만 화질이 낮고 워터마크가 붙습니다.", 0],
};
const SEC_PER_SCENE = 7;   // 장면 하나당 대략 7초

function updateImageInfo() {
  const v = $("#opt-images").value;
  const warnEl = $("#img-warn"), costEl = $("#img-cost");
  if (!v) {   // 프리셋 기본값 사용
    warnEl.textContent = "";
    costEl.textContent = "프리셋에 설정된 provider 를 사용합니다.";
    return;
  }
  const [key, msg, won] = IMG_INFO[v] || [null, "", 0];
  const missing = key && !(window.KEYS || {})[key];
  warnEl.textContent = missing ? "⚠ " + msg : (key ? "" : "ℹ " + msg);

  const secs = Number($("#opt-seconds").value) || 55;
  const scenes = Math.max(6, Math.min(10, Math.round(secs / SEC_PER_SCENE)));
  costEl.textContent = won
    ? `예상 이미지 비용 약 ${(won * scenes).toLocaleString()}원 (${scenes}장 × ${won}원)`
    : "이미지 비용 0원";
}
$("#opt-images").addEventListener("change", updateImageInfo);
$("#opt-seconds").addEventListener("input", updateImageInfo);
updateImageInfo();

// ---------- 프리셋 지침 편집 ----------
let presetCache = {};

async function loadPresets() {
  const list = await (await fetch("/api/presets")).json();
  presetCache = Object.fromEntries(list.map(p => [p.id, p]));
  updateBrollWarn();
}

function currentPresetId() { return $("input[name=preset]:checked").value; }

// 짜깁기 프리셋을 고르면 저작권 경고를 띄운다
function updateBrollWarn() {
  const p = presetCache[currentPresetId()];
  $("#broll-warn").style.display = (p && p.visual_mode === "broll") ? "block" : "none";
}
$$("input[name=preset]").forEach(r => r.addEventListener("change", updateBrollWarn));

$("#edit-preset").addEventListener("click", async () => {
  if (!Object.keys(presetCache).length) await loadPresets();
  const p = presetCache[currentPresetId()];
  if (!p) return;
  $("#pm-id").textContent = p.name || p.id;
  $("#pm-name").value = p.name || "";
  $("#pm-description").value = p.description || "";
  $("#pm-tone").value = p.tone || "";
  $("#pm-rules").value = (p.script_rules || "").trim();
  $("#pm-image").value = p.image_style || "";
  $("#pm-suffix").value = p.research_queries_suffix || "";
  $("#pm-highlight").value = (p.subtitle && p.subtitle.highlight) || "#FFD400";
  $("#pm-size").value = (p.subtitle && p.subtitle.size) || 74;
  $("#pm-msg").textContent = "";
  $("#preset-modal").classList.remove("hidden");
});

function closeModal() { $("#preset-modal").classList.add("hidden"); }
$("#pm-close").addEventListener("click", closeModal);
$("#preset-modal").addEventListener("click", e => { if (e.target.id === "preset-modal") closeModal(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") { closeModal(); closeStyleModal(); } });

$("#pm-save").addEventListener("click", async () => {
  const id = currentPresetId();
  const body = {
    name: $("#pm-name").value.trim(),
    description: $("#pm-description").value.trim(),
    tone: $("#pm-tone").value.trim(),
    script_rules: $("#pm-rules").value.trim() + "\n",
    image_style: $("#pm-image").value.trim(),
    research_queries_suffix: $("#pm-suffix").value.trim(),
    subtitle: { highlight: $("#pm-highlight").value, size: Number($("#pm-size").value) || 74 },
  };
  $("#pm-save").disabled = true;
  try {
    const r = await fetch("/api/presets/" + id, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || r.statusText);
    presetCache[id] = data;
    // 버튼 라벨 갱신
    const card = $(`input[name=preset][value="${id}"]`).closest(".preset");
    $(".preset-name", card).textContent = data.name;
    $(".preset-desc", card).textContent = data.description;
    $("#pm-id").textContent = data.name;
    $("#pm-msg").textContent = "저장됨 ✓ 다음 영상부터 적용됩니다";
    setTimeout(closeModal, 900);
  } catch (e) {
    $("#pm-msg").textContent = "오류: " + e.message;
  } finally {
    $("#pm-save").disabled = false;
  }
});

// ---------- 상태 ----------
const jobs = {};            // id → 서버가 보낸 최신 job
let currentJobId = null;    // null 이면 새 프로젝트 작성 중
let step = "";
let reviewFor = null;       // ④~⑥ 을 채운 job id
let reviewScript = null;
let sceneFiles = {};        // ⑥ 장면별로 올린 파일 {원래 장면 번호: {name, kind}}
let tl = null;              // ⑦ 에서 고치는 중인 timeline
let capFor = null;
let capDirty = false;
let capcutRoot = null;

const REVIEW_STEPS = ["script", "voice", "visuals"];
const DONE_STEPS = ["captions", "export"];
const STEP_OFF_HINT = {
  source: "새 프로젝트에서만 씁니다. ① 프로젝트 목록에서 「새로 만들기」를 누르세요.",
  style: "새 프로젝트에서만 씁니다. ① 프로젝트 목록에서 「새로 만들기」를 누르세요.",
  script: "대본이 나오면(검토 대기 중) 열립니다.", voice: "대본이 나오면(검토 대기 중) 열립니다.",
  visuals: "대본이 나오면(검토 대기 중) 열립니다.",
  captions: "영상이 완성되면 열립니다.", export: "영상이 완성되면 열립니다.",
};

function currentJob() { return currentJobId ? jobs[currentJobId] : null; }
function jobTitle(j) { return (j.result && j.result.topic) || j.input || "(자동 선택)"; }
function hasVideo(j) { return !!(j && j.result && j.result.video); }
function hasTimeline(j) { return !!(j && j.result && j.result.timeline); }
function videoUrl(j) { return `/files/${j.id}/final.mp4?v=${encodeURIComponent(j.result.rendered_at || "")}`; }
async function api(url, opts = {}) {
  const r = await fetch(url, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
}
const jsonOpts = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

// ---------- 단계 이동 ----------
function stepEnabled(s, j = currentJob()) {
  if (s === "projects" || s === "settings") return true;
  if (s === "source" || s === "style") return !j;
  if (REVIEW_STEPS.includes(s)) return !!j && j.status === "awaiting_review" && !!j.script;
  if (DONE_STEPS.includes(s)) return hasVideo(j) && j.status !== "error";
  return false;
}

function go(s) {
  if (!stepEnabled(s)) return;
  if (step === "captions" && s !== "captions" && capDirty) {
    if (!confirm("저장하지 않은 자막·댓글 수정이 있습니다. 버리고 이동할까요?")) return;
    capDirty = false; capFor = null;
  }
  step = s;
  $$(".panel").forEach(p => p.classList.toggle("hidden", p.dataset.panel !== s));
  if (REVIEW_STEPS.includes(s) && reviewFor !== currentJobId) fillReview(currentJob());
  if (s === "visuals") renderVisuals();
  if (s === "captions") loadCaptions();
  if (s === "export") renderExport();
  updateNav();
  window.scrollTo(0, 0);
}

function autoStep() {
  const j = currentJob();
  if (!j) return go("source");
  if (j.status === "awaiting_review" && j.script) return go("script");
  if (hasVideo(j) && j.status === "done") return go(hasTimeline(j) ? "captions" : "export");
  go("projects");
}

function updateNav() {
  const j = currentJob();
  $$(".sidebar .step").forEach(b => {
    const on = stepEnabled(b.dataset.step, j);
    b.disabled = !on;
    b.title = on ? "" : (STEP_OFF_HINT[b.dataset.step] || "");
    b.classList.toggle("active", b.dataset.step === step);
  });
  $("#cur-title").textContent = j ? jobTitle(j) : "새 프로젝트";
  $("#cur-status").textContent = j ? statusText(j) : "② 소재부터 입력하세요";
  $$("#jobs .job-row").forEach(r => r.classList.toggle("current", r.dataset.id === currentJobId));
}

$$(".sidebar .step").forEach(b => b.addEventListener("click", () => go(b.dataset.step)));
$$("[data-go]").forEach(b => b.addEventListener("click", () => go(b.dataset.go)));
$("#cur-box").addEventListener("click", () => go("projects"));
$("#new-project").addEventListener("click", newProject);

function newProject() {
  if (step === "captions" && capDirty && !confirm("저장하지 않은 자막·댓글 수정이 있습니다. 버릴까요?")) return;
  capDirty = false;
  currentJobId = null;
  renderRun(null);
  go("source");
}

function selectJob(id) {
  if (id === currentJobId) return autoStep();   // 같은 작업을 다시 누르면 고치던 내용은 그대로 둔다
  if (capDirty && !confirm("저장하지 않은 자막·댓글 수정이 있습니다. 버릴까요?")) return;
  capDirty = false; capFor = null; tl = null;
  currentJobId = id;
  renderRun(currentJob());
  autoStep();
}

// ---------- 잡 업데이트 ----------
function statusText(j) {
  if (j.status === "error") return "오류";
  if (j.status === "awaiting_review") return "대본 검토 대기";
  if (j.status === "done") return "완성";
  return `${STAGE_LABEL[j.stage] || j.stage} 진행 중`;
}

function onJob(job) {
  const prev = jobs[job.id];
  jobs[job.id] = job;
  renderRow(job);
  if (job.id !== currentJobId) return;
  renderRun(job);
  const changed = !prev || prev.status !== job.status;
  if (changed) {
    if (job.status === "awaiting_review") { reviewFor = null; go("script"); }
    else if (job.status === "done") {
      if (step === "captions") { capFor = null; loadCaptions(); }
      else if (step === "export") renderExport();
      else autoStep();
    } else if (!stepEnabled(step)) go("projects");
  }
  if (step === "captions") setCapBusy(job.status !== "done");
  if (step === "export") setExportBusy(job.status !== "done");
  updateNav();
}

function renderRun(j) {
  const bar = $("#runbar");
  const failedRerender = j && j.status === "done" && /^다시 만들기 실패/.test(j.message || "");
  const show = j && (["queued", "running", "error"].includes(j.status) || failedRerender);
  bar.classList.toggle("hidden", !show);
  if (!show) return;
  bar.className = "card " + j.status;
  $("#run-title").textContent = jobTitle(j);
  $("#run-stage").textContent = STAGE_LABEL[j.stage] || j.stage;
  $("#run-bar").style.width = (j.status === "done" ? 100 : stagePct(j)) + "%";
  $("#run-msg").textContent = j.status === "error" ? "오류: " + (j.error || j.message) : j.message;
  $("#run-logs").textContent = (j.logs || []).join("\n");
}

function renderRow(job) {
  let el = $(`#jobs .job-row[data-id="${job.id}"]`);
  if (!el) {
    el = document.createElement("div");
    el.className = "job-row";
    el.dataset.id = job.id;
    el.innerHTML = `<div class="thumb"></div>
      <div class="row-main">
        <div class="badges"><span class="badge mode"></span><span class="badge preset"></span></div>
        <strong class="title"></strong>
        <div class="status"></div>
        <div class="progress"><div class="bar"></div></div>
      </div>
      <div class="row-side"><span class="created"></span><button class="del" title="삭제" type="button">✕</button></div>`;
    el.addEventListener("click", e => { if (!e.target.closest(".del")) selectJob(job.id); });
    $(".del", el).addEventListener("click", async () => {
      if (!confirm("이 작업과 결과 파일을 삭제할까요?")) return;
      await fetch("/api/jobs/" + job.id, { method: "DELETE" });
      delete jobs[job.id];
      el.remove();
      $("#jobs-empty").classList.toggle("hidden", !!$("#jobs .job-row"));
      if (currentJobId === job.id) { capDirty = false; newProject(); go("projects"); }
    });
    // 최신 작업이 위로
    const after = $$("#jobs .job-row").find(r => (jobs[r.dataset.id]?.created || "") < (job.created || ""));
    after ? $("#jobs").insertBefore(el, after) : $("#jobs").append(el);
    $("#jobs-empty").classList.add("hidden");
  }
  el.className = `job-row ${job.status}` + (job.id === currentJobId ? " current" : "");
  $(".mode", el).textContent = MODE_LABEL[job.mode] || job.mode;
  $(".preset", el).textContent = (presetCache[job.preset] || {}).name || job.preset;
  const styleName = (job.result && job.result.style) || (styleCache[job.options?.style_id] || {}).name || "";
  let sb = $(".style-badge", el);
  if (styleName && !sb) { sb = document.createElement("span"); sb.className = "badge style-badge"; $(".badges", el).append(sb); }
  if (sb) styleName ? (sb.textContent = "🎬 " + styleName) : sb.remove();
  $(".title", el).textContent = jobTitle(job);
  $(".title", el).title = job.options?.instructions ? "지침: " + job.options.instructions : "";
  $(".created", el).textContent = (job.created || "").replace("T", " ").slice(0, 16);
  $(".status", el).textContent = job.status === "error" ? "오류: " + (job.error || job.message)
    : `${statusText(job)} · ${job.message || ""}`;
  $(".bar", el).style.width = (job.status === "done" ? 100 : stagePct(job)) + "%";
  const thumb = $(".thumb", el);
  const want = hasVideo(job) ? `/files/${job.id}/thumb.jpg?v=${encodeURIComponent(job.result.rendered_at || "")}` : "";
  if (thumb.dataset.src !== want) {
    thumb.dataset.src = want;
    thumb.innerHTML = want ? `<img src="${want}" alt="">` : "";
  }
}

function descriptionWithSources(description, sources) {
  const extra = [...new Set((sources || []).filter(url => url && !(description || "").includes(url)))];
  return (description || "") + (extra.length ? "\n\n" + extra.join("\n") : "");
}

function stagePct(job) {
  const order = ["research", "script", "tts", "images", "render"];
  const i = order.indexOf(job.stage);
  if (i < 0) return 0;
  return Math.round((i * 100 + (job.pct || 0)) / order.length);
}

// ---------- ④ 대본 · ⑤ 음성 · ⑥ 화면 배치 ----------
function fillReview(job) {
  if (!job || !job.script) return;
  reviewFor = job.id;
  reviewScript = job.script;
  const result = job.result || {};
  const reference = result.reference;
  $("#rv-reference").classList.toggle("hidden", !reference);
  if (reference) $("#rv-reference").textContent = `참고 영상 분석: ${reference.topic} · ${reference.summary}`;

  const sources = result.source_candidates || [];
  $("#rv-sources").classList.toggle("hidden", !sources.length);
  $("#rv-sources .source-list").innerHTML = sources.map((s, i) => `<label class="candidate">
    <input type="checkbox" data-source-index="${i}" checked>
    <span>${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title || s.url)}</a>` : esc(s.title || "내 영상")}
    <small>${esc(s.channel || "")} · ${Math.round(s.duration || 0)}초</small></span>
  </label>`).join("");

  const comments = result.comment_candidates || [];
  $("#rv-comments").classList.toggle("hidden", !sources.length && !comments.length);
  const clist = $("#rv-comments .comment-list");
  clist.innerHTML = comments.length ? comments.map(c => `<label class="candidate">
    <input type="checkbox" data-comment-id="${esc(c.id)}">
    <span><a href="${esc(c.url)}" target="_blank" rel="noopener noreferrer">${esc(c.text)}</a>
    <small>좋아요 ${c.likes || 0}개 · 원문 확인</small></span>
  </label>`).join("") : '<p class="hint">댓글 후보가 없습니다. 필요하면 ⚙ 설정에서 YouTube Data API 키를 등록하세요. 완성 후 ⑦ 에서 댓글 캡처를 직접 넣을 수도 있습니다.</p>';
  const suggested = result.suggested_comment_ids || [];
  suggested.forEach(id => { const box = $$("[data-comment-id]", clist).find(x => x.dataset.commentId === id); if (box) box.checked = true; });
  if (suggested.length) clist.insertAdjacentHTML("afterbegin",
    `<p class="hint">스타일의 댓글 배치에 맞춰 좋아요가 많은 댓글 ${suggested.length}개를 미리 골라 뒀습니다. 바꿔도 됩니다.</p>`);
  clist.onchange = () => {
    const checked = $$("[data-comment-id]:checked", clist);
    if (checked.length > 2) { checked.at(-1).checked = false; alert("댓글은 최대 2개까지 선택할 수 있습니다."); }
  };

  const box = $("#rv-scenes");
  box.innerHTML = "";
  job.script.scenes.forEach((s, i) => {
    const row = document.createElement("div");
    row.className = "scene";
    row.dataset.orig = i;
    row.innerHTML = `<div class="num">${i + 1}</div>
      <textarea rows="2" data-k="narration">${esc(s.narration)}</textarea>
      <input type="text" data-k="on_screen_text" value="${esc(s.on_screen_text)}" placeholder="화면 키워드">`;
    box.append(row);
  });

  // ⑤ 음성 기본값: 이 작업을 만들 때 고른 값
  $("#rv-tts").value = job.options?.tts_provider || $("#opt-tts").value || "edge";
  $("#rv-voice").value = job.options?.voice || "";
  updateTTSWarn();
  $("#approve").disabled = false;
  $("#approve-msg").textContent = "";

  sceneFiles = {};
  api(`/api/jobs/${job.id}/scene-visuals`).then(files => { sceneFiles = files || {}; if (step === "visuals") renderVisuals(); })
    .catch(() => {});
}

function reviewRows() {
  return $$("#rv-scenes .scene").map(row => ({
    orig: Number(row.dataset.orig),
    narration: $("[data-k=narration]", row).value.trim(),
    keyword: $("[data-k=on_screen_text]", row).value.trim(),
  }));
}

function updateTTSWarn() {
  const need = { openai: "openai", elevenlabs: "elevenlabs", typecast: "typecast" }[$("#rv-tts").value];
  $("#rv-tts-warn").textContent = need && !window.KEYS[need] ? "⚠ 이 음성은 API 키가 필요합니다 (.env). 키가 없으면 음성 만들기에서 실패합니다." : "";
}
$("#rv-tts").addEventListener("change", updateTTSWarn);

function renderVisuals() {
  const job = currentJob();
  if (!job || !reviewScript) return;
  let n = 0;
  $("#rv-visuals").innerHTML = reviewRows().map(r => {
    const kept = !!r.narration;
    const f = sceneFiles[r.orig];
    const url = f ? `/files/${job.id}/uploads/${encodeURIComponent(f.name)}` : "";
    const preview = !f ? '<div class="vis-empty">자동</div>'
      : f.kind === "video" ? `<video src="${url}" muted preload="metadata"></video>` : `<img src="${url}" alt="">`;
    return `<div class="vis-row${kept ? "" : " removed"}" data-orig="${r.orig}">
      <div class="num">${kept ? ++n : "✕"}</div>
      <div class="vis-thumb">${preview}</div>
      <div class="vis-text"><strong>${esc(r.keyword || "(키워드 없음)")}</strong>
        <span class="hint">${kept ? esc(r.narration.slice(0, 70)) : "④ 에서 나레이션을 비워 삭제된 장면"}</span>
        <span class="hint vis-file">${f ? "✓ " + esc(f.name.replace(/^scene_\d\d_/, "")) : "올린 파일 없음 → 첨부·기사 이미지나 대체 카드로 채움"}</span></div>
      ${kept ? `<label class="scene-up" title="이 장면에 쓸 이미지·영상 올리기">＋ 파일
        <input type="file" accept="image/*,video/*" hidden data-scene="${r.orig}"></label>` : ""}
    </div>`;
  }).join("");
  $$('#rv-visuals input[type=file]').forEach(inp => inp.addEventListener("change", async e => {
    const file = e.target.files[0];
    if (!file) return;
    const idx = Number(inp.dataset.scene);
    const cell = $(".vis-file", inp.closest(".vis-row"));
    cell.textContent = "올리는 중...";
    const fd = new FormData();
    fd.append("scene", String(idx));
    fd.append("file", file);
    try {
      const data = await api(`/api/jobs/${job.id}/scene-visual`, { method: "POST", body: fd });
      sceneFiles[idx] = { name: data.name, kind: data.kind };
      renderVisuals();
    } catch (err) {
      cell.textContent = "실패: " + err.message;
    }
  }));
}

$("#rv-copy-prompts").addEventListener("click", () => {
  if (!reviewScript) return;
  const rows = reviewRows().filter(r => r.narration);
  const text = rows.map((r, i) => `[${i + 1}번 장면] ${r.keyword}\n${reviewScript.scenes[r.orig].image_prompt}`).join("\n\n");
  navigator.clipboard.writeText(text).then(() => {
    const b = $("#rv-copy-prompts");
    b.textContent = "복사됨 ✓ Flow에 붙여넣으세요";
    setTimeout(() => b.textContent = "장면별 이미지 프롬프트 복사", 2200);
  });
});

$("#approve").addEventListener("click", async () => {
  const job = currentJob();
  if (!job || !reviewScript) return;
  const scenes = [], sceneMap = [];
  reviewRows().forEach(r => {
    if (!r.narration) return;
    scenes.push({ ...reviewScript.scenes[r.orig], narration: r.narration, on_screen_text: r.keyword });
    sceneMap.push(r.orig);
  });
  if (!scenes.length) return alert("장면이 하나 이상 필요합니다. ④ 대본을 확인하세요.");
  const btn = $("#approve");
  btn.disabled = true;
  $("#approve-msg").textContent = "시작하는 중...";
  try {
    await api(`/api/jobs/${job.id}/approve`, jsonOpts("POST", {
      script: { ...reviewScript, scenes },
      source_indexes: $$("#rv-sources [data-source-index]:checked").map(x => Number(x.dataset.sourceIndex)),
      comment_ids: $$("#rv-comments [data-comment-id]:checked").map(x => x.dataset.commentId),
      tts_provider: $("#rv-tts").value,
      voice: $("#rv-voice").value.trim(),
      scene_map: sceneMap,
    }));
    $("#approve-msg").textContent = "렌더링을 시작했습니다. 완성되면 ⑦ 자막·댓글로 이동합니다.";
  } catch (e) {
    $("#approve-msg").textContent = "오류: " + e.message;
    btn.disabled = false;
  }
});

// ---------- ⑦ 자막·댓글 ----------
const POSITIONS = [["top", "위", 0.25], ["mid", "가운데", 0.42], ["low", "아래", 0.6]];

function setVideo(el, j) {
  const src = videoUrl(j);
  if (el.dataset.src !== src) {
    el.src = src;
    el.poster = `/files/${j.id}/thumb.jpg?v=${encodeURIComponent(j.result.rendered_at || "")}`;
    el.dataset.src = src;
  }
}

async function loadCaptions() {
  const j = currentJob();
  if (!j || !hasVideo(j)) return;
  setVideo($("#cap-video"), j);
  const ok = hasTimeline(j);
  $("#cap-unavailable").classList.toggle("hidden", ok);
  $$("#cap-editor .cap-body").forEach(b => b.classList.toggle("hidden", !ok));
  if (!ok) return;
  if (capFor !== j.id || !tl) {
    try {
      tl = await api(`/api/jobs/${j.id}/timeline`);
      capFor = j.id;
      capDirty = false;
      renderCaptions();
    } catch (e) {
      $("#cap-msg").textContent = "불러오기 실패: " + e.message;
    }
  }
  setCapBusy(j.status !== "done");
}

function totalDur() { return tl.scenes.reduce((a, s) => a + s.duration, 0); }
function fmt(t) { return (Math.round(t * 10) / 10).toFixed(1); }
function markDirty() { capDirty = true; $("#cap-msg").textContent = "저장 안 됨 · 「저장」 또는 「적용해서 다시 만들기」"; }

function renderCaptions() {
  const sub = tl.subtitles;
  $("#cap-sub-on").checked = !!sub.enabled;
  $("#cap-title-on").checked = sub.titles_enabled !== false;
  $("#cap-lines").classList.toggle("off", !sub.enabled);
  $("#cap-titles").classList.toggle("off", sub.titles_enabled === false);

  $("#cap-lines").innerHTML = sub.lines.length ? sub.lines.map((ln, i) => `<div class="cap-line" data-i="${i}">
      <button class="icon seek" type="button" title="이 위치로 이동">▶</button>
      <input type="number" step="0.1" min="0" data-f="start" value="${fmt(ln.start)}" aria-label="시작(초)">
      <input type="number" step="0.1" min="0" data-f="end" value="${fmt(ln.end)}" aria-label="끝(초)">
      <input type="text" data-f="text" value="${esc(ln.text)}" aria-label="자막 문구">
      <button class="icon del-line" type="button" title="이 줄 삭제">✕</button>
    </div>`).join("") : '<p class="hint">자막 줄이 없습니다.</p>';

  $("#cap-titles").innerHTML = tl.scenes.map((s, i) => `<label class="cap-title">
      <span class="hint">${i + 1} · ${fmt(s.start)}초</span>
      <input type="text" data-scene="${i}" value="${esc(s.title)}" placeholder="(키워드 없음)"></label>`).join("");

  const jid = currentJobId;
  $("#cap-comments").innerHTML = (tl.comments || []).map((c, i) => {
    const pos = POSITIONS.reduce((best, p) => Math.abs(p[2] - c.y) < Math.abs(best[2] - c.y) ? p : best);
    const body = c.kind === "image"
      ? `<img src="/files/${jid}/${c.path.split("/").map(encodeURIComponent).join("/")}" alt="">`
      : `<textarea rows="2" data-f="text">${esc(c.text)}</textarea>`;
    return `<div class="cap-comment" data-i="${i}">
      <div class="cc-body">${body}<span class="hint">${c.kind === "image" ? "캡처 " + esc(c.name || "") : "💬 유튜브 댓글 카드"}</span></div>
      <div class="cc-controls">
        <label>시작(초)<input type="number" step="0.1" min="0" data-f="start" value="${fmt(c.start)}"></label>
        <label>길이(초)<input type="number" step="0.1" min="0.5" data-f="len" value="${fmt(c.end - c.start)}"></label>
        <label>위치<select data-f="pos">${POSITIONS.map(p => `<option value="${p[0]}" ${p === pos ? "selected" : ""}>${p[1]}</option>`).join("")}</select></label>
        ${c.kind === "image" ? `<label>크기 <span class="hint">${Math.round(c.width * 100)}%</span><input type="range" min="30" max="100" data-f="width" value="${Math.round(c.width * 100)}"></label>` : ""}
        <button class="icon del-comment" type="button" title="삭제">✕</button>
      </div>
    </div>`;
  }).join("") || '<p class="hint">넣은 댓글이 없습니다. 없어도 됩니다.</p>';
}

$("#cap-sub-on").addEventListener("change", e => { tl.subtitles.enabled = e.target.checked; $("#cap-lines").classList.toggle("off", !e.target.checked); markDirty(); });
$("#cap-title-on").addEventListener("change", e => { tl.subtitles.titles_enabled = e.target.checked; $("#cap-titles").classList.toggle("off", !e.target.checked); markDirty(); });

$("#cap-lines").addEventListener("input", e => {
  const row = e.target.closest(".cap-line");
  if (!row) return;
  const ln = tl.subtitles.lines[Number(row.dataset.i)];
  const f = e.target.dataset.f;
  ln[f] = f === "text" ? e.target.value : Number(e.target.value);
  markDirty();
});
$("#cap-lines").addEventListener("click", e => {
  const row = e.target.closest(".cap-line");
  if (!row) return;
  const i = Number(row.dataset.i);
  if (e.target.closest(".seek")) {
    const v = $("#cap-video");
    v.currentTime = tl.subtitles.lines[i].start;
    v.play().catch(() => {});
  } else if (e.target.closest(".del-line")) {
    tl.subtitles.lines.splice(i, 1);
    renderCaptions(); markDirty();
  }
});
$("#cap-add-line").addEventListener("click", () => {
  const t = Math.min($("#cap-video").currentTime || 0, Math.max(0, totalDur() - 0.5));
  tl.subtitles.lines.push({ start: t, end: Math.min(totalDur(), t + 2), text: "새 자막", words: [] });
  tl.subtitles.lines.sort((a, b) => a.start - b.start);
  renderCaptions(); markDirty();
  const idx = tl.subtitles.lines.findIndex(l => l.start === t && l.text === "새 자막");
  const inp = $(`#cap-lines .cap-line[data-i="${idx}"] [data-f=text]`);
  if (inp) { inp.focus(); inp.select(); }
});
$("#cap-titles").addEventListener("input", e => {
  const i = e.target.dataset.scene;
  if (i === undefined) return;
  tl.scenes[Number(i)].title = e.target.value;
  markDirty();
});

$("#cap-comments").addEventListener("input", e => {
  const box = e.target.closest(".cap-comment");
  if (!box) return;
  const c = tl.comments[Number(box.dataset.i)];
  const f = e.target.dataset.f, v = e.target.value;
  if (f === "text") c.text = v;
  if (f === "start") { const len = c.end - c.start; c.start = Number(v); c.end = c.start + len; }
  if (f === "len") c.end = c.start + Math.max(0.5, Number(v));
  if (f === "pos") c.y = POSITIONS.find(p => p[0] === v)[2];
  if (f === "width") { c.width = Number(v) / 100; e.target.previousElementSibling.textContent = v + "%"; }
  markDirty();
});
$("#cap-comments").addEventListener("click", e => {
  const box = e.target.closest(".cap-comment");
  if (!box || !e.target.closest(".del-comment")) return;
  tl.comments.splice(Number(box.dataset.i), 1);
  renderCaptions(); markDirty();
});

async function saveCaptions() {
  const j = currentJob();
  tl = await api(`/api/jobs/${j.id}/timeline`, jsonOpts("PUT", {
    subtitles: { enabled: tl.subtitles.enabled, titles_enabled: tl.subtitles.titles_enabled, lines: tl.subtitles.lines },
    titles: tl.scenes.map(s => s.title),
    comments: tl.comments,
  }));
  capDirty = false;
  renderCaptions();
}

$("#cap-save").addEventListener("click", async () => {
  try { await saveCaptions(); $("#cap-msg").textContent = "저장됨 ✓ 영상에 넣으려면 「적용해서 다시 만들기」"; }
  catch (e) { $("#cap-msg").textContent = "저장 실패: " + e.message; }
});

$("#cap-rerender").addEventListener("click", async () => {
  const j = currentJob();
  setCapBusy(true);
  try {
    await saveCaptions();
    const job = await api(`/api/jobs/${j.id}/rerender`, { method: "POST" });
    onJob(job);
    watch(j.id);
    $("#cap-msg").textContent = "다시 만드는 중... 끝나면 미리보기가 바뀝니다.";
  } catch (e) {
    $("#cap-msg").textContent = "실패: " + e.message;
    setCapBusy(false);
  }
});

function setCapBusy(busy) {
  $$("#cap-editor .cap-body input, #cap-editor .cap-body textarea, #cap-editor .cap-body select, #cap-editor .cap-body button")
    .forEach(el => { el.disabled = busy; });
  $("#cap-drop").classList.toggle("disabled", busy);
  if (busy) $("#cap-msg").textContent = "다시 만드는 중... (1~3분)";
  else if (/다시 만드는 중/.test($("#cap-msg").textContent)) {
    const j = currentJob();
    $("#cap-msg").textContent = j && /^다시 만들기 실패/.test(j.message || "") ? j.message : "완료 ✓ 미리보기를 확인하세요.";
  }
}

async function addCaptures(fileList) {
  const files = [...fileList];
  const j = currentJob();
  if (!files.length || !j || !tl || $("#cap-drop").classList.contains("disabled")) return;
  try {
    if (capDirty) await saveCaptions();
    const fd = new FormData();
    files.forEach(f => fd.append("files", f));
    const t = $("#cap-video").currentTime || 0;
    fd.append("start", String(t > 0.05 ? t : -1));
    $("#cap-msg").textContent = `올리는 중... (${files.length}장)`;
    const data = await api(`/api/jobs/${j.id}/overlays`, { method: "POST", body: fd });
    tl = data.timeline;
    renderCaptions();
    $("#cap-msg").textContent = `캡처 ${data.added.length}장 추가됨 · 「적용해서 다시 만들기」를 눌러야 영상에 들어갑니다.`
      + (data.skipped.length ? ` (건너뜀: ${data.skipped.join(", ")})` : "");
  } catch (e) {
    $("#cap-msg").textContent = "캡처 추가 실패: " + e.message;
  }
}
const capDrop = $("#cap-drop");
capDrop.addEventListener("click", () => { if (!capDrop.classList.contains("disabled")) $("#cap-input").click(); });
$("#cap-input").addEventListener("change", e => { addCaptures(e.target.files); e.target.value = ""; });
["dragenter", "dragover"].forEach(ev => capDrop.addEventListener(ev, e => { e.preventDefault(); capDrop.classList.add("over"); }));
["dragleave", "drop"].forEach(ev => capDrop.addEventListener(ev, e => { e.preventDefault(); capDrop.classList.remove("over"); }));
capDrop.addEventListener("drop", e => addCaptures(e.dataTransfer.files));

// ---------- ⑧ 내보내기 ----------
async function renderExport() {
  const j = currentJob();
  if (!j || !hasVideo(j)) return;
  setVideo($("#ex-video"), j);
  $("#ex-download").href = videoUrl(j);
  $("#ex-download").download = `${j.id}.mp4`;
  $("#ex-meta").href = `/files/${j.id}/meta.txt`;
  const fill = m => {
    $("#ex-titles").innerHTML = (m.titles || []).map(t => `<div>${esc(t)}</div>`).join("");
    $("#ex-desc").value = descriptionWithSources(m.description, m.sources);
    $("#ex-tags").textContent = (m.hashtags || []).map(h => "#" + h.replace(/^#/, "")).join(" ");
  };
  if (j.script) fill({ ...j.script, sources: j.result.final_sources || j.script.sources });
  else fetch(`/files/${j.id}/meta.json`).then(r => r.ok ? r.json() : null).then(m => m && fill(m));

  const ok = hasTimeline(j);
  $("#ex-capcut").classList.toggle("hidden", !ok);
  $("#ex-unavailable").classList.toggle("hidden", ok);
  const ex = j.result.exports || {};
  $("#ex-capcut-msg").textContent = ex.capcut ? `마지막으로 보낸 CapCut 프로젝트: ${ex.capcut}` : "";
  $("#ex-pack-msg").innerHTML = ex.pack ? `최근 재료 묶음: <a href="/files/${j.id}/${ex.pack}" download>${esc(ex.pack)} 받기</a>` : "";
  if (capcutRoot === null) {
    capcutRoot = await api("/api/capcut").catch(() => ({ found: false }));
  }
  $("#ex-root").textContent = capcutRoot.found ? `CapCut 프로젝트 폴더: ${capcutRoot.drafts_root}`
    : "CapCut 프로젝트 폴더를 찾지 못했습니다. CapCut을 설치·실행한 뒤 다시 열어 주세요. 재료 묶음은 그대로 쓸 수 있습니다.";
  $("#ex-capcut-btn").disabled = !capcutRoot.found;
  setExportBusy(j.status !== "done");
}

function setExportBusy(busy) {
  $("#ex-pack-btn").disabled = busy;
  if (capcutRoot) $("#ex-capcut-btn").disabled = busy || !capcutRoot.found;
}

$("#ex-copy").addEventListener("click", () => {
  const text = [$$("#ex-titles div").map(d => d.textContent).join("\n"), "", $("#ex-desc").value, "", $("#ex-tags").textContent].join("\n");
  navigator.clipboard.writeText(text).then(() => { $("#ex-copy").textContent = "복사됨 ✓"; setTimeout(() => $("#ex-copy").textContent = "제목+설명+태그 복사", 1500); });
});

$("#ex-capcut-btn").addEventListener("click", async () => {
  const j = currentJob();
  const btn = $("#ex-capcut-btn"), msg = $("#ex-capcut-msg");
  btn.disabled = true;
  msg.textContent = "CapCut 프로젝트 만드는 중...";
  try {
    const data = await api(`/api/jobs/${j.id}/export/capcut`, { method: "POST" });
    j.result.exports = { ...(j.result.exports || {}), capcut: data.path };
    msg.textContent = `✓ CapCut에 「${data.name}」 프로젝트를 만들었습니다. CapCut을 켜서 목록에서 여세요 (켜져 있었다면 껐다 켜기).`;
  } catch (e) {
    msg.textContent = "실패: " + e.message;
  } finally {
    btn.disabled = false;
  }
});

$("#ex-pack-btn").addEventListener("click", async () => {
  const j = currentJob();
  const btn = $("#ex-pack-btn"), msg = $("#ex-pack-msg");
  btn.disabled = true;
  msg.textContent = "재료 묶음 만드는 중... (영상 구간을 자르는 데 시간이 걸릴 수 있습니다)";
  try {
    const data = await api(`/api/jobs/${j.id}/export/pack`, { method: "POST" });
    j.result.exports = { ...(j.result.exports || {}), pack: data.file };
    msg.innerHTML = `✓ <a href="/files/${j.id}/${data.file}?v=${Date.now()}" download>${esc(data.file)} 받기</a> (${fmtSize(data.size)}) · 안의 「순서.txt」에 장면 순서와 시간이 있습니다.`;
  } catch (e) {
    msg.textContent = "실패: " + e.message;
  } finally {
    btn.disabled = false;
  }
});

function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

// ---------- SSE ----------
function watch(id) {
  if (streams[id]) return;
  const es = new EventSource(`/api/jobs/${id}/events`);
  streams[id] = es;
  es.onmessage = ev => {
    const job = JSON.parse(ev.data);
    onJob(job);
    if (job.status === "done" || job.status === "error") { es.close(); delete streams[id]; }
  };
  es.onerror = () => { es.close(); delete streams[id]; setTimeout(() => refresh(id), 3000); };
}

async function refresh(id) {
  const r = await fetch("/api/jobs/" + id);
  if (!r.ok) return;
  const job = await r.json();
  onJob(job);
  if (!["done", "error"].includes(job.status)) watch(id);
}

window.addEventListener("beforeunload", e => { if (capDirty) { e.preventDefault(); e.returnValue = ""; } });

// ---------- 초기 로드 ----------
(async () => {
  await loadPresets().catch(() => {});
  loadStyleList();
  refreshUploads();
  const list = await (await fetch("/api/jobs")).json();
  list.forEach(j => { jobs[j.id] = j; renderRow(j); if (!["done", "error"].includes(j.status)) watch(j.id); });
  $("#jobs-empty").classList.toggle("hidden", list.length > 0);
  // 검토 대기·진행 중인 작업이 있으면 그 작업을 열고, 아니면 목록(없으면 새 프로젝트)부터
  const active = list.find(j => ["awaiting_review", "running", "queued"].includes(j.status));
  if (active) selectJob(active.id);
  else go(list.length ? "projects" : "source");
})();
