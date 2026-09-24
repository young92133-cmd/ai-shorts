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
    if (mode === "upload" && !$("#reference-file").value) throw new Error("분석할 영상 파일을 올리고 선택해 주세요.");
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
        style_id: $("#opt-style").value || undefined,
        upload_token: $("#up-list").children.length ? uploadToken : undefined,
        reference_name: mode === "upload" ? $("#reference-file").value : undefined,
      },
    };
    msg.textContent = "";
    const r = await fetch("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || r.statusText);
    renderJob(data, true);
    watch(data.id);
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

function openStyleModal({ analyze, style, findings }) {
  editingStyleId = style ? style.id : null;
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
  btn.disabled = true;
  let dots = 0;
  const timer = setInterval(() => { dots = (dots + 1) % 4; prog.textContent = `영상 ${urls.length}개 분석 중${".".repeat(dots)}`; }, 600);
  try {
    await ensureCurrentServer();
    const r = await fetch("/api/styles/analyze", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls, hint: $("#sm-hint").value.trim(), save: true, ...selectedLLM() }),
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
document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });

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

// ---------- 잡 카드 ----------
function jobEl(id) { return document.getElementById("job-" + id); }

function renderJob(job, prepend = false) {
  let el = jobEl(job.id);
  if (!el) {
    el = $("#job-tpl").content.firstElementChild.cloneNode(true);
    el.id = "job-" + job.id;
    $(".del", el).addEventListener("click", async () => {
      if (!confirm("이 작업과 결과 파일을 삭제할까요?")) return;
      await fetch("/api/jobs/" + job.id, { method: "DELETE" });
      el.remove();
    });
    $(".approve", el).addEventListener("click", () => approve(job.id, el));
    $(".copy", el).addEventListener("click", () => copyMeta(el));
    prepend ? $("#jobs").prepend(el) : $("#jobs").append(el);
  }
  el.className = "card job " + job.status;
  $(".mode", el).textContent = MODE_LABEL[job.mode] || job.mode;
  $(".preset", el).textContent = job.preset;
  const styleName = (job.result && job.result.style) || (styleCache[job.options?.style_id] || {}).name || "";
  let sb = $(".style-badge", el);
  if (styleName) {
    if (!sb) {
      sb = document.createElement("span");
      sb.className = "badge style-badge";
      $(".preset", el).after(sb);
    }
    sb.textContent = "🎬 " + styleName;
  } else if (sb) {
    sb.remove();
  }
  $(".title", el).textContent = (job.result && job.result.topic) || job.input || "(자동 선택)";
  $(".created", el).textContent = (job.created || "").replace("T", " ");
  // 비주얼 출처 요약 (첨부 / 기사 / 생성 / 카드)
  const vis = (job.result && job.result.visuals) || [];
  if (vis.length) {
    const c = { broll: 0, upload: 0, sourced: 0, generated: 0, card: 0 };
    vis.forEach(v => { c[v.kind] = (c[v.kind] || 0) + 1; });
    const label = [
      c.broll && `영상 클립 ${c.broll}`, c.upload && `첨부 ${c.upload}`, c.sourced && `기사 ${c.sourced}`,
      c.generated && `AI 생성 ${c.generated}`, c.card && `대체 카드 ${c.card}`,
    ].filter(Boolean).join(" · ");
    let ve = $(".visuals", el);
    if (!ve) {
      ve = document.createElement("div");
      ve.className = "visuals hint";
      $(".status", el).after(ve);
    }
    ve.textContent = "비주얼: " + label;
  }

  const instr = job.options && job.options.instructions;
  $(".title", el).title = instr ? "지침: " + instr : "";
  if (instr && !$(".instr", el)) {
    const d = document.createElement("div");
    d.className = "instr hint";
    d.textContent = "지침: " + instr;
    $(".status", el).after(d);
  }
  $(".bar", el).style.width = (job.status === "done" ? 100 : stagePct(job)) + "%";
  const st = STAGE_LABEL[job.stage] || job.stage;
  $(".status", el).textContent = job.status === "error" ? "오류: " + job.error : `${st} · ${job.message}`;
  $(".logs pre", el).textContent = (job.logs || []).join("\n");

  // 대본 검토
  const review = $(".review", el);
  if (job.status === "awaiting_review" && job.script) {
    review.classList.remove("hidden");
    if (!review.dataset.filled) {
      fillReview(review, job.script, job.id, job.result || {});
      review.dataset.filled = "1";
    }
  } else {
    review.classList.add("hidden");
  }

  // 결과
  const res = $(".result", el);
  if (job.status === "done" && job.result && job.result.video) {
    res.classList.remove("hidden");
    const v = $("video", el);
    const src = `/files/${job.id}/final.mp4`;
    if (v.dataset.src !== src) { v.src = src; v.poster = `/files/${job.id}/thumb.jpg`; v.dataset.src = src; }
    $(".download", el).href = src;
    $(".download", el).download = `${job.id}.mp4`;
    $(".folder", el).href = `/files/${job.id}/meta.txt`;
    if (job.script) {
      $(".titles", el).innerHTML = job.script.titles.map(t => `<div>${esc(t)}</div>`).join("");
      $(".desc", el).value = descriptionWithSources(job.script.description, job.result.final_sources || job.script.sources);
      $(".tags", el).textContent = job.script.hashtags.map(h => "#" + h.replace(/^#/, "")).join(" ");
    } else {
      fetch(`/files/${job.id}/meta.json`).then(r => r.ok ? r.json() : null).then(m => {
        if (!m) return;
        $(".titles", el).innerHTML = m.titles.map(t => `<div>${esc(t)}</div>`).join("");
        $(".desc", el).value = descriptionWithSources(m.description, m.sources);
        $(".tags", el).textContent = m.hashtags.map(h => "#" + h.replace(/^#/, "")).join(" ");
      });
    }
  } else {
    res.classList.add("hidden");
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

function fillReview(review, script, jobId, result) {
  const reference = result.reference;
  const summary = $(".reference-summary", review);
  summary.classList.toggle("hidden", !reference);
  if (reference) summary.textContent = `참고 영상 분석: ${reference.topic} · ${reference.summary}`;

  const sourceBox = $(".source-review", review);
  const sources = result.source_candidates || [];
  sourceBox.classList.toggle("hidden", !sources.length);
  $(".source-list", review).innerHTML = sources.map((s, i) => `<label class="candidate">
    <input type="checkbox" data-source-index="${i}" checked>
    <span>${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title || s.url)}</a>` : esc(s.title || "내 영상")}
    <small>${esc(s.channel || "")} · ${Math.round(s.duration || 0)}초</small></span>
  </label>`).join("");

  const comments = result.comment_candidates || [];
  const commentBox = $(".comment-review", review);
  commentBox.classList.toggle("hidden", !sources.length && !comments.length);
  $(".comment-list", review).innerHTML = comments.length ? comments.map(c => `<label class="candidate">
    <input type="checkbox" data-comment-id="${esc(c.id)}">
    <span><a href="${esc(c.url)}" target="_blank" rel="noopener noreferrer">${esc(c.text)}</a>
    <small>좋아요 ${c.likes || 0}개 · 원문 확인</small></span>
  </label>`).join("") : '<p class="hint">댓글 후보가 없습니다. YouTube Data API 키를 등록했는지 확인하거나, 댓글이 공개된 영상을 사용해 주세요.</p>';
  $(".comment-list", review).onchange = () => {
    const checked = $$('[data-comment-id]:checked', review);
    if (checked.length > 2) { checked.at(-1).checked = false; alert("댓글은 최대 2개까지 선택할 수 있습니다."); }
  };
  const box = $(".scenes", review);
  box.innerHTML = "";
  script.scenes.forEach((s, i) => {
    const row = document.createElement("div");
    row.className = "scene";
    row.innerHTML = `<div class="num">${i + 1}</div>
      <textarea rows="2" data-k="narration">${esc(s.narration)}</textarea>
      <div class="scene-right">
        <input type="text" data-k="on_screen_text" value="${esc(s.on_screen_text)}" placeholder="화면 키워드">
        <label class="scene-up" title="이 장면에 쓸 이미지·영상 올리기">＋
          <input type="file" accept="image/*,video/*" hidden data-scene="${i}">
        </label>
        <span class="scene-file hint"></span>
      </div>`;
    box.append(row);
  });

  $$('input[type=file][data-scene]', review).forEach(inp => {
    inp.addEventListener("change", async e => {
      const f = e.target.files[0];
      if (!f) return;
      const idx = Number(inp.dataset.scene);
      const cell = inp.closest(".scene-right").querySelector(".scene-file");
      cell.textContent = "올리는 중...";
      const fd = new FormData();
      fd.append("scene", String(idx));
      fd.append("file", f);
      try {
        const r = await fetch(`/api/jobs/${jobId}/scene-visual`, { method: "POST", body: fd });
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || r.statusText);
        cell.textContent = "✓ " + data.name;
      } catch (err) {
        cell.textContent = "실패: " + err.message;
      }
      e.target.value = "";
    });
  });

  $(".copy-prompts", review).onclick = () => {
    const text = script.scenes
      .map((s, i) => `[${i + 1}번 장면] ${s.on_screen_text}\n${s.image_prompt}`)
      .join("\n\n");
    navigator.clipboard.writeText(text).then(() => {
      const b = $(".copy-prompts", review);
      b.textContent = "복사됨 ✓ Flow에 붙여넣으세요";
      setTimeout(() => b.textContent = "장면별 이미지 프롬프트 복사", 2200);
    });
  };

  review.dataset.script = JSON.stringify(script);
}

async function approve(id, el) {
  const review = $(".review", el);
  const script = JSON.parse(review.dataset.script);
  const rows = $$(".scene", review);
  const scenes = [];
  rows.forEach((row, i) => {
    const narration = $("[data-k=narration]", row).value.trim();
    if (!narration) return;
    scenes.push({ ...script.scenes[i], narration, on_screen_text: $("[data-k=on_screen_text]", row).value.trim() });
  });
  if (!scenes.length) return alert("장면이 하나 이상 필요합니다.");
  $(".approve", el).disabled = true;
  const r = await fetch(`/api/jobs/${id}/approve`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ script: { ...script, scenes },
      source_indexes: $$('[data-source-index]:checked', review).map(x => Number(x.dataset.sourceIndex)),
      comment_ids: $$('[data-comment-id]:checked', review).map(x => x.dataset.commentId) }),
  });
  if (!r.ok) { alert((await r.json()).detail || "실패"); $(".approve", el).disabled = false; }
}

function copyMeta(el) {
  const text = [$$(".titles div", el).map(d => d.textContent).join("\n"), "", $(".desc", el).value, "", $(".tags", el).textContent].join("\n");
  navigator.clipboard.writeText(text).then(() => { $(".copy", el).textContent = "복사됨 ✓"; setTimeout(() => $(".copy", el).textContent = "제목+설명+태그 복사", 1500); });
}

function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

// ---------- SSE ----------
function watch(id) {
  if (streams[id]) return;
  const es = new EventSource(`/api/jobs/${id}/events`);
  streams[id] = es;
  es.onmessage = ev => {
    const job = JSON.parse(ev.data);
    renderJob(job);
    if (job.status === "done" || job.status === "error") { es.close(); delete streams[id]; }
  };
  es.onerror = () => { es.close(); delete streams[id]; setTimeout(() => refresh(id), 3000); };
}

async function refresh(id) {
  const r = await fetch("/api/jobs/" + id);
  if (!r.ok) return;
  const job = await r.json();
  renderJob(job);
  if (!["done", "error"].includes(job.status)) watch(id);
}

// ---------- 초기 로드 ----------
(async () => {
  loadPresets();
  loadStyleList();
  refreshUploads();
  const jobs = await (await fetch("/api/jobs")).json();
  jobs.forEach(j => { renderJob(j); if (!["done", "error"].includes(j.status)) watch(j.id); });
})();
